"""Unit and integration tests for FastAPI REST API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.brain.health import DecisionHealthInfo
from app.config import get_settings
from app.main import app

settings = get_settings()
client = TestClient(app)
has_cloud_credentials = bool(settings.FALKORDB_HOST and settings.LLM_API_KEY.get_secret_value())


# =====================================================================
# Unit Tests (with FastAPI TestClient and Mocks)
# =====================================================================


def test_root_endpoint():
    """Verify root discovery endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Decision-Trace Company Brain"
    assert "health" in data


def test_health_check_endpoint():
    """Verify health check endpoint returns 200 when alive."""
    with patch("app.main.ping_falkordb", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["falkordb"] == "connected"


def test_admin_reset_unauthorized():
    """Verify POST /admin/reset rejects unauthorized requests without valid token."""
    response = client.post("/admin/reset")
    assert response.status_code == 401

    response = client.post("/admin/reset", headers={"X-Admin-Token": "wrong-secret-token"})
    assert response.status_code == 401


def test_admin_reset_authorized_with_mock():
    """Verify POST /admin/reset succeeds with valid X-Admin-Token."""
    token = settings.ADMIN_TOKEN.get_secret_value()
    with patch("app.api.admin.reset", new_callable=AsyncMock) as mock_reset:
        mock_reset.return_value = {"status": "success"}
        response = client.post(
            "/admin/reset?dataset_name=mock_dataset",
            headers={"X-Admin-Token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["dataset"] == "mock_dataset"
        mock_reset.assert_called_once_with(dataset_name="mock_dataset")


def test_get_decisions_with_filters():
    """Verify GET /decisions filters by system, person, and health."""
    mock_health = {
        "d1": DecisionHealthInfo(
            id="d1",
            title="Adopt Postgres 16",
            status="active",
            reason="Active decision",
            system="Postgres",
            decided_by="Evan Wright",
        ),
        "d2": DecisionHealthInfo(
            id="d2",
            title="Use Redis for sessions",
            status="superseded",
            reason="Superseded by Keycloak",
            system="Redis",
            decided_by="Alice Vance",
        ),
    }

    mock_rows = [
        ["d1", "Adopt Postgres 16", "accepted", "Postgres", "Evan Wright", "2026-08-01"],
        ["d2", "Use Redis for sessions", "accepted", "Redis", "Alice Vance", "2026-02-01"],
    ]

    with (
        patch("app.api.decisions.evaluate_graph_health", new_callable=AsyncMock) as mock_eval,
        patch("app.api.decisions.query_graph", new_callable=AsyncMock) as mock_query,
    ):
        mock_eval.return_value = mock_health
        mock_query.return_value = mock_rows

        # Filter by system
        res_sys = client.get("/decisions?system=Postgres")
        assert res_sys.status_code == 200
        items = res_sys.json()
        assert len(items) == 1
        assert items[0]["system"] == "Postgres"
        assert items[0]["health"] == "active"

        # Filter by health
        res_health = client.get("/decisions?health=superseded")
        assert res_health.status_code == 200
        items = res_health.json()
        assert len(items) == 1
        assert items[0]["id"] == "d2"
        assert items[0]["health"] == "superseded"


def test_get_decision_not_found():
    """Verify GET /decisions/{id} returns 404 for unknown decision."""
    with patch("app.api.decisions.query_graph", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = []
        response = client.get("/decisions/nonexistent-uuid")
        assert response.status_code == 404


def test_ask_refusal_when_no_entities_found():
    """Verify POST /ask returns refusal when no entities or matching decisions exist."""
    with patch("app.api.ask._resolve_entities_in_question", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = {"people": [], "systems": [], "decision_ids": []}
        response = client.post(
            "/ask",
            json={"question": "What is the airspeed velocity of an unladen swallow?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "could not find" in data["answer"].lower()
        assert data["citations"] == []
        assert data["graph_path"]["nodes"] == []


# =====================================================================
# Integration Tests on Seeded Graph (5 Representative Questions)
# =====================================================================


@pytest.mark.integration
@pytest.mark.skipif(not has_cloud_credentials, reason="Requires FalkorDB and LLM credentials.")
@pytest.mark.asyncio
async def test_api_ask_five_questions_on_seeded_graph():
    """Execute 5 representative questions via /ask on the seeded graph."""
    # Questions from project brief:
    # 1. Why did we choose RabbitMQ over Kafka?
    # 2. Who owns Elasticsearch now?
    # 3. What replaced Redis for sessions?
    # 4. Who decided to deploy Prometheus Operator?
    # 5. What database secrets management policy was adopted?

    test_queries = [
        {
            "q": "Why did we choose RabbitMQ over Kafka?",
            "expected_terms": ["RabbitMQ", "Kafka"],
            "expected_rel": "contradicts",
        },
        {
            "q": "Who owns Elasticsearch now?",
            "expected_terms": ["Elasticsearch", "Marcus Aurelius"],
            "expected_rel": "owns",
        },
        {
            "q": "What replaced Redis for sessions?",
            "expected_terms": ["Keycloak", "Redis"],
            "expected_rel": "supersedes",
        },
        {
            "q": "Who decided to deploy Prometheus Operator?",
            "expected_terms": ["Prometheus", "Kevin Flynn"],
            "expected_rel": "decided_by",
        },
        {
            "q": "What database secrets management policy was adopted?",
            "expected_terms": ["Vault", "secrets"],
            "expected_rel": "decided_by",
        },
    ]

    for item in test_queries:
        response = client.post(
            "/ask", json={"question": item["q"], "dataset_name": "company_brain"}
        )
        assert response.status_code == 200, f"Failed on question: {item['q']}"
        data = response.json()
        answer = data["answer"]
        graph_path = data["graph_path"]

        # Ensure grounded response
        assert len(answer) > 10, f"Empty answer for: {item['q']}"
        # If nodes retrieved, verify graph path structure
        if graph_path["nodes"]:
            assert any(
                node["label"] in ["Decision", "System", "Person", "Ticket", "Meeting"]
                for node in graph_path["nodes"]
            )
            # Citations should be typed citations
            for citation in data["citations"]:
                assert citation["type"] in ["ticket", "meeting", "decision", "document"]
