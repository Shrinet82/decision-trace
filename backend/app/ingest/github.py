"""Import decisions from a public GitHub repository.

Reads ADR / decision markdown from the usual folders (docs/adr, doc/adr, docs/decisions, adr,
architecture/decisions, or any ADR-*.md) and, optionally, recent closed pull requests and issues
that look like decisions (label or keyword: decision, rfc, adr, proposal). ADRs are mapped
deterministically: status (Accepted / Superseded / Deprecated), "Supersedes ADR-n" and
"Superseded by ADR-n" lines become `supersedes` edges, deciders / authors become people, the
repository becomes a Project, and dates come from front matter, the document, or its first commit.
The language model is used only for small, bounded jobs: naming the systems an ADR is about, and
judging whether a pull request or issue records a decision. Total model tokens per import are capped.

Events: `progress` (phase, label, detail), then `diff` or `error`.
"""

import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.api.rate_limiter import DEMO_LIMIT_MESSAGE, budget_exceeded, estimate_tokens
from app.brain import cache
from app.brain.memory import query_graph
from app.brain.names import split_names
from app.ingest.live import (
    TAG,
    _event,
    _llm,
    _now,
    _snapshot_state,
    build_diff,
    record_change,
    rollback,
)
from app.ingest.source_text import excerpt, quote_in

logger = logging.getLogger("decision_trace.ingest.github")

MAX_ADRS = 40
MAX_ITEMS = 30
MAX_BODY = 3000
TOKEN_CAP = 80_000  # estimated model tokens per import
HTTP_TIMEOUT = 20.0
LLM_CONCURRENCY = 4
KEYWORDS = re.compile(r"\b(decision|decided|rfc|adr|proposal|proposed)\b", re.IGNORECASE)
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


class GithubRequest(BaseModel):
    repo_url: str = Field(..., min_length=8, max_length=300)
    include_prs: bool = Field(default=True, description="Also read closed PRs and issues that look like decisions")


class GithubError(Exception):
    """A problem to show the user as it is."""


def parse_repo_url(url: str) -> tuple[str, str]:
    """owner, repo from https://github.com/owner/repo (extra path, .git and query are ignored)."""
    raw = url.strip()
    if not re.match(r"^[a-z]+://", raw):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.hostname not in ("github.com", "www.github.com"):
        raise GithubError("Enter a public repository URL on github.com, like https://github.com/owner/repo.")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise GithubError("The URL needs an owner and a repository: https://github.com/owner/repo.")
    owner, repo = parts[0], re.sub(r"\.git$", "", parts[1])
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", n) or set(n) <= {"."} for n in (owner, repo)):
        raise GithubError("That does not look like a GitHub repository name.")
    return owner, repo


# --------------------------------------------------------------------------------------------
# Finding ADR files
# --------------------------------------------------------------------------------------------

_ADR_DIR = re.compile(
    r"(^|/)(docs?/)?(adrs?|decisions?|architecture[-_ ]decisions?|architecture/decisions?|decision[-_ ]records?)(/|$)",
    re.IGNORECASE,
)
_ADR_FILE = re.compile(r"(^|/)(adr[-_ ]?\d+[^/]*|\d{2,4}[-_.][^/]+)\.(md|markdown)$", re.IGNORECASE)
_SKIP_FILE = re.compile(r"(^|/)([^/]*template[^/]*|readme[^/]*|index|summary|contributing[^/]*)\.(md|markdown)$|(^|/)templates?/", re.IGNORECASE)


def select_adr_paths(paths: list[str], limit: int = MAX_ADRS) -> list[str]:
    """ADR markdown paths from a repository's file list: in a decision folder, or named ADR-n.md."""
    picked = []
    for p in paths:
        if not p.lower().endswith((".md", ".markdown")):
            continue
        if re.search(r"(^|/)(node_modules|vendor|\.github)/", p):
            continue
        base = p.rsplit("/", 1)[-1]
        if _SKIP_FILE.search(p) or base.lower().startswith(("template", "readme")):
            continue
        if _ADR_FILE.search(p) or (_ADR_DIR.search(p) and p.count("/") <= 6):
            picked.append(p)
    # Numbered files first (they are the real records), then by path; shallow folders before deep ones
    picked = sorted(set(picked), key=lambda p: (not re.search(r"\d{2,4}", p.rsplit("/", 1)[-1]), p.count("/"), p))
    return picked[:limit]


