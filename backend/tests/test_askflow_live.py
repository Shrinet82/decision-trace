"""Read-only checks of the Ask intents against the live FalkorDB graph (and the LLM for /ask).

Run with: PYTHONPATH=backend pytest -m integration backend/tests/test_askflow_live.py
"""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.server import app

has_credentials = bool(get_settings().FALKORDB_HOST)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not has_credentials, reason="Requires FalkorDB credentials."),
]
client = TestClient(app)


def _codes() -> dict[str, str]:
    return {d["id"]: d["decision_code"] for d in client.get("/decisions").json()}


def _ask(question: str) -> dict:
    r = client.post("/ask", json={"question": question})
    assert r.status_code == 200, r.text
    return r.json()


def test_impact_snowflake_includes_dec_03_13_17():
    d = _ask("What's affected if we drop Snowflake?")
    assert d["intent"] == "impact"
    decisions = next(s for s in d["sections"] if s["key"] == "decisions")
    assert {"DEC-03", "DEC-13", "DEC-17"} <= {i["code"] for i in decisions["items"]}
    assert d["trace"]["queries"] and all(q["rows"] >= 0 for q in d["trace"]["queries"])


def test_expertise_kafka_top_results_include_alice():
    d = _ask("Who knows the most about Kafka?")
    assert d["intent"] == "expertise"
    assert "Alice Vance" in [e["name"] for e in d["experts"][:3]]


def test_keycloak_why_is_still_dec_11():
    d = _ask("Why did we move sessions to Keycloak?")
    assert _codes()[d["primary_decision_id"]] == "DEC-11"
    assert {c["id"] for c in d["citations"]} & {"TICK-102", "TICK-101"}


def test_unanswerable_is_empty():
    d = _ask("Why did we choose quantum encryption for database backups?")
    assert "not found" in d["answer"].lower()
    assert d["graph_path"]["nodes"] == [] and d["citations"] == [] and d["primary_decision_id"] is None


def test_sources_list_and_a_ticket():
    listing = client.get("/sources").json()
    assert listing["counts"]["ticket"] == 80 and listing["counts"]["meeting"] == 12
    doc = client.get("/sources/ticket/TICK-105").json()
    assert "Kafka" in doc["text"] and any(d["quote"] for d in doc["decisions"])
