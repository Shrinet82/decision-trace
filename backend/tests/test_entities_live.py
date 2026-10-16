"""Read-only checks of the decision/system/people endpoints against the live FalkorDB graph.

These run the real Cypher (variable-length paths, multi-type patterns) that the unit tests stub.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

has_credentials = bool(get_settings().FALKORDB_HOST)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not has_credentials, reason="Requires FalkorDB credentials."),
]
client = TestClient(app)


def _by_title(fragment: str) -> dict:
    items = client.get("/decisions").json()
    return next(d for d in items if d["title"].startswith(fragment))


def test_keycloak_session_decision_lineage():
    keycloak = _by_title("Migrate session storage to embedded Keycloak")
    redis = _by_title("Migrate session storage from Postgres to Redis")
    d = client.get(f"/decisions/{keycloak['decision_code']}").json()
    assert [x["id"] for x in d["lineage"]["supersedes"]] == [redis["id"]]
    assert keycloak["id"] in [x["id"] for x in d["timeline"]]
    assert d["sources"] and d["sources"][0]["id"] == "TICK-102"
    assert len(d["cypher"]["queries"]) >= 8

    back = client.get(f"/decisions/{redis['decision_code']}").json()
    assert [x["id"] for x in back["lineage"]["superseded_by"]] == [keycloak["id"]]


def test_kafka_is_contradicted_by_rabbitmq():
    kafka = _by_title("Adopt Kafka")
    rabbit = _by_title("Adopt RabbitMQ")
    d = client.get(f"/decisions/{kafka['decision_code']}").json()
    assert [x["id"] for x in d["lineage"]["contradicted_by"]] == [rabbit["id"]]
    assert any(e["type"] == "contradicts" for e in d["subgraph"]["edges"])


def test_elasticsearch_is_the_orphaned_system():
    systems = client.get("/systems").json()
    assert [s["name"] for s in systems if s["orphaned"]] == ["Elasticsearch"]
    es = client.get("/systems/Elasticsearch").json()
    assert es["owner"]["name"] == "Marcus Aurelius" and es["owner"]["departed"] is True


def test_people_pages():
    alice = client.get("/people/Alice Vance").json()
    assert alice["decision_count"] == len(alice["decisions"]) >= 1
    marcus = client.get("/people/Marcus Aurelius").json()
    assert marcus["departed"] is True
    assert marcus["owned"] == [{"name": "Elasticsearch", "orphaned": True}]