# --------------------------------------------------------------------------------------------
# Reading one ADR
# --------------------------------------------------------------------------------------------

STATUS_WORDS = {
    "accepted": "accepted", "approved": "accepted", "adopted": "accepted", "decided": "accepted",
    "proposed": "proposed", "draft": "proposed", "pending": "proposed", "rfc": "proposed", "open": "proposed",
    "rejected": "rejected", "declined": "rejected", "withdrawn": "rejected",
    "deprecated": "deprecated", "obsolete": "deprecated", "retired": "deprecated",
    "superseded": "superseded", "replaced": "superseded",
}


@dataclass
class Adr:
    path: str
    number: Optional[int]
    title: str
    status: str
    date: Optional[str]
    deciders: list[str]
    supersedes: list[int]
    superseded_by: list[int]
    quote: str
    body: str
    systems: list[str] = field(default_factory=list)
    url: str = ""


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("'\"")
    return meta, text[m.end():]


def _numbers(fragment: str) -> list[int]:
    found: list[int] = []
    for m in re.finditer(r"(?i)\badr[-_ ]?0*(\d+)|\[0*(\d+)[.\]:)]|\(\s*\.?/?0*(\d{2,4})[-_][\w.-]+\.md|\b0*(\d{1,4})\b(?=\s*[.:]\s)", fragment):
        n = next(int(g) for g in m.groups() if g)
        if n not in found:
            found.append(n)
    return found


def _status_section(body: str) -> str:
    m = re.search(r"(?im)^#{1,4}\s*status\s*$\n+((?:.+\n?){1,6})", body)
    return m.group(1) if m else ""


def _section(body: str, names: tuple[str, ...]) -> str:
    pattern = r"(?im)^#{1,4}\s*(?:%s)[^\n]*$\n+(.*?)(?=^#{1,4}\s|\Z)" % "|".join(names)
    m = re.search(pattern, body, re.DOTALL)
    return m.group(1).strip() if m else ""


def _people(value: str) -> list[str]:
    names: list[str] = []
    for part in re.split(r",|;|\band\b|&|\n", re.sub(r"[\[\]<>()@*_`]|https?://\S+|\S+@\S+", " ", value)):
        part = re.sub(r"\s+", " ", part).strip(" .-")
        if 0 < len(part.split()) <= 4 and len(part) <= 40 and not re.search(r"\d{3,}", part) and part.lower() not in ("none", "n/a", "tbd", "team"):
            names.append(part)
    return names[:6]


