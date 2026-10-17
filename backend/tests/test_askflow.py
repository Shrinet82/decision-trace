"""Unit tests for the Ask pipeline: intent rules, per-intent assembly, the event stream and the
shared result of POST /ask and POST /ask/stream.

Assembly tests use rows captured read-only from the production graph
(tests/fixtures/askflow_live_rows.json), so they exercise real result shapes without a database.
tests/test_askflow_live.py runs the same questions against FalkorDB.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.askflow import assemble, pipeline, queries
from app.askflow.intent import classify_intent
from app.brain.health import DecisionHealthInfo
from app.server import app

client = TestClient(app)
FIX = json.loads((Path(__file__).parent / "fixtures" / "askflow_live_rows.json").read_text())
ROWS: dict[str, list[Any]] = FIX["rows"]
CODES: dict[str, str] = FIX["codes"]
HEALTH = {
    i: DecisionHealthInfo(id=i, title=h["title"], status=h["status"], reason=h["reason"])
    for i, h in FIX["health"].items()
}
TODAY = "2026-10-17"
ID_BY_CODE = {c: i for i, c in CODES.items()}


@pytest.mark.parametrize(
    "question, intent, focus",
    [
        ("Why did we move sessions to Keycloak?", "why", None),
        ("Do any decisions conflict?", "status", "conflicts"),
        ("What's affected if we drop Snowflake?", "impact", None),
        ("Who knows the most about Kafka?", "expertise", None),
        ("Which systems have no owner?", "status", "ownership"),
        ("Why did we choose Kafka over RabbitMQ?", "why", None),
        ("What replaced Redis for session storage?", "why", None),
        ("Who decided to adopt Prometheus?", "why", None),
        ("Who owns Elasticsearch?", "other", None),
        ("What happens if we decommission Vault?", "impact", None),
        ("Who is the expert on Postgres?", "expertise", None),
        ("Are any decisions possibly stale?", "status", "stale"),
    ],
)
def test_intent_rules(question, intent, focus):
    parsed = classify_intent(question)
    assert (parsed.intent, parsed.focus) == (intent, focus)


def test_match_names_whole_words_in_order():
    people, systems = pipeline.match_names(
        "Did Alice pick Kafka over RabbitMQ or Vaulted storage?",
        ["Alice Vance", "Bob Martin"], ["RabbitMQ", "Kafka", "Vault"],
    )
    assert people == ["Alice Vance"]
    assert systems == ["Kafka", "RabbitMQ"]  # order of appearance; "Vaulted" is not "Vault"


def test_impact_snowflake_includes_chain_and_people():
    res = assemble.build_impact("Snowflake", ROWS["IMPACT_DECISIONS"], ROWS["IMPACT_PEOPLE"],
                                ROWS["IMPACT_TICKETS"], CODES, HEALTH, TODAY)
    sections = {s["key"]: s for s in res.sections}
    codes = [i["code"] for i in sections["decisions"]["items"]]
    assert {"DEC-03", "DEC-13", "DEC-17"} <= set(codes)
    # Direct decisions first (by date), then the supersedes chain
    assert codes == ["DEC-03", "DEC-17", "DEC-13"]
    assert CODES[res.primary_decision_id] == "DEC-17"  # newest decision on Snowflake still in force
    people = sections["people"]["items"]
    assert people[0]["name"] == "Fiona Gallagher" and people[0]["detail"].startswith("owner")
    assert {"Bob Martin", "Carlos Mendez", "Laura Croft"} <= {p["name"] for p in people}
    assert [t["name"] for t in sections["teams"]["items"]] == ["Data Platform"]
    tickets = sections["tickets"]["items"]
    assert [t["date"] for t in tickets] == sorted((t["date"] for t in tickets), reverse=True)
    assert all(len(t["date"]) == 10 for t in tickets)  # '2026-004-24' normalised
    # The evidence graph links DEC-13 -> DEC-03 and cites only based_on sources
    path = res.graph.capped()
    assert {"source": ID_BY_CODE["DEC-13"], "target": ID_BY_CODE["DEC-03"], "type": "supersedes",
            "properties": {}} in path["edges"]
    assert set(res.graph.citations) == {"TICK-103", "TICK-104", "Cloud Cost Optimization Taskforce"}


def test_expertise_kafka_ranks_alice_first_with_counts():
    experts = assemble.rank_experts(ROWS["EXPERTISE"], CODES, TODAY)
    top = experts[0]
    assert top["name"] == "Alice Vance"
    assert top["evidence"] == {"decided": 1, "owns": 1, "meetings": 1, "tickets": 1}
    assert top["score"] == 3 + 3 + 2 + 1
    assert top["decisions"] == ["DEC-04"]
    scores = [e["score"] for e in experts if not e["departed"]]
    assert scores == sorted(scores, reverse=True)


def test_expertise_ranks_departed_people_last_but_keeps_them():
    alice_left = json.loads(json.dumps(ROWS["EXPERTISE"]).replace('"leave_date": ""', '"leave_date": ""'))
    for group in alice_left[0]:
        for pair in group:
            if pair[0] and pair[0].get("name") == "Alice Vance":
                pair[0]["is_active"] = False
                pair[0]["leave_date"] = "2026-10-16"
    experts = assemble.rank_experts(alice_left, CODES, TODAY)
    assert experts[-1]["name"] == "Alice Vance" and experts[-1]["departed"]
    assert experts[0]["name"] == "Bob Martin"


def test_status_conflicts_and_ownership():
    res = assemble.build_status("conflicts", ROWS["STATUS_DECISIONS"], [], CODES, HEALTH, TODAY)
    conflicts = res.sections[0]
    assert conflicts["title"] == "Conflicts"
    assert sorted(i["code"] for i in conflicts["items"]) == ["DEC-04", "DEC-07"]
    assert CODES[res.primary_decision_id] == "DEC-07"  # the newer decision of the pair
    assert {"TICK-105", "TICK-106"} <= set(res.graph.citations)

    own = assemble.build_status("ownership", [], ROWS["STATUS_SYSTEMS"], CODES, HEALTH, TODAY)
    orphaned = {s["key"]: s for s in own.sections}["orphaned"]["items"]
    assert [i["name"] for i in orphaned] == ["Elasticsearch"]
    assert "Marcus Aurelius" in orphaned[0]["detail"]
    assert own.primary_decision_id is None


def test_citations_only_from_based_on_and_named_in_answer():
    g = assemble.EvidenceGraph()
    g.node("d1", "Decision", {"title": "X"}, 10)
    g.source("d1", "Ticket", "TICK-1", "One", None)
    g.source("d1", "Ticket", "TICK-2", "Two", None)
    g.citations["TICK-9"] = {"type": "ticket", "id": "TICK-9", "title": "Phantom"}  # no based_on edge
    cited = assemble.verified_citations(g, "Based on TICK-2 and TICK-9.")
    assert [c["id"] for c in cited] == ["TICK-2"]


# --- the event stream ---------------------------------------------------------------------------

def _fake_query(by_query: dict[str, list[Any]]):
    async def run(cypher, dataset_name=None, params=None):
        return by_query.get(cypher, [])
    return run


def _llm(text: str):
    async def stream(intent, context, question):
        for word in text.split(" "):
            yield word + " "
    return stream


def _patches(by_query: dict[str, list[Any]], answer: str, decisions_matched: list[tuple[str, float]] | None = None):
    return [
        patch("app.askflow.pipeline.query_graph_threaded", side_effect=_fake_query(by_query)),
        patch("app.askflow.pipeline.get_decision_codes_cached", new=AsyncMock(return_value=CODES)),
        patch("app.askflow.pipeline.get_health_map", new=AsyncMock(return_value=HEALTH)),
        patch("app.askflow.pipeline._match_decisions", return_value=decisions_matched or []),
        patch("app.askflow.pipeline._stream_llm", side_effect=_llm(answer)),
        patch("app.askflow.pipeline.record_llm_call"),
    ]


async def _events(question: str, patches) -> list[dict[str, Any]]:
    for p in patches:
        p.start()
    try:
        return [e async for e in pipeline.run_ask(question, "test")]
    finally:
        for p in patches:
            p.stop()


async def test_impact_stream_steps_queries_path_tokens_done():
    by_query = {queries.ROSTER: ROWS["ROSTER"], queries.IMPACT_DECISIONS: ROWS["IMPACT_DECISIONS"],
                queries.IMPACT_PEOPLE: ROWS["IMPACT_PEOPLE"], queries.IMPACT_TICKETS: ROWS["IMPACT_TICKETS"]}
    events = await _events("What's affected if we drop Snowflake?",
                           _patches(by_query, "Dropping Snowflake affects DEC-17 (Cloud Cost Optimization Taskforce)."))
    names = [e["event"] for e in events]
    assert names[-1] == "done" and "error" not in names
    done_steps = [e["data"]["step"] for e in events if e["event"] == "step" and e["data"]["status"] == "done"]
    assert done_steps == ["understanding", "matching", "traversal", "health", "composing"]
    assert names.index("path") < names.index("token")
    q = [e["data"] for e in events if e["event"] == "query"]
    assert [x["name"] for x in q][0] == "roster"
    assert {x["name"] for x in q[1:]} == {"impact_decisions", "impact_people", "impact_tickets"}
    assert all(isinstance(x["rows"], int) and "query" in x for x in q)
    done = events[-1]["data"]
    assert done["intent"] == "impact"
    assert CODES[done["primary_decision_id"]] == "DEC-17"
    assert [c["id"] for c in done["citations"]] == ["Cloud Cost Optimization Taskforce"]
    assert done["entities"] == [{"label": "System", "name": "Snowflake"}]
    assert [s["step"] for s in done["trace"]["steps"]] == done_steps
    assert len(done["trace"]["queries"]) == 4 and done["trace"]["total_ms"] >= 0


async def test_unanswerable_skips_traversal_and_the_model():
    patches = _patches({queries.ROSTER: ROWS["ROSTER"]}, "should not be called")
    events = await _events("Why did we choose quantum encryption for database backups?", patches)
    steps = {e["data"]["step"]: e["data"]["status"] for e in events
             if e["event"] == "step" and e["data"]["status"] != "running"}
    assert steps == {"understanding": "done", "matching": "done", "traversal": "skipped",
                     "health": "skipped", "composing": "done"}
    done = events[-1]["data"]
    assert done["answer"] == pipeline.NOT_FOUND
    assert done["graph_path"]["nodes"] == [] and done["citations"] == [] and done["primary_decision_id"] is None


async def test_model_saying_not_found_clears_the_path():
    keycloak = ID_BY_CODE["DEC-11"]
    patches = _patches({queries.ROSTER: ROWS["ROSTER"]}, "The answer is not found in the Company Brain.",
                       decisions_matched=[(keycloak, 0.9)])
    events = await _events("Why did we pick quantum vaults?", patches)
    done = events[-1]["data"]
    assert done["graph_path"]["nodes"] == [] and done["primary_decision_id"] is None


def test_post_ask_and_stream_return_the_same_result():
    by_query = {queries.ROSTER: ROWS["ROSTER"], queries.EXPERTISE: ROWS["EXPERTISE"]}
    answer = "Alice Vance knows Kafka best: decided DEC-04 and owns Kafka."
    for p in _patches(by_query, answer):
        p.start()
    try:
        plain = client.post("/ask", json={"question": "Who knows the most about Kafka?"}).json()
        with client.stream("POST", "/ask/stream", json={"question": "Who knows the most about Kafka?"}) as r:
            assert r.headers["content-type"].startswith("text/event-stream")
            body = "".join(r.iter_text())
    finally:
        patch.stopall()
    frames = [f for f in body.split("\n\n") if f.startswith("event: done")]
    streamed = json.loads(frames[0].split("data: ", 1)[1])
    for key in ("answer", "citations", "primary_decision_id", "intent", "experts", "graph_path"):
        assert plain[key] == streamed[key], key
    assert plain["experts"][0]["name"] == "Alice Vance"
    assert plain["intent"] == "expertise" and plain["primary_decision_id"] is None


async def test_llm_failure_falls_back_to_graph_results():
    by_query = {queries.ROSTER: ROWS["ROSTER"], queries.STATUS_SYSTEMS: ROWS["STATUS_SYSTEMS"]}

    async def broken(intent, context, question):
        raise TimeoutError("model down")
        yield ""  # pragma: no cover

    patches = _patches(by_query, "")
    patches[4] = patch("app.askflow.pipeline._stream_llm", side_effect=broken)
    events = await _events("Which systems have no owner?", patches)
    done = events[-1]["data"]
    assert "Owner has left: 1" in done["answer"]
    assert done["sections"][0]["items"][0]["name"] == "Elasticsearch"


async def test_weak_title_matches_are_dropped_when_a_system_is_named():
    noise = [(ID_BY_CODE["DEC-08"], 0.61), (ID_BY_CODE["DEC-05"], 0.61)]
    by_query = {queries.ROSTER: ROWS["ROSTER"]}
    events = await _events("Who owns Elasticsearch?", _patches(by_query, "Marcus Aurelius owns it.", noise))
    matching = next(e["data"] for e in events if e["event"] == "step" and e["data"]["step"] == "matching"
                    and e["data"]["status"] == "done")
    assert matching["entities"] == [{"label": "System", "name": "Elasticsearch"}]
    names = [e["data"]["name"] for e in events if e["event"] == "query"]
    assert "decisions_by_id" not in names and "system_owners" in names
