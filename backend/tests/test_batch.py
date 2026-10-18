"""File upload ingest: reading files, detecting type/date/title, chunking, combined diff."""

import base64
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api import rate_limiter
from app.ingest import batch
from app.ingest.batch import FileRejected, UploadFile, detect_date, detect_participants, detect_title, detect_type, extract_text, merge_diffs
from app.ingest.live import chunk_text
from app.server import app

client = TestClient(app)


def _pdf(text: str) -> bytes:
    """A minimal one-page PDF with a text layer."""
    stream = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def test_text_files_are_read_and_empty_or_binary_ones_rejected():
    assert extract_text(UploadFile(name="notes.md", text="  We decided X.  ")) == "We decided X."
    with pytest.raises(FileRejected, match="empty"):
        extract_text(UploadFile(name="a.txt", text="   "))
    with pytest.raises(FileRejected, match="binary"):
        extract_text(UploadFile(name="a.txt", text="ab\x00cd"))
    with pytest.raises(FileRejected, match="Unsupported"):
        extract_text(UploadFile(name="a.docx", text="hello"))


def test_pdf_text_is_extracted():
    sentence = "We decided to adopt Kafka for all event messaging across services."
    text = extract_text(UploadFile(name="adr.pdf", pdf_base64=base64.b64encode(_pdf(sentence)).decode()))
    assert "adopt Kafka" in text


def test_a_pdf_without_text_is_skipped_with_a_clear_message():
    from io import BytesIO

    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(612, 792)
    buf = BytesIO()
    w.write(buf)
    with pytest.raises(FileRejected, match="no extractable text"):
        extract_text(UploadFile(name="scan.pdf", pdf_base64=base64.b64encode(buf.getvalue()).decode()))
    with pytest.raises(FileRejected, match="could not be"):
        extract_text(UploadFile(name="bad.pdf", pdf_base64=base64.b64encode(b"not a pdf").decode()))


def test_type_detection():
    adr = "# ADR-0007: Use Postgres\n\nStatus: Accepted\n\n## Context\nx\n\n## Decision\nWe use Postgres.\n"
    assert detect_type(adr) == "adr"
    assert detect_type("# Architecture sync\nAttendees: Alice Vance, Bob Martin\nWe agreed.") == "meeting"
    assert detect_type("TICK-12 Login fails\nPriority: high\nSteps to reproduce: ...") == "ticket"
    assert detect_type("Quarterly plan and thoughts.") == "doc"
    assert detect_type("whatever", "adr-0003-cache.md") == "adr"


def test_date_title_and_participants():
    assert detect_date("Sync held 2026-03-04.") == "2026-03-04"
    assert detect_date("no date", "2025-12-01-notes.md") == "2025-12-01"
    assert len(detect_date("no date")) == 10
    assert detect_title("\n\n# Use Kafka\nbody", "x.md") == "Use Kafka"
    assert detect_title("", "plan.md") == "plan"
    assert detect_participants("Attendees: Alice Vance, Bob Martin and Kevin Flynn\n") == ["Alice Vance", "Bob Martin", "Kevin Flynn"]


def test_chunks_respect_the_size_and_keep_everything():
    short = "a short note"
    assert chunk_text(short) == [short]
    paras = [f"Paragraph {i}. " + "word " * 200 for i in range(12)]
    text = "\n\n".join(paras)
    chunks = chunk_text(text, 4500)
    assert len(chunks) > 1 and all(len(c) <= 4500 for c in chunks)
    assert "".join(c.replace("\n", "").replace(" ", "") for c in chunks) == text.replace("\n", "").replace(" ", "")
    assert all(len(c) <= 100 for c in chunk_text("x" * 250, 100))