def parse_adr(path: str, text: str) -> Adr:
    meta, body = parse_front_matter(text)
    base = path.rsplit("/", 1)[-1]

    # number: file name first, then the heading
    number: Optional[int] = None
    m = re.match(r"(?i)^(?:adr[-_ ]?)?0*(\d{1,4})(?:[-_.]|$)", base)
    if m:
        number = int(m.group(1))

    # title: front matter, else the first level-1 heading, else the file name
    h1 = next((line for line in body.splitlines() if re.match(r"^#\s+\S", line)), "")
    title = (meta.get("title") or re.sub(r"^#\s*", "", h1)).strip()
    hm = re.match(r"(?i)^(?:adr[-_ ]?)?0*(\d{1,4})\s*[.:)\-–—]\s*(.+)$", title)
    if hm:
        number = number if number is not None else int(hm.group(1))
        title = hm.group(2).strip()
    # "Architecture Decision Record: Use ADRs" -> "Use ADRs" (the prefix says nothing the type does not)
    title = re.sub(r"(?i)^(?:architecture decision record|adr)\s*[:\-–—]\s*", "", title).strip() or title
    if not title:
        stem = re.sub(r"\.(md|markdown)$", "", base, flags=re.IGNORECASE)
        title = re.sub(r"^(?:adr[-_ ]?)?\d+[-_.]?", "", stem, flags=re.IGNORECASE).replace("-", " ").replace("_", " ").strip().capitalize() or stem

    # status
    status_text = meta.get("status", "")
    inline = re.search(r"(?im)^[\s*_>-]*status\**\s*[:\-]\s*\**\s*(.+)$", body)
    section = _status_section(body)
    status_text = status_text or (inline.group(1) if inline else "") or section
    status = "accepted"
    for word in re.findall(r"[a-z]+", status_text.lower()):
        if word in STATUS_WORDS:
            status = STATUS_WORDS[word]
            break
    status_block = " ".join(filter(None, [meta.get("status", ""), inline.group(0) if inline else "", section]))

    superseded_by: list[int] = []
    sb = re.search(r"(?i)superseded\s+by([^\n]*)", status_block + "\n" + "\n".join(body.splitlines()[:25]))
    if sb:
        superseded_by = _numbers(sb.group(1))
    sup = re.search(r"(?i)(?<!ed )\bsupersedes\b([^\n]*)", status_block + "\n" + "\n".join(body.splitlines()[:25]))
    supersedes = _numbers(sup.group(1)) if sup else []
    if number is not None:
        supersedes = [n for n in supersedes if n != number]
        superseded_by = [n for n in superseded_by if n != number]

    # date
    date = meta.get("date") or meta.get("created") or meta.get("updated") or ""
    dm = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", date or "") or re.search(r"(?i)\bdate\W{0,4}\s*(\d{4}-\d{2}-\d{2})", body[:1500])
    date_value = dm.group(1) if dm else None

    # deciders
    raw_people = meta.get("deciders") or meta.get("decision-makers") or meta.get("decision makers") or meta.get("authors") or meta.get("author") or ""
    if not raw_people:
        pm = re.search(r"(?im)^[\s*_>-]*(?:deciders?|decision[- ]makers?|authors?|decided by|proposed by)\**\s*[:\-]\s*(.+)$", body)
        raw_people = pm.group(1) if pm else ""
    deciders = _people(raw_people)

    # the decision itself, verbatim: the Decision section's opening, else the first prose paragraph
    quote = ""
    decision_text = _section(body, ("decision outcome", "decision", "resolution", "outcome")) or ""
    source = decision_text or next((p for p in re.split(r"\n\s*\n", body) if p.strip() and not p.strip().startswith("#") and ":" not in p.strip()[:20]), "")
    for line in source.splitlines():
        line = line.strip()
        if len(line) >= 20 and not line.startswith(("#", "|", "```", "---")):
            quote = line[:320]
            break
    if quote and quote not in text:
        quote = ""
    return Adr(
        path=path, number=number, title=title[:200], status=status, date=date_value, deciders=deciders,
        supersedes=supersedes, superseded_by=superseded_by, quote=quote, body=body.strip(),
    )


def supersession_pairs(adrs: list[Adr]) -> list[tuple[Adr, Adr, str]]:
    """(newer, older, why) for every supersession stated by an ADR, deduplicated, no self links."""
    by_number = {a.number: a for a in adrs if a.number is not None}
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[Adr, Adr, str]] = []

    def add(newer: Adr, older: Adr, why: str) -> None:
        key = (newer.path, older.path)
        if newer.path != older.path and key not in seen:
            seen.add(key)
            pairs.append((newer, older, why))

    for a in adrs:
        for n in a.supersedes:
            if n in by_number:
                add(a, by_number[n], f"ADR-{a.number} says it supersedes ADR-{n}")
        for n in a.superseded_by:
            if n in by_number:
                add(by_number[n], a, f"ADR-{a.number} is marked superseded by ADR-{n}")
    return pairs


def is_decision_item(title: str, labels: list[str], body: str) -> bool:
    return bool(KEYWORDS.search(title) or any(KEYWORDS.search(label) for label in labels) or KEYWORDS.search((body or "")[:600]))


