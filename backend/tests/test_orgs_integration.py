"""Live end-to-end for organizations (FalkorDB Cloud + the LLM): create an org, upload two files,
see the decisions, ask about them, check the sample is untouched, delete the org and its graph.

Run with `pytest -m integration backend/tests/test_orgs_integration.py`. Skipped without credentials."""

import json

import pytest
from fastapi.testclient import TestClient

from app.brain.memory import list_falkordb_graphs
from app.config import get_settings
from app.orgs import registry
from app.server import app

settings = get_settings()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (settings.FALKORDB_HOST and settings.LLM_API_KEY.get_secret_value()),
        reason="needs FalkorDB and LLM credentials",
    ),
]

ADR_ONE = """# ADR-0001: Use PostgreSQL for the billing service

Date: 2026-03-02
Status: Accepted

## Context
The billing team needs transactions and strong consistency for invoices.

## Decision
Dana Whitfield decided: we use PostgreSQL for the billing service instead of MongoDB.

## Consequences
Invoices are stored relationally and migrations run through Flyway.
"""

NOTES = """# Platform sync

Date: 2026-04-10
Attendees: Dana Whitfield, Omar Haddad

Decision: Omar Haddad decided that all services will send logs to Loki and the old ELK stack is retired by June.
Dana agreed to own the Loki rollout.
"""


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return out


def test_create_upload_ask_delete():
    client = TestClient(app)
    sample_before = len(client.get("/decisions").json())
    org = client.post("/orgs", json={"name": "Integration Co"}).json()
    org_id = org["id"]
    headers = {"X-Org-Key": org["owner_key"]}
    graph = registry._orgs[org_id]["graph_name"]
    try:
        assert client.get(f"/orgs/{org_id}/decisions").json() == []

        # Without the owner key nothing can be added
        assert client.post(f"/orgs/{org_id}/ingest/batch", json={"files": [{"name": "a.md", "text": "We decided X."}]}).status_code == 403
        res = client.post(
            f"/orgs/{org_id}/ingest/batch",
            headers=headers,
            json={"files": [
                {"name": "adr-0001-postgres.md", "type": "auto", "text": ADR_ONE},
                {"name": "platform-sync.md", "type": "auto", "text": NOTES},
            ]},
        )
        assert res.status_code == 200
        events = _events(res.text)
        assert events[-1][0] == "diff", events[-1]
        plan = events[0][1]["files"]
        assert [f["type"] for f in plan] == ["adr", "meeting"]
        diff = events[-1][1]
        assert any(n["label"] == "Decision" for n in diff["nodes_added"])

        decisions = client.get(f"/orgs/{org_id}/decisions").json()
        assert len(decisions) >= 2
        assert all(d["decision_code"].startswith("DEC-") for d in decisions)
        assert {p["name"] for p in client.get(f"/orgs/{org_id}/people").json()} >= {"Dana Whitfield"}

        answer = client.post(f"/orgs/{org_id}/ask", json={"question": "Why did we choose PostgreSQL for billing?"}).json()
        assert "PostgreSQL" in answer["answer"] or "Postgres" in answer["answer"]
        assert answer["citations"], answer

        # The sample organization is untouched, and the org's data never shows up there
        assert len(client.get("/decisions").json()) == sample_before
        assert "Dana Whitfield" not in {p["name"] for p in client.get("/people").json()}
        # Nothing resets automatically inside a user organization
        assert client.get(f"/orgs/{org_id}/ingest/status").json()["has_demo_data"] is False
    finally:
        assert client.delete(f"/orgs/{org_id}", headers=headers).status_code == 200
    graphs = pytest.importorskip("asyncio").run(list_falkordb_graphs())
    assert graph not in graphs and f"{graph}__changes" not in graphs
