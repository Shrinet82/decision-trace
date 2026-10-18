"""Demo safety (destructive-script guard, reset() guard, automatic demo reset) and /sources."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.brain import memory
from app.brain.health import DecisionHealthInfo
from app.ingest import live
from app.server import app

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from destructive_guard import (  # noqa: E402
    ALLOW_ENV,
    CONFIRM_FLAG,
    FORCE_PRODUCTION_FLAG,
    PRODUCTION_GRAPH,
    GuardRefused,
    confirm_delete_all_graphs,
)

client = TestClient(app)


# --- scripts/destructive_guard.py -----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_leaked_opt_in(monkeypatch):
    monkeypatch.delenv(ALLOW_ENV, raising=False)


def _confirm(argv, env, typed):
    confirm_delete_all_graphs("company_brain", argv, env=env, read=lambda _prompt: typed)


def test_guard_requires_the_flag():
    with pytest.raises(GuardRefused, match=CONFIRM_FLAG):
        _confirm([], {"FALKORDB_GRAPH_NAME": "scratch"}, "scratch")


def test_guard_refuses_production_without_force():
    with pytest.raises(GuardRefused, match="production"):
        _confirm([CONFIRM_FLAG], {"FALKORDB_GRAPH_NAME": PRODUCTION_GRAPH}, PRODUCTION_GRAPH)


def test_guard_requires_the_typed_graph_name():
    with pytest.raises(GuardRefused, match="did not match"):
        _confirm([CONFIRM_FLAG], {"FALKORDB_GRAPH_NAME": "scratch"}, "scratch-typo")


def test_guard_allows_a_confirmed_run_and_opts_in_for_this_process(monkeypatch):
    _confirm([CONFIRM_FLAG], {"FALKORDB_GRAPH_NAME": "scratch"}, "scratch")
    import os

    assert os.environ[ALLOW_ENV] == "1"
    monkeypatch.delenv(ALLOW_ENV)
    _confirm([CONFIRM_FLAG, FORCE_PRODUCTION_FLAG], {"FALKORDB_GRAPH_NAME": PRODUCTION_GRAPH}, PRODUCTION_GRAPH)


# --- app.brain.memory.reset guard -------------------------------------------------------------------

async def test_reset_refuses_delete_all_graphs_without_opt_in():
    with pytest.raises(memory.DestructiveResetRefused):
        await memory.reset(dataset_name="anything", delete_all_graphs=True)


async def test_reset_refuses_the_production_graph():
    with patch("app.brain.memory.resolve_active_graph_name", new=AsyncMock(return_value=PRODUCTION_GRAPH)):
        with pytest.raises(memory.DestructiveResetRefused):
            await memory.check_reset_allowed("company_brain", False)
        with pytest.raises(memory.DestructiveResetRefused):
            await memory.check_reset_allowed(None, False)  # bare reset() targets DATASET_NAME


async def test_reset_allows_other_datasets_and_confirmed_runs(monkeypatch):
    with patch("app.brain.memory.resolve_active_graph_name", new=AsyncMock(return_value="holdout-graph")):
        await memory.check_reset_allowed("holdout_eval", False)
    monkeypatch.setenv(ALLOW_ENV, "1")
    await memory.check_reset_allowed(None, True)


def test_admin_reset_of_production_is_forbidden():
    token = memory._settings.ADMIN_TOKEN.get_secret_value()
    with patch("app.brain.memory.resolve_active_graph_name", new=AsyncMock(return_value=PRODUCTION_GRAPH)):
        r = client.post("/admin/reset", headers={"X-Admin-Token": token})
    assert r.status_code == 403


# --- automatic demo reset ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)


def _status_rows(nodes: int, edges: int, last: str | None):
    async def run(query, dataset_name=None, params=None):
        if "Change" in query:
            return [[last]] if last else []
        return [[edges]] if "()-[r]->()" in query else [[nodes]]
    return run


async def _status(nodes, edges, last):
    with patch("app.brain.memory.query_graph_threaded", side_effect=_status_rows(nodes, edges, last)), \
         patch("app.ingest.live.resolve_active_graph_name", new=AsyncMock(return_value="g")):
        return await live.demo_status("ds", now=NOW)


async def test_demo_status_counts_down_from_the_last_ingest():
    three_min_ago = (NOW - timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = await _status(2, 7, three_min_ago)
    assert s["has_demo_data"] and s["seconds_left"] == 7 * 60
    assert s["resets_at"] == "2026-10-17T12:07:00Z"


async def test_demo_status_without_demo_data_or_record():
    assert (await _status(0, 0, None))["resets_at"] is None
    orphaned = await _status(1, 0, None)  # tagged data but no ingest record: due now
    assert orphaned["seconds_left"] == 0


async def test_auto_reset_loop_resets_only_when_due():
    due = {"has_demo_data": True, "seconds_left": 0}
    waiting = {"has_demo_data": True, "seconds_left": 120}
    for state, expected in ((due, 1), (waiting, 0)):
        reset = AsyncMock(return_value={})
        sleeps = iter([None, StopAsyncIteration()])

        async def fake_sleep(_s):
            nxt = next(sleeps)
            if isinstance(nxt, BaseException):
                raise nxt

        with patch("app.ingest.live.demo_status", new=AsyncMock(return_value=state)), \
             patch("app.orgs.registry.load", new=AsyncMock()), \
             patch("app.orgs.registry.sample_orgs", return_value=[]), \
             patch("app.ingest.live.reset_demo", new=reset), \
             patch("app.ingest.live.asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(StopAsyncIteration):
                await live.auto_reset_loop("ds", interval_seconds=0)
        assert reset.await_count == expected


# --- /sources ---------------------------------------------------------------------------------------

def stub_trace(canned: dict[str, list[Any]]):
    async def run(self, name, query, params=None):
        self.entries.append({"name": name, "query": query, "params": params or {}, "ms": 1.0})
        return canned.get(name, [])
    return patch("app.brain.trace.CypherTrace.run", run)


TICKET_TEXT = "To guarantee ordering, Alice Vance decided: Use Kafka for all event messaging across services."


def test_sources_list_counts_and_dates():
    canned = {
        "documents": [["Ticket", "TICK-105", "Kafka ordering", "2026-003-01", "closed", None, 1],
                      ["Meeting", "Core Messaging Architecture Sync", "Core Messaging Architecture Sync", "2026-04-08", None, None, 1],
                      ["Document", "People update", "People update", "2026-10-16", None, "ing_1", 0]],
        "records": [["System", "Kafka", "message-broker", 1], ["Person", "Alice Vance", "Principal Platform Engineer", 3]],
    }
    with stub_trace(canned):
        r = client.get("/sources").json()
    assert r["counts"] == {"ticket": 1, "meeting": 1, "document": 1, "system": 1, "person": 1}
    first = r["items"][0]
    assert first["key"] == "TICK-105" and first["date"] == "2026-03-01" and first["linked_decisions"] == 1
    assert [i for i in r["items"] if i["kind"] == "document"][0]["demo"] is True


def test_source_detail_quotes_people_and_systems():
    canned = {"source": [[
        {"ticket_id": "TICK-105", "title": "Kafka ordering", "body": TICKET_TEXT, "opened": "2026-03-01", "status": "closed"},
        [["d4", "Adopt Kafka", None, "Use Kafka for all event messaging across services"],
         ["d9", "Unrelated", None, "This sentence is not in the ticket"]],
        [["Alice Vance", "raised_by", True, "", "Engineer"], ["Alice Vance", "decided", True, "", "Engineer"],
         ["Bob Martin", "assigned_to", False, "2026-01-01", "SRE"]],
        ["Kafka"],
    ]]}
    health = {"d4": DecisionHealthInfo(id="d4", title="Adopt Kafka", status="contradicted", reason="x")}
    with stub_trace(canned), \
         patch("app.api.sources.get_decision_codes_cached", new=AsyncMock(return_value={"d4": "DEC-04", "d9": "DEC-09"})), \
         patch("app.api.sources.get_health_map", new=AsyncMock(return_value=health)):
        doc = client.get("/sources/ticket/TICK-105").json()
    assert doc["text"] == TICKET_TEXT
    quotes = {d["decision_code"]: d["quote"] for d in doc["decisions"]}
    # The decision-level quote is used only when it is verbatim in this source
    assert quotes == {"DEC-04": "Use Kafka for all event messaging across services", "DEC-09": None}
    assert doc["decisions"][0]["health"] == "contradicted"
    people = {p["name"]: p for p in doc["people"]}
    assert people["Alice Vance"]["relation"] == "raised · decided"
    assert people["Bob Martin"]["departed"] is True
    assert doc["systems"] == ["Kafka"]
    assert doc["cypher"]["queries"][0]["name"] == "source"


def test_source_record_fields_hide_bookkeeping():
    canned = {"source": [[
        {"id": "x", "name": "Elasticsearch", "system_type": "search-engine", "vendor": "Elastic NV", "email": "x@y"},
        [[None, None, None, None]],
        [["Person", "Marcus Aurelius", "owns"]],
    ]]}
    with stub_trace(canned), \
         patch("app.api.sources.get_decision_codes_cached", new=AsyncMock(return_value={})), \
         patch("app.api.sources.get_health_map", new=AsyncMock(return_value={})):
        doc = client.get("/sources/system/Elasticsearch").json()
    assert doc["fields"] == {"name": "Elasticsearch", "system_type": "search-engine", "vendor": "Elastic NV"}
    assert doc["related"] == [{"label": "Person", "name": "Marcus Aurelius", "relation": "owns"}]
    assert doc["decisions"] == []


def test_source_not_found_and_bad_kind():
    with stub_trace({"source": []}):
        assert client.get("/sources/ticket/TICK-999").status_code == 404
    assert client.get("/sources/admin/x").status_code == 422


async def test_auto_reset_loop_also_resets_showcase_organizations():
    due = {"has_demo_data": True, "seconds_left": 0}
    reset = AsyncMock(return_value={})
    sleeps = iter([None, StopAsyncIteration()])
    seen: list[str] = []

    async def fake_sleep(_s):
        nxt = next(sleeps)
        if isinstance(nxt, BaseException):
            raise nxt

    async def fake_reset(dataset, title="x"):
        from app.brain import orgctx

        seen.append(orgctx.current_slug() or "acme")
        return {}

    showcase = [{"id": "arachne", "graph_name": "org_arachne_x"}]
    with patch("app.ingest.live.demo_status", new=AsyncMock(return_value=due)), \
         patch("app.orgs.registry.load", new=AsyncMock()), \
         patch("app.orgs.registry.sample_orgs", return_value=showcase), \
         patch("app.ingest.live.reset_demo", new=fake_reset), \
         patch("app.ingest.live.asyncio.sleep", side_effect=fake_sleep):
        with pytest.raises(StopAsyncIteration):
            await live.auto_reset_loop("ds", interval_seconds=0)
    assert seen == ["acme", "arachne"]
    assert reset.await_count == 0