# --------------------------------------------------------------------------------------------
# Model jobs (small and capped)
# --------------------------------------------------------------------------------------------

class AdrSystems(BaseModel):
    systems: list[str] = Field(default_factory=list, description="Up to 3 technologies or systems this decision is about, each a short name like 'Kafka' or 'PostgreSQL'")


class ItemJudgement(BaseModel):
    is_decision: bool = Field(..., description="True only if the text records a decision that was made")
    title: str = Field(default="", description="The decision in one short line")
    decided_by: Optional[str] = Field(default=None, description="Person who made or approved it, only if stated")
    system: Optional[str] = Field(default=None, description="Main technology or system affected, short name")
    status: Literal["accepted", "proposed", "rejected"] = "accepted"
    quote: str = Field(default="", description="One sentence copied exactly from the text that states the decision")


SYSTEMS_PROMPT = (
    "You read one architecture decision record. Name up to three technologies or systems the decision is "
    "about (e.g. 'Kafka', 'PostgreSQL', 'Kubernetes'). Short proper names only; no phrases. If none, return an empty list."
)
ITEM_PROMPT = (
    "You read a GitHub pull request or issue. Decide whether it records a DECISION that was made (a choice, "
    "adoption, deprecation, or standard), as opposed to a bug, a feature request or a discussion. If it does, give "
    "a one-line title, who decided only if the text says, the main system affected, whether it was accepted, "
    "proposed or rejected, and copy one sentence from the text exactly as the quote."
)


@dataclass
class TokenMeter:
    cap: int = TOKEN_CAP
    used: int = 0

    def can_afford(self, *texts: str, reply: int = 300) -> bool:
        return self.used + estimate_tokens(*texts) + reply <= self.cap

    def spend(self, *texts: str, reply: int = 300) -> None:
        self.used += estimate_tokens(*texts) + reply


# --------------------------------------------------------------------------------------------
# GitHub access
# --------------------------------------------------------------------------------------------

class GithubClient:
    def __init__(self) -> None:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "decision-trace-import", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.authenticated = bool(token)
        self.http = httpx.AsyncClient(headers=headers, timeout=HTTP_TIMEOUT, follow_redirects=True)
        self.remaining: Optional[int] = None

    async def close(self) -> None:
        await self.http.aclose()

    async def api(self, endpoint: str, /, **params: Any) -> Any:
        try:
            res = await self.http.get(f"{API}{endpoint}", params=params or None)
        except httpx.HTTPError as exc:
            raise GithubError("GitHub could not be reached. Try again in a moment.") from exc
        left = res.headers.get("x-ratelimit-remaining")
        if left is not None:
            self.remaining = int(left)
        if res.status_code == 404:
            raise GithubError("That repository was not found. It must be public, and the URL spelled correctly.")
        if res.status_code in (401, 403, 429):
            if self.remaining == 0 or res.headers.get("retry-after") or "rate limit" in res.text.lower():
                reset = res.headers.get("x-ratelimit-reset")
                when = ""
                if reset and reset.isdigit():
                    when = " It resets at " + datetime.fromtimestamp(int(reset), timezone.utc).strftime("%H:%M UTC") + "."
                hint = "" if self.authenticated else " Unauthenticated requests are limited to 60 per hour."
                raise GithubError(f"GitHub's API rate limit has been reached.{hint}{when} Try again later.")
            raise GithubError("GitHub refused the request. Is the repository public?")
        if res.status_code >= 400:
            raise GithubError(f"GitHub responded with {res.status_code}. Try again in a moment.")
        return res.json()

    async def raw(self, owner: str, repo: str, ref: str, path: str) -> Optional[str]:
        """File text from raw.githubusercontent.com (not counted against the API rate limit)."""
        try:
            res = await self.http.get(f"{RAW}/{owner}/{repo}/{ref}/{path}")
        except httpx.HTTPError:
            return None
        return res.text if res.status_code == 200 else None


