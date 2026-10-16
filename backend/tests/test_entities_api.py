"""Unit tests for the decision page, systems and people endpoints.

CypherTrace.run is stubbed by query name, so these tests check how each endpoint assembles its
response. tests/test_entities_live.py runs the real Cypher against FalkorDB.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.brain.health import DecisionHealthInfo, SystemOrphanInfo, is_departed
from app.main import app

client = TestClient(app)

CODES = {"d_old": "DEC-01", "d_mid": "DEC-02", "d_new": "DEC-03", "d_rival": "DEC-04"}
HEALTH = {
    "d_old": DecisionHealthInfo(id="d_old", title="Old", status="superseded", reason="by mid"),
    "d_mid": DecisionHealthInfo(id="d_mid", title="Mid", status="superseded", reason="by new"),
    "d_new": DecisionHealthInfo(id="d_new", title="New", status="contradicted", reason="rival"),
    "d_rival": DecisionHealthInfo(id="d_rival", title="Rival", status="contradicted", reason="new"),
}
ALICE = {"name": "Alice Vance", "role": "Engineer", "is_active": True, "leave_date": ""}
MARCUS = {"name": "Marcus Aurelius", "role": "Architect", "is_active": False, "leave_date": "2025-11-30"}


def stub_trace(canned: dict[str, list[Any]]):
    """Patch CypherTrace.run to return canned rows by query name and record the calls."""
    calls: list[str] = []

    async def run(self, name, query, params=None):
        calls.append(name)
        self.entries.append({"name": name, "query": query, "params": params or {}, "ms": 1.0})
        return canned.get(name, [])

    return patch("app.brain.trace.CypherTrace.run", run), calls


def common_patches(module: str):
    return (
        patch(f"{module}.get_decision_codes_cached", new=AsyncMock(return_value=CODES)),
        patch(f"{module}.get_health_map", new=AsyncMock(return_value=HEALTH)),
    )


DECISION_CANNED = {
    "decision": [
        [
            {"id": "d_mid", "title": "Mid", "decided_on": "2026-03-01", "evidence_quote": "Alice decided: mid."},
            [ALICE, MARCUS],
            ["Redis"],
        ]
    ],
    "supersedes_chain": [["d_old", 1]],
    "superseded_by_chain": [["d_new", 1]],
    "contradictions": [["d_rival", False]],
    "system_timeline": [["d_old"], ["d_new"]],
    "decision_attributes": [
        ["d_old", "Old", "2026-01-01", ["Alice Vance"], ["Redis"]],
        ["d_mid", "Mid", "2026-03-01", ["Alice Vance", "Marcus Aurelius"], ["Redis"]],
        ["d_new", "New", "2026-05-01", ["Alice Vance"], ["Redis"]],
        ["d_rival", "Rival", "2026-05-02", ["Bob Martin"], ["Kafka"]],
    ],
    "lineage_edges": [["d_mid", "supersedes", "d_old"], ["d_new", "supersedes", "d_mid"], ["d_rival", "contradicts", "d_mid"]],
    "sources": [
        ["d_mid", "Ticket", {"ticket_id": "TICK-1", "title": "Latency", "closed": "2026-03-01"}],
        ["d_old", "Meeting", {"title": "Kickoff", "date": "2026-01-01"}],
    ],
    "impact": [
        ["Person", ALICE, "owns", "System", {"name": "Redis"}],
        ["Person", ALICE, "member_of", "Team", {"name": "Core Infrastructure"}],
        ["Person", ALICE, "leads", "Project", {"name": "Project Horizon"}],
    ],
}


def test_decision_page_by_code_assembles_lineage_timeline_impact_and_trace():
    trace_patch, calls = stub_trace(DECISION_CANNED)
    codes_patch, health_patch = common_patches("app.brain.lineage")
    with trace_patch, codes_patch, health_patch:
        res = client.get("/decisions/dec-02")
    assert res.status_code == 200
    d = res.json()

    assert d["id"] == "d_mid" and d["decision_code"] == "DEC-02"
    assert "resolve" not in calls  # a DEC code resolves from the code map, no query needed
    assert [(p["name"], p["departed"]) for p in d["deciders"]] == [
        ("Alice Vance", False),
        ("Marcus Aurelius", True),
    ]
    assert d["decided_by"] == "Alice Vance, Marcus Aurelius"
    assert [x["decision_code"] for x in d["lineage"]["supersedes"]] == ["DEC-01"]
    assert [x["decision_code"] for x in d["lineage"]["superseded_by"]] == ["DEC-03"]
    assert [x["decision_code"] for x in d["lineage"]["contradicted_by"]] == ["DEC-04"]
    assert d["lineage"]["contradicts"] == []
    assert [x["decision_code"] for x in d["timeline"]] == ["DEC-01", "DEC-02", "DEC-03"]
    assert d["sources"] == [
        {"type": "ticket", "id": "TICK-1", "title": "Latency", "date": "2026-03-01", "quote": "Alice decided: mid."}
    ]
    assert d["impact"]["teams"] == ["Core Infrastructure"]
    assert d["impact"]["projects"] == ["Project Horizon"]
    assert d["supersedes"] == ["Old"] and d["superseded_by"] == ["New"]

    node_ids = {n["id"] for n in d["subgraph"]["nodes"]}
    assert {"Decision:d_mid", "Decision:d_old", "Ticket:TICK-1", "Meeting:Kickoff", "Team:Core Infrastructure"} <= node_ids
    assert len(node_ids) == len(d["subgraph"]["nodes"])  # deduplicated
    assert {"source": "Decision:d_rival", "target": "Decision:d_mid", "type": "contradicts", "properties": {}} in d["subgraph"]["edges"]
    mid = next(n for n in d["subgraph"]["nodes"] if n["id"] == "Decision:d_mid")
    assert mid["properties"]["decision_code"] == "DEC-02" and mid["properties"]["health"] == "superseded"

    assert [q["name"] for q in d["cypher"]["queries"]] == calls
    assert all(q["query"].startswith("MATCH") for q in d["cypher"]["queries"])
    assert d["cypher"]["total_ms"] == float(len(calls))


def test_decision_page_hides_per_source_quote_when_several_sources():
    canned = dict(DECISION_CANNED)
    canned["sources"] = [
        ["d_mid", "Ticket", {"ticket_id": "TICK-1", "title": "A"}],
        ["d_mid", "Meeting", {"title": "Sync", "date": "2026-03-01"}],
    ]
    trace_patch, _ = stub_trace(canned)
    codes_patch, health_patch = common_patches("app.brain.lineage")
    with trace_patch, codes_patch, health_patch:
        d = client.get("/decisions/DEC-02").json()
    assert [s["quote"] for s in d["sources"]] == [None, None]
    assert d["evidence_quote"] == "Alice decided: mid."


def test_decision_page_404_for_unknown_code_and_title():
    trace_patch, _ = stub_trace({"resolve": []})
    codes_patch, health_patch = common_patches("app.brain.lineage")
    with trace_patch, codes_patch, health_patch:
        assert client.get("/decisions/DEC-77").status_code == 404
        assert client.get("/decisions/no-such-title").status_code == 404


SYSTEM_ROWS = [
    ["Elasticsearch", "search", "Elastic", [MARCUS], 0, 4],
    ["Redis", "cache", "Redis Ltd", [ALICE], 2, 9],
]


def test_list_systems_flags_orphaned_and_sorts_them_first():
    trace_patch, _ = stub_trace(
        {"systems": SYSTEM_ROWS, "system_teams": [["Redis", ["Core Infrastructure"]]]}
    )
    orphans = {"Elasticsearch": SystemOrphanInfo(system="Elasticsearch", owner="Marcus Aurelius")}
    with trace_patch, patch("app.api.systems.evaluate_system_orphans", new=AsyncMock(return_value=orphans)):
        items = client.get("/systems").json()
    assert [s["name"] for s in items] == ["Elasticsearch", "Redis"]
    es, redis = items
    assert es["orphaned"] is True and es["owner"]["departed"] is True
    assert redis["orphaned"] is False and redis["teams"] == ["Core Infrastructure"]
    assert redis["decision_count"] == 2 and redis["ticket_count"] == 9


def test_system_detail_merges_people_roles_and_timeline():
    trace_patch, _ = stub_trace(
        {
            "systems": [SYSTEM_ROWS[1]],
            "system_teams": [],
            "system_decisions": [
                ["d_old", "Old", "2026-01-01", ["Alice Vance"], ["Redis"]],
                ["d_mid", "Mid", "2026-03-01", ["Alice Vance"], ["Redis"]],
            ],
            "system_people": [
                [
                    [ALICE],
                    [ALICE],
                    [
                        ["Bob Martin", "SRE", True, "", "TICK-1"],
                        ["Bob Martin", "SRE", True, "", "TICK-2"],
                        ["Alice Vance", "Engineer", True, "", "TICK-1"],
                    ],
                ]
            ],
        }
    )
    codes_patch, health_patch = common_patches("app.api.systems")
    with (
        trace_patch,
        codes_patch,
        health_patch,
        patch("app.api.systems.evaluate_system_orphans", new=AsyncMock(return_value={})),
    ):
        s = client.get("/systems/redis").json()
    assert s["name"] == "Redis" and s["orphaned"] is False
    assert [d["decision_code"] for d in s["decisions"]] == ["DEC-01", "DEC-02"]
    assert s["decisions"][0]["health"] == "superseded"
    people = {p["name"]: p for p in s["people"]}
    assert people["Alice Vance"]["roles"] == ["owner", "decider", "tickets"]
    assert people["Bob Martin"]["roles"] == ["tickets"] and people["Bob Martin"]["ticket_count"] == 2
    assert [p["name"] for p in s["people"]][0] == "Alice Vance"  # owner first
    assert len(s["cypher"]["queries"]) == 4


def test_system_detail_404():
    trace_patch, _ = stub_trace({"systems": [], "system_teams": []})
    with trace_patch, patch("app.api.systems.evaluate_system_orphans", new=AsyncMock(return_value={})):
        assert client.get("/systems/Nope").status_code == 404


PEOPLE_ROWS = [
    [{"name": "Marcus Aurelius", "role": "Architect", "is_active": False, "leave_date": "2025-11-30"}, ["Core Infrastructure"], ["Elasticsearch"], 0],
    [{"name": "Alice Vance", "role": "Engineer", "is_active": True, "leave_date": ""}, ["Core Infrastructure"], ["Kafka", "Redis"], 3],
]


def test_list_people_sorted_by_decisions_with_departed_flag():
    trace_patch, _ = stub_trace({"people": PEOPLE_ROWS})
    with trace_patch:
        people = client.get("/people").json()
    assert [p["name"] for p in people] == ["Alice Vance", "Marcus Aurelius"]
    assert people[1]["departed"] is True and people[1]["systems_owned"] == ["Elasticsearch"]


def test_person_detail_marks_owned_systems_orphaned_when_departed():
    trace_patch, _ = stub_trace(
        {
            "person": [PEOPLE_ROWS[0]],
            "person_decisions": [],
            "person_activity": [[[], [], 2, 1, 4]],
        }
    )
    codes_patch, health_patch = common_patches("app.api.people")
    with trace_patch, codes_patch, health_patch:
        p = client.get("/people/marcus aurelius").json()
    assert p["departed"] is True and p["leave_date"] == "2025-11-30"
    assert p["owned"] == [{"name": "Elasticsearch", "orphaned": True}]
    assert (p["tickets_raised"], p["tickets_assigned"], p["meetings_attended"]) == (2, 1, 4)


def test_person_detail_lists_decisions_and_leadership():
    trace_patch, _ = stub_trace(
        {
            "person": [PEOPLE_ROWS[1]],
            "person_decisions": [["d_old", "Old", "2026-01-01", ["Alice Vance"], ["Redis"]]],
            "person_activity": [[["Core Infrastructure"], ["Project Horizon"], 11, 8, 6]],
        }
    )
    codes_patch, health_patch = common_patches("app.api.people")
    with trace_patch, codes_patch, health_patch:
        p = client.get("/people/Alice Vance").json()
    assert [d["decision_code"] for d in p["decisions"]] == ["DEC-01"]
    assert p["teams_led"] == ["Core Infrastructure"] and p["projects_led"] == ["Project Horizon"]
    assert p["owned"] == [{"name": "Kafka", "orphaned": False}, {"name": "Redis", "orphaned": False}]


def test_person_detail_404():
    trace_patch, _ = stub_trace({"person": []})
    with trace_patch:
        assert client.get("/people/Nobody").status_code == 404


@pytest.mark.parametrize(
    "active,leave,expected",
    [(False, "", True), ("False", "", True), (True, "2025-11-30", True), (True, "2099-01-01", False), (True, "", False), (None, None, False)],
)
def test_is_departed(active, leave, expected):
    assert is_departed(active, leave, "2026-10-16") is expected


@pytest.mark.asyncio
async def test_evaluate_system_orphans_maps_rows():
    from app.brain import health

    rows = [["Elasticsearch", "Marcus Aurelius", "2025-11-30"]]
    with patch.object(health, "query_graph", new=AsyncMock(return_value=rows)) as q:
        out = await health.evaluate_system_orphans("ds", reference_date="2026-10-16")
    assert out["Elasticsearch"].owner == "Marcus Aurelius"
    assert q.call_args.kwargs["params"] == {"today": "2026-10-16"}
    assert "[:owns]" in q.call_args.args[0]
