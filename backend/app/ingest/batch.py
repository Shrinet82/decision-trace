"""File upload ingest: several files in, each run through the live ingest pipeline, one combined diff out.

Accepts Markdown, plain text and PDF (text extracted here; a PDF without a text layer is skipped
with a clear message). Limits: 10 files, 1 MB each, 50,000 characters of text in total. The type
(meeting / ticket / doc / ADR) is detected from the content unless the caller names it.
"""

import base64
import binascii
import io
import re
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.api.rate_limiter import DEMO_LIMIT_MESSAGE, budget_exceeded
from app.ingest.live import IngestRequest, _event, run_ingest

MAX_FILES = 10
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_CHARS = 50_000
MIN_PDF_CHARS = 40
FileType = Literal["auto", "meeting", "ticket", "doc", "adr"]


class UploadFile(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: FileType = "auto"
    text: Optional[str] = Field(default=None, description="Decoded text of a .md or .txt file")
    pdf_base64: Optional[str] = Field(default=None, description="A PDF's bytes, base64 encoded")
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("name")
    @classmethod
    def _plain_name(cls, v: str) -> str:
        return v.replace("\\", "/").split("/")[-1].strip() or "file"


class BatchRequest(BaseModel):
    files: list[UploadFile] = Field(..., min_length=1, max_length=MAX_FILES)


class BatchSource(IngestRequest):
    """One file as an ingest source: the same as a pasted source but allowed to be long
    (the pipeline reads it in chunks)."""

    text: str = Field(..., min_length=1, max_length=MAX_TOTAL_CHARS)


class FileRejected(ValueError):
    """A file that cannot be read; the message is shown to the user."""


def extract_text(f: UploadFile) -> str:
    """The file's text, or FileRejected with a reason."""
    ext = f.name.lower().rsplit(".", 1)[-1] if "." in f.name else ""
    if f.pdf_base64 is not None or ext == "pdf":
        if f.pdf_base64 is None:
            raise FileRejected("The PDF has no content.")
        try:
            raw = base64.b64decode(f.pdf_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FileRejected("The PDF could not be decoded.") from exc
        if len(raw) > MAX_FILE_BYTES:
            raise FileRejected(f"The PDF is larger than {MAX_FILE_BYTES // 1_000_000} MB.")
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise FileRejected("The PDF is password protected.")
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except FileRejected:
            raise
        except Exception as exc:  # noqa: BLE001 - any parser failure is a rejected file
            raise FileRejected("The PDF could not be read.") from exc
        if len(text.strip()) < MIN_PDF_CHARS:
            raise FileRejected("The PDF has no extractable text (it looks like a scan). Upload a text PDF, Markdown or .txt instead.")
        return text.strip()
    if ext not in ("md", "markdown", "txt", ""):
        raise FileRejected(f"Unsupported file type .{ext}. Use .md, .txt or .pdf.")
    text = (f.text or "").strip()
    if len(f.text or "") > MAX_FILE_BYTES:
        raise FileRejected(f"The file is larger than {MAX_FILE_BYTES // 1_000_000} MB.")
    if not text:
        raise FileRejected("The file is empty.")
    if "\x00" in text:
        raise FileRejected("The file looks binary, not text.")
    return text


_ADR = re.compile(r"(?im)^\s*(?:#+\s*)?(?:adr[-\s]?\d*|architecture decision record)|^\s*status\s*[:\-]\s*(?:accepted|proposed|superseded|deprecated|rejected)")
_ADR_SECTIONS = re.compile(r"(?im)^#+\s*(context|decision|consequences)\b")
_MEETING = re.compile(r"(?im)\b(attendees?|agenda|minutes|participants|action items)\b|^\s*#+\s*.*\b(meeting|sync|standup|retro)\b")
_TICKET = re.compile(r"(?im)\b(steps to reproduce|acceptance criteria|story points|priority\s*:|assignee\s*:|reporter\s*:)|^\s*(?:[A-Z]{2,8}-\d+)\b")


def detect_type(text: str, name: str = "") -> str:
    """meeting | ticket | doc | adr from the content (and file name)."""
    head = text[:3000]
    if re.search(r"(?i)\badr[-_ ]?\d", name) or (_ADR.search(head) and len(_ADR_SECTIONS.findall(head)) >= 1):
        return "adr"
    if len(_ADR_SECTIONS.findall(head)) >= 2:
        return "adr"
    if _MEETING.search(head):
        return "meeting"
    if _TICKET.search(head):
        return "ticket"
    return "doc"


def detect_date(text: str, name: str = "") -> str:
    for source in (name, text[:2000]):
        m = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b", source)
        if m:
            return m.group(0)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def detect_title(text: str, name: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:200]
    return re.sub(r"\.[A-Za-z0-9]+$", "", name)[:200] or name


def detect_participants(text: str) -> list[str]:
    m = re.search(r"(?im)^\W*(?:attendees?|participants?|present)\s*[:\-]\s*(.+)$", text)
    if not m:
        return []
    names = [n.strip(" .") for n in re.split(r",|;| and ", m.group(1)) if n.strip(" .")]
    return [n for n in names if 0 < len(n.split()) <= 4][:30]


def to_source(f: UploadFile, text: str) -> BatchSource:
    kind = f.type if f.type != "auto" else detect_type(text, f.name)
    return BatchSource(
        type=kind,  # type: ignore[arg-type]
        title=detect_title(text, f.name),
        date=f.date or detect_date(text, f.name),
        text=text,
        participants=detect_participants(text) if kind == "meeting" else [],
    )


def _first(items: list[Any], key: str) -> dict[Any, Any]:
    out: dict[Any, Any] = {}
    for item in items:
        out.setdefault(item[key], item)
    return out


def merge_diffs(diffs: list[dict[str, Any]], titles: list[str]) -> dict[str, Any]:
    """One diff for a whole batch: everything added, the first 'before' and last 'after' of each change."""
    nodes = [n for d in diffs for n in d["nodes_added"]]
    edges = [e for d in diffs for e in d["edges_added"]]
    links = [lk for d in diffs for lk in d["links"]]

    def span(key: str, ident: str, before_key: str = "before", after_key: str = "after") -> list[dict[str, Any]]:
        firsts = _first([c for d in diffs for c in d[key]], ident)
        last: dict[Any, Any] = {}
        for d in diffs:
            for c in d[key]:
                last[c[ident]] = c
        merged = []
        for k, first in firsts.items():
            item = {**last[k], before_key: first[before_key], after_key: last[k][after_key]}
            if item[before_key] != item[after_key]:
                merged.append(item)
        return merged

    status_changes = span("status_changes", "id")
    person_changes = span("person_changes", "name")
    orphan_changes = span("orphan_changes", "system")
    decisions = [n for n in nodes if n["label"] == "Decision"]
    parts = [f"{len(titles)} file{'s' if len(titles) != 1 else ''}"]
    if decisions:
        parts.append(f"{len(decisions)} new decision{'s' if len(decisions) != 1 else ''}")
    if status_changes:
        parts.append(f"{len(status_changes)} status change{'s' if len(status_changes) != 1 else ''}")
    if any(p["after"] and not p["before"] for p in person_changes):
        parts.append("a person left")
    if any(o["after"] for o in orphan_changes):
        parts.append("a system orphaned")
    return {
        "ingest_id": diffs[0]["ingest_id"] if diffs else "batch",
        "ingested_at": diffs[-1]["ingested_at"] if diffs else "",
        "source": {"id": "batch", "label": "Upload", "title": f"{len(titles)} file{'s' if len(titles) != 1 else ''}: " + ", ".join(titles[:3]) + ("…" if len(titles) > 3 else "")},
        "nodes_added": nodes,
        "edges_added": edges,
        "status_changes": status_changes,
        "person_changes": person_changes,
        "orphan_changes": orphan_changes,
        "links": links,
        "summary": " · ".join(parts),
    }


async def run_batch(files: list[UploadFile], dataset: str) -> AsyncIterator[dict[str, Any]]:
    """Ingest each file in turn. Events: `files` (the plan), then per file `file` (running / done /
    skipped / failed) with that file's `step` and `graph` events tagged with its index, and finally
    `diff` (combined) or `error` (nothing could be ingested). The caller holds the ingest lock."""
    prepared: list[tuple[int, UploadFile, Optional[BatchSource], Optional[str]]] = []
    total = 0
    for i, f in enumerate(files):
        try:
            text = extract_text(f)
            total += len(text)
            if total > MAX_TOTAL_CHARS:
                raise FileRejected(f"The batch is over {MAX_TOTAL_CHARS:,} characters of text. Upload fewer or shorter files.")
            prepared.append((i, f, to_source(f, text), None))
        except FileRejected as exc:
            prepared.append((i, f, None, str(exc)))
    yield _event("files", {"files": [
        {"index": i, "name": f.name, "type": src.type if src else None, "title": src.title if src else None,
         "chars": len(src.text) if src else 0, "rejected": reason}
        for i, f, src, reason in prepared
    ]})

    diffs: list[dict[str, Any]] = []
    titles: list[str] = []
    for i, f, src, reason in prepared:
        if src is None:
            yield _event("file", {"index": i, "name": f.name, "status": "skipped", "message": reason})
            continue
        if budget_exceeded():
            yield _event("file", {"index": i, "name": f.name, "status": "failed", "message": DEMO_LIMIT_MESSAGE})
            continue
        yield _event("file", {"index": i, "name": f.name, "status": "running"})
        outcome: Optional[dict[str, Any]] = None
        message: Optional[str] = None
        async for event in run_ingest(src, dataset):
            if event["event"] in ("step", "graph"):
                yield _event(event["event"], {**event["data"], "file": i})
            elif event["event"] == "diff":
                outcome = event["data"]
            elif event["event"] == "error":
                message = event["data"]["message"]
        if outcome is not None:
            diffs.append(outcome)
            titles.append(src.title)
            yield _event("file", {"index": i, "name": f.name, "status": "done", "summary": outcome["summary"]})
        else:
            yield _event("file", {"index": i, "name": f.name, "status": "failed", "message": message or "The file could not be ingested."})
    if diffs:
        yield _event("diff", merge_diffs(diffs, titles))
    else:
        yield _event("error", {"message": "No file could be ingested. See the messages for each file."})