def _diff(i, **over):
    base = {
        "ingest_id": f"ing_{i}", "ingested_at": f"2026-10-18T0{i}:00:00Z", "source": {"id": f"S{i}", "label": "Document", "title": f"T{i}"},
        "nodes_added": [{"id": f"Decision:{i}", "label": "Decision", "name": f"D{i}"}],
        "edges_added": [{"source": f"Decision:{i}", "target": f"Document:{i}", "type": "based_on"}],
        "status_changes": [], "person_changes": [], "orphan_changes": [], "links": [], "summary": "x",
    }
    return {**base, **over}


def test_merged_diff_spans_the_whole_batch():
    d1 = _diff(1, status_changes=[{"id": "d", "decision_code": "DEC-01", "title": "t", "before": "active", "after": "superseded"}])
    d2 = _diff(2, status_changes=[{"id": "d", "decision_code": "DEC-01", "title": "t", "before": "superseded", "after": "active"},
                                   {"id": "e", "decision_code": "DEC-02", "title": "u", "before": "active", "after": "contradicted"}])
    merged = merge_diffs([d1, d2], ["T1", "T2"])
    assert len(merged["nodes_added"]) == 2 and len(merged["edges_added"]) == 2
    # d went active -> superseded -> active: no net change; e did change
    assert [c["id"] for c in merged["status_changes"]] == ["e"]
    assert merged["summary"] == "2 files · 2 new decisions · 1 status change"
    assert merged["source"]["title"].startswith("2 files: T1, T2")


async def test_run_batch_streams_per_file_and_one_combined_diff():
    async def fake_run(req, dataset):
        yield {"event": "step", "data": {"step": "reading", "status": "done", "label": "Reading source"}}
        if "boom" in req.text:
            yield {"event": "error", "data": {"message": "ValueError: boom"}}
            return
        yield {"event": "diff", "data": _diff(1)}

    files = [
        UploadFile(name="a.md", text="We decided to use Kafka."),
        UploadFile(name="b.md", text="boom"),
        UploadFile(name="c.txt", text="   "),
    ]
    with patch.object(batch, "run_ingest", fake_run):
        events = [e async for e in batch.run_batch(files, "ds")]
    kinds = [(e["event"], e["data"].get("status")) for e in events if e["event"] in ("file", "files", "diff", "error")]
    assert kinds[0] == ("files", None)
    assert ("file", "done") in kinds and ("file", "failed") in kinds and ("file", "skipped") in kinds
    assert events[-1]["event"] == "diff"
    steps = [e for e in events if e["event"] == "step"]
    assert steps and all("file" in e["data"] for e in steps)
    plan = events[0]["data"]["files"]
    assert plan[2]["rejected"] == "The file is empty."


async def test_run_batch_ends_with_an_error_when_nothing_could_be_ingested():
    events = [e async for e in batch.run_batch([UploadFile(name="a.md", text="  ")], "ds")]
    assert events[-1]["event"] == "error"


async def test_total_text_is_capped():
    big = "x" * 30_000
    files = [UploadFile(name="a.md", text=big), UploadFile(name="b.md", text=big)]
    events = [e async for e in batch.run_batch(files, "ds")]
    assert "over 50,000 characters" in events[0]["data"]["files"][1]["rejected"]


@pytest.fixture(autouse=True)
def _clear_limits():
    rate_limiter._ip_ingest_requests.clear()
    yield
    rate_limiter._ip_ingest_requests.clear()


def test_endpoint_limits_the_number_of_files_and_streams_events():
    too_many = {"files": [{"name": f"{i}.md", "text": "x"} for i in range(11)]}
    assert client.post("/ingest/batch", json=too_many).status_code == 422
    assert client.post("/ingest/batch", json={"files": []}).status_code == 422

    async def fake_batch(files, dataset):
        yield {"event": "diff", "data": {"summary": "ok"}}

    with patch("app.api.ingest.run_batch", fake_batch):
        res = client.post("/ingest/batch", json={"files": [{"name": "a.md", "text": "We decided X."}]})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/event-stream")
    assert 'event: diff' in res.text