async def _gather_limited(coros: list[Any], limit: int) -> list[Any]:
    sem = asyncio.Semaphore(limit)

    async def run(c: Any) -> Any:
        async with sem:
            return await c

    return await asyncio.gather(*(run(c) for c in coros), return_exceptions=True)


# --------------------------------------------------------------------------------------------
# The import
# --------------------------------------------------------------------------------------------

def _progress(phase: str, status: str, label: str, detail: Optional[str] = None) -> dict[str, Any]:
    data: dict[str, Any] = {"phase": phase, "status": status, "label": label}
    if detail:
        data["detail"] = detail
    return _event("progress", data)


def _day(stamp: Optional[str]) -> Optional[str]:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", stamp or "")
    return m.group(1) if m else None


async def run_github_import(req: GithubRequest, dataset: str, client: Optional[GithubClient] = None) -> AsyncIterator[dict[str, Any]]:
    """Run the import, yielding events. The caller holds the ingest lock."""
    started = datetime.now(timezone.utc)
    ingest_id = f"ing_{uuid.uuid4().hex[:10]}"
    ingested_at = _now()
    tags = {TAG: ingest_id, "ingested_at": ingested_at}
    created: list[dict[str, Any]] = []
    meter = TokenMeter()
    gh = client or GithubClient()
    wrote = False
    try:
        owner, repo = parse_repo_url(req.repo_url)
        full = f"{owner}/{repo}"
        if budget_exceeded():
            raise GithubError(DEMO_LIMIT_MESSAGE)

        # 1. Fetching
        yield _progress("fetching", "running", "Fetching repository", full)
        info = await gh.api(f"/repos/{owner}/{repo}")
        if info.get("private"):
            raise GithubError("That repository is private. Only public repositories can be imported.")
        branch = info.get("default_branch") or "main"
        existing = await query_graph("MATCH (p:Project {name: $n}) RETURN count(p)", dataset_name=dataset, params={"n": full})
        if existing and existing[0][0]:
            raise GithubError(f"{full} has already been imported into this organization.")
        tree = await gh.api(f"/repos/{owner}/{repo}/git/trees/{branch}", recursive="1")
        paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
        adr_paths = select_adr_paths(paths)
        yield _progress("fetching", "running", "Fetching repository", f"{len(paths):,} files, {len(adr_paths)} look like ADRs")

        texts = await _gather_limited([gh.raw(owner, repo, branch, p) for p in adr_paths], 8)
        adrs: list[Adr] = []
        for path, text in zip(adr_paths, texts, strict=True):
            if isinstance(text, str) and len(text.strip()) > 80:
                adr = parse_adr(path, text[:60_000])
                adr.url = f"https://github.com/{full}/blob/{branch}/{path}"
                adrs.append(adr)

        items: list[dict[str, Any]] = []
        if req.include_prs:
            prs = await gh.api(f"/repos/{owner}/{repo}/pulls", state="closed", per_page=MAX_ITEMS, sort="updated", direction="desc")
            issues = await gh.api(f"/repos/{owner}/{repo}/issues", state="closed", per_page=MAX_ITEMS, sort="updated", direction="desc")
            for kind, rows in (("PR", prs), ("ISSUE", [i for i in issues if "pull_request" not in i])):
                for r in rows:
                    labels = [lab["name"] for lab in r.get("labels", [])]
                    if is_decision_item(r.get("title", ""), labels, r.get("body") or ""):
                        items.append({
                            "kind": kind, "number": r["number"], "title": r.get("title", "")[:200], "body": (r.get("body") or "")[:MAX_BODY],
                            "author": (r.get("user") or {}).get("login"), "assignees": [a["login"] for a in r.get("assignees", [])],
                            "date": _day(r.get("merged_at") or r.get("closed_at") or r.get("created_at")), "url": r.get("html_url"),
                            "merged": bool(r.get("merged_at")),
                        })
        yield _progress("fetching", "done", "Fetching repository", f"found {len(adrs)} ADRs and {len(items)} decision-like PRs/issues")
        if not adrs and not items:
            raise GithubError(
                f"No ADRs or decision-like pull requests were found in {full}. Looked in docs/adr, doc/adr, docs/decisions, adr, "
                "architecture/decisions and for ADR-*.md files."
            )

        # Dates and authors for ADRs the document does not date (the first commit that added the file)
        undated = [a for a in adrs if not a.date]
        fallback_date = _day(info.get("pushed_at")) or _now()[:10]
        estimated = 0
        for a in undated:
            if gh.remaining is not None and gh.remaining < 12:
                break
            try:
                commits = await gh.api(f"/repos/{owner}/{repo}/commits", path=a.path, per_page=1)
            except GithubError:
                break
            if commits:
                c = commits[0]
                a.date = _day(c["commit"]["author"]["date"])
                author = (c.get("commit", {}).get("author") or {}).get("name")
                if not a.deciders and author:
                    a.deciders = [author]
        for a in adrs:
            if not a.date:
                a.date = fallback_date
                estimated += 1

        # 2. Extracting: systems per ADR, decisions from PRs/issues (bounded)
        yield _progress("extracting", "running", "Extracting systems and decisions", f"{len(adrs)} ADRs, {len(items)} PRs/issues")

        async def adr_systems(a: Adr) -> None:
            sample = f"{a.title}\n{a.body[:2200]}"
            if not meter.can_afford(SYSTEMS_PROMPT, sample, reply=120):
                return
            meter.spend(SYSTEMS_PROMPT, sample, reply=120)
            out = await _llm(SYSTEMS_PROMPT, sample, AdrSystems, 120)
            a.systems = [s.strip() for s in out.systems if 0 < len(s.split()) <= 3 and len(s) <= 40][:3]

        await _gather_limited([adr_systems(a) for a in adrs], LLM_CONCURRENCY)

        judged: list[dict[str, Any]] = []

        async def judge(item: dict[str, Any]) -> None:
            text = f"{item['title']}\n\n{item['body']}"
            if not meter.can_afford(ITEM_PROMPT, text, reply=250):
                return
            meter.spend(ITEM_PROMPT, text, reply=250)
            out = await _llm(ITEM_PROMPT, text, ItemJudgement, 250)
            if out.is_decision and out.quote and quote_in(out.quote, text):
                judged.append({**item, "decision": out})

        await _gather_limited([judge(i) for i in items], LLM_CONCURRENCY)
        yield _progress(
            "extracting", "done", "Extracting systems and decisions",
            f"{len(adrs)} ADR decisions, {len(judged)} of {len(items)} PRs/issues recorded a decision · ~{meter.used:,} model tokens",
        )

        # 3. Linking: supersession from the ADRs' own words (no model call)
        yield _progress("linking", "running", "Linking decisions")
        before = await _snapshot_state(dataset)
        pairs = supersession_pairs(adrs)
        yield _progress("linking", "done", "Linking decisions", f"{len(pairs)} supersedes link{'s' if len(pairs) != 1 else ''}" + (f" · {estimated} dates estimated" if estimated else ""))

        # 4. Writing
        yield _progress("writing", "running", "Writing to FalkorDB")
        wrote = True
        decision_ids: dict[str, str] = {}
        people: dict[str, str] = {}  # lower-case name -> stored name
        known = await query_graph("MATCH (p:Person) RETURN p.name", dataset_name=dataset)
        for (n,) in known:
            people[str(n).lower()] = str(n)
        known_sys = await query_graph("MATCH (s:System) RETURN s.name", dataset_name=dataset)
        systems = {str(n).lower(): str(n) for (n,) in known_sys}

        new_people: list[dict[str, Any]] = []

        def person(name: str) -> str:
            key = name.lower()
            if key not in people:
                people[key] = name
                new_people.append({"name": name, "is_active": True, "leave_date": "", **tags})
                created.append({"kind": "node", "id": f"Person:{name}", "label": "Person", "name": name})
            return people[key]

        new_systems: list[dict[str, Any]] = []

        def system(name: str) -> str:
            key = name.lower()
            if key not in systems:
                systems[key] = name
                new_systems.append({"name": name, **tags})
                created.append({"kind": "node", "id": f"System:{name}", "label": "System", "name": name})
            return systems[key]

        project = {"id": f"proj_{ingest_id}", "name": full, "url": info.get("html_url"), "description": (info.get("description") or "")[:300], **tags}
        created.append({"kind": "node", "id": f"Project:{full}", "label": "Project", "name": full})
        docs: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        edges: dict[str, list[dict[str, Any]]] = {k: [] for k in ("decided_by", "about_system", "based_on", "part_of", "supersedes", "raised_by")}

        def add_edge(kind: str, a: str, b: str, props: Optional[dict[str, Any]] = None, a_key: str = "id", b_key: str = "id") -> None:
            edges[kind].append({"a": a, "b": b, "props": {**(props or {}), **tags}})

        for a in adrs:
            d_id = f"dec_{uuid.uuid4().hex[:12]}"
            decision_ids[a.path] = d_id
            doc_id = f"src_{uuid.uuid4().hex[:12]}"
            docs.append({"id": doc_id, "title": f"{a.title}", "name": a.path, "date": a.date, "body": excerpt(a.body), "source_type": "adr", "url": a.url, **tags})
            created.append({"kind": "node", "id": f"Document:{a.path}", "label": "Document", "name": a.title})
            quote = a.quote or a.title
            decisions.append({
                "id": d_id, "title": a.title, "summary": quote, "rationale": quote, "status": a.status if a.status != "superseded" else "accepted",
                "confidence": 0.95, "evidence_quote": quote, "decided_on": a.date, "source_url": a.url,
                "adr_number": a.number if a.number is not None else -1, **tags,
            })
            created.append({"kind": "node", "id": f"Decision:{d_id}", "label": "Decision", "name": a.title, "decision_id": d_id})
            add_edge("based_on", d_id, doc_id, {"quote": quote})
            add_edge("part_of", d_id, project["id"])
            for name in a.deciders:
                add_edge("decided_by", d_id, person(name))
            for s in a.systems:
                add_edge("about_system", d_id, system(s))

        links: list[dict[str, Any]] = []
        order = {a.path: i for i, a in enumerate(adrs)}
        for newer, older, why in pairs:
            add_edge("supersedes", decision_ids[newer.path], decision_ids[older.path], {"reason": why, "judged_by": "adr-text"})
            links.append({"new": order[newer.path], "existing": decision_ids[older.path], "title": older.title, "relation": "supersedes", "reason": why})

        for j in judged:
            out: ItemJudgement = j["decision"]
            d_id = f"dec_{uuid.uuid4().hex[:12]}"
            doc_id = f"src_{uuid.uuid4().hex[:12]}"
            ticket_id = f"{j['kind']}-{j['number']}"
            docs.append({"id": doc_id, "ticket_id": ticket_id, "title": j["title"], "opened": j["date"], "date": j["date"], "status": "closed", "body": excerpt(j["body"]), "source_type": "ticket", "url": j["url"], **tags, "_label": "Ticket"})
            created.append({"kind": "node", "id": f"Ticket:{ticket_id}", "label": "Ticket", "name": j["title"]})
            decisions.append({
                "id": d_id, "title": (out.title or j["title"])[:200], "summary": out.quote, "rationale": out.quote, "status": out.status,
                "confidence": 0.7, "evidence_quote": out.quote, "decided_on": j["date"], "source_url": j["url"], "adr_number": -1, **tags,
            })
            created.append({"kind": "node", "id": f"Decision:{d_id}", "label": "Decision", "name": (out.title or j["title"])[:200], "decision_id": d_id})
            add_edge("based_on", d_id, doc_id, {"quote": out.quote})
            add_edge("part_of", d_id, project["id"])
            who = out.decided_by or j["author"]
            for name in split_names(who) if out.decided_by else ([who] if who else []):
                add_edge("decided_by", d_id, person(name))
            if out.system and len(out.system.split()) <= 3:
                add_edge("about_system", d_id, system(out.system.strip()))
            for name in j["assignees"]:
                add_edge("raised_by", doc_id, person(name))

        await query_graph("CREATE (p:Project) SET p += $props", dataset_name=dataset, params={"props": project})
        for label in ("Document", "Ticket"):
            rows = [{k: v for k, v in d.items() if k != "_label"} for d in docs if d.get("_label", "Document") == label]
            if rows:
                await query_graph(f"UNWIND $rows AS r CREATE (n:{label}) SET n += r", dataset_name=dataset, params={"rows": rows})
        if decisions:
            await query_graph("UNWIND $rows AS r CREATE (n:Decision) SET n += r", dataset_name=dataset, params={"rows": decisions})
        if new_people:
            await query_graph("UNWIND $rows AS r CREATE (n:Person) SET n += r", dataset_name=dataset, params={"rows": new_people})
        if new_systems:
            await query_graph("UNWIND $rows AS r CREATE (n:System) SET n += r", dataset_name=dataset, params={"rows": new_systems})
        wiring = {
            "decided_by": ("Decision", "id", "Person", "name"),
            "about_system": ("Decision", "id", "System", "name"),
            "based_on": ("Decision", "id", "Document|Ticket", "id"),
            "part_of": ("Decision", "id", "Project", "id"),
            "supersedes": ("Decision", "id", "Decision", "id"),
            "raised_by": ("Ticket", "id", "Person", "name"),
        }
        for kind, rows in edges.items():
            if not rows:
                continue
            a_label, a_key, b_label, b_key = wiring[kind]
            b_pattern = f"(b) WHERE (b:Document OR b:Ticket) AND b.{b_key} = r.b" if "|" in b_label else f"(b:{b_label} {{{b_key}: r.b}})"
            await query_graph(
                f"UNWIND $rows AS r MATCH (a:{a_label} {{{a_key}: r.a}}) MATCH {b_pattern} CREATE (a)-[x:{kind}]->(b) SET x += r.props",
                dataset_name=dataset, params={"rows": rows},
            )
            for r in rows:
                created.append({"kind": "edge", "source": r["a"], "target": r["b"], "type": kind, **({"reason": r["props"]["reason"]} if "reason" in r["props"] else {})})
        n_nodes = sum(1 for c in created if c["kind"] == "node")
        yield _progress("writing", "done", "Writing to FalkorDB", f"{n_nodes} nodes, {sum(1 for c in created if c['kind'] == 'edge')} edges")

        # 5. Health
        yield _progress("health", "running", "Recomputing health")
        cache.invalidate()
        after = await _snapshot_state(dataset)
        cache.put("health", dataset, after["health"])
        cache.put("codes", dataset or "", after["codes"])

        class _Req:  # build_diff only needs the title
            title = f"GitHub: {full}"

        diff = build_diff(ingest_id, ingested_at, _Req(), f"Project:{full}", created, [], links, before, after)  # type: ignore[arg-type]
        diff["source"] = {"id": f"Project:{full}", "label": "Project", "title": full}
        seconds = (datetime.now(timezone.utc) - started).total_seconds()
        diff["import"] = {"repo": full, "adrs": len(adrs), "items_considered": len(items), "items_decisions": len(judged), "supersedes": len(pairs), "tokens_estimated": meter.used, "seconds": round(seconds, 1)}
        yield _progress("health", "done", "Recomputing health", diff["summary"])
        await record_change(dataset, {
            "id": ingest_id, "kind": "ingest", "title": f"GitHub: {full}", "type": "github", "created_at": ingested_at,
            "summary": diff["summary"], "diff": diff, "overrides": [],
        })
        yield _event("diff", diff)
    except GithubError as exc:
        if wrote:
            await rollback(dataset, ingest_id, [])
        yield _event("error", {"message": str(exc)})
    except Exception as exc:  # noqa: BLE001 - surfaced to the client as an error event
        logger.exception("GitHub import %s failed", ingest_id)
        if wrote:
            await rollback(dataset, ingest_id, [])
        yield _event("error", {"message": f"{type(exc).__name__}: {exc}"[:300]})
    finally:
        if client is None:
            await gh.close()
