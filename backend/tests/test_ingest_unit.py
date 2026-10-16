"""Unit tests for live ingest: validation, guardrails, SSE framing, diffing, reset safety."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import rate_limiter
from app.brain.health import DecisionHealthInfo
from app.ingest import live
from app.main import app

client = TestClient(app)
GOOD = {"type": "meeting", "title": "Sync", "date": "2026-10-16", "text": "We decided X."}


@pytest.fixture(autouse=True)
def _clear_limits():
    rate_limiter._ip_ingest_requests.clear()
    yield
    rate_limiter._ip_ingest_requests.clear()


@pytest.mark.parametrize(
    "patch_body",
    [{"text": ""}, {"text": "x" * 5001}, {"date": "16/10/2026"}, {"type": "email"}, {"title": ""}],
)
def test_ingest_rejects_invalid_input(patch_body):
    assert client.post("/ingest", json={**GOOD, **patch_body}).status_code == 422


def test_ingest_rate_limited_to_three_per_minute():
    async def fake_run(req, dataset):
        yield {"event": "diff", "data": {"summary": "ok"}}

    with patch("app.api.ingest.run_ingest", fake_run):
        codes = [client.post("/ingest", json=GOOD).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_ingest_streams_server_sent_events():
    async def fake_run(req, dataset):
        yield {"event": "step", "data": {"step": "reading", "status": "running", "label": "Reading source"}}
        yield {"event": "diff", "data": {"summary": "1 new decision"}}

    with patch("app.api.ingest.run_ingest", fake_run):
        res = client.post("/ingest", json=GOOD)
    assert res.headers["content-type"].startswith("text/event-stream")
    assert res.text == (
        'event: step\ndata: {"step": "reading", "status": "running", "label": "Reading source"}\n\n'
        'event: diff\ndata: {"summary": "1 new decision"}\n\n'
    )


@pytest.mark.asyncio
async def test_busy_returns_409():
    async with live.INGEST_LOCK:
        assert client.post("/ingest", json=GOOD).status_code == 409
        assert client.post("/ingest/reset").status_code == 409


def test_match_system_and_system_like():
    known = ["Kafka", "RabbitMQ", "Redis"]
    assert live._match_system("kafka", known) == "Kafka"
    assert live._match_system("Kafka for all event messaging across services", known) == "Kafka"
    assert live._match_system("Kafka and RabbitMQ", known) is None  # ambiguous
    assert live._is_system_like("OpenTelemetry")
    assert not live._is_system_like("Kafka for all event messaging across services")


@pytest.mark.asyncio
async def test_match_person():
    people = ["Alice Vance", "Bob Martin"]
    assert await live._match_person("alice vance", people) == "Alice Vance"
    assert await live._match_person("Ms. Vance", people) == "Alice Vance"
    assert await live._match_person("Carol New", people) is None


def _h(d_id, status, title="T"):
    return DecisionHealthInfo(id=d_id, title=title, status=status, reason="")


def test_build_diff_reports_status_person_orphan_changes_and_summary():
    before = {
        "health": {"d4": _h("d4", "contradicted"), "d7": _h("d7", "contradicted")},
        "orphans": {"Elasticsearch"},
        "codes": {"d4": "DEC-04", "d7": "DEC-07"},
    }
    after = {
        "health": {"d4": _h("d4", "active"), "d7": _h("d7", "superseded"), "dnew": _h("dnew", "active")},
        "orphans": {"Elasticsearch", "Kafka"},
        "codes": {"d4": "DEC-04", "d7": "DEC-07", "dnew": "DEC-18"},
    }
    created = [
        {"kind": "node", "id": "Decision:dnew", "label": "Decision", "name": "New", "decision_id": "dnew"},
        {"kind": "edge", "source": "Decision:dnew", "target": "Decision:d7", "type": "supersedes", "reason": "r"},
    ]
    overrides = [{"label": "Person", "name": "Alice Vance", "before": {"is_active": True, "leave_date": ""},
                  "after": {"is_active": False, "leave_date": "2026-10-16"}}]
    links = [{"new": 0, "existing": "d7", "relation": "supersedes", "reason": "r"}]
    req = live.IngestRequest(**GOOD)
    diff = live.build_diff("ing_1", "now", req, "Meeting:Sync", created, overrides, links, before, after)
    assert diff["nodes_added"][0]["decision_code"] == "DEC-18"
    assert [(s["decision_code"], s["before"], s["after"]) for s in diff["status_changes"]] == [
        ("DEC-04", "contradicted", "active"), ("DEC-07", "contradicted", "superseded")
    ]
    assert diff["person_changes"] == [{"name": "Alice Vance", "field": "departed", "before": False, "after": True}]
    assert diff["orphan_changes"] == [{"system": "Kafka", "before": False, "after": True}]
    assert diff["links"] == [{"new_code": "DEC-18", "existing_code": "DEC-07", "relation": "supersedes", "reason": "r"}]
    assert diff["summary"] == "1 new decision · 2 status changes · conflict resolved · 1 person left · 1 system orphaned"


@pytest.mark.asyncio
async def test_reset_only_touches_tagged_data():
    """Every deleting query in reset must be restricted to demo-tagged items."""
    queries: list[str] = []

    async def fake_query(q, dataset_name=None, params=None):
        queries.append(q)
        if "RETURN count(n)" in q or "RETURN count(r)" in q:
            return [[0]]
        return []

    with (
        patch.object(live, "query_graph", new=fake_query),
        patch.object(live, "resolve_active_graph_name", new=AsyncMock(return_value="g")),
    ):
        await live.reset_demo("ds")
    destructive = [q for q in queries if "DELETE" in q]
    assert destructive, "reset issued no deletes"
    assert all("demo_ingest_id IS NOT NULL" in q for q in destructive)
