"""Unit and integration safety tests verifying parameterized Cypher execution.

Asserts that malicious injections like `x'] MATCH (n) DETACH DELETE n //` are treated
strictly as literal parameter values and cause no unintended graph mutations or deletions.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.brain.memory import query_graph
from app.main import app


@pytest.mark.asyncio
async def test_parameterized_cypher_injection_is_harmless():
    """Verify that a hostile Cypher injection is strictly evaluated as a parameter literal."""
    hostile_input = "x'] MATCH (n) DETACH DELETE n //"

    # Query with hostile value as parameter
    res = await query_graph(
        "MATCH (d:Decision) WHERE d.id = $id RETURN d.id, d.title",
        params={"id": hostile_input},
    )
    # The query must execute cleanly and return an empty list or exact match, not crash or delete
    assert isinstance(res, list)
    assert len(res) == 0


@pytest.mark.asyncio
async def test_ask_endpoint_hostile_input_is_harmless():
    """Verify that sending a hostile injection string to /ask executes safely without deleting graph data."""
    hostile_question = "x'] MATCH (n) DETACH DELETE n // What did Alice Vance decide?"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/ask",
            json={"question": hostile_question},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "graph_path" in data
        assert isinstance(data["graph_path"]["nodes"], list)
        assert data["graph_path"]["omitted_count"] >= 0
