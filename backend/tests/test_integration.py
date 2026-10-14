"""End-to-End integration test against FalkorDB Cloud and Groq LLM.

Marked as 'integration' and conditionally executed only when valid
cloud credentials and RUN_INTEGRATION_TESTS=1 are present in the environment.
"""

import os

import pytest

from app.brain.memory import ask, get_graph_engine, ingest_text, list_falkordb_graphs, reset
from app.brain.models import CompanyBrainGraph
from app.config import get_settings

settings = get_settings()

has_cloud_credentials = bool(
    os.getenv("RUN_INTEGRATION_TESTS") == "1"
    or (
        settings.FALKORDB_HOST
        and settings.FALKORDB_PASSWORD.get_secret_value()
        and settings.LLM_API_KEY.get_secret_value()
    )
)


@pytest.mark.integration
@pytest.mark.skipif(
    not has_cloud_credentials,
    reason="Integration tests require FALKORDB_HOST and LLM_API_KEY credentials.",
)
@pytest.mark.asyncio
async def test_end_to_end_knowledge_flow():
    """Ingest synthetic text, extract graph via cognify, query, and verify cleanup."""
    isolated_dataset = "integration_test_dataset"

    # Synthetic sentence containing decision and decider
    synthetic_doc = (
        "Sarah is the Principal Platform Engineer at AcmeCorp. "
        "On October 10th, Sarah decided to adopt FalkorDB Cloud for GraphRAG "
        "because of its low-latency matrix-based OpenCypher graph engine."
    )

    try:
        # 1. Ingest and cognify
        ingest_res = await ingest_text(
            synthetic_doc, dataset_name=isolated_dataset, run_cognify=True
        )
        assert ingest_res["status"] == "success"

        # 2. Ask question and verify answer
        query_res = await ask("Who decided to adopt FalkorDB?", dataset_name=isolated_dataset)
        assert query_res is not None
        answer_text = query_res.get("answer", "")
        assert len(answer_text) > 0
        # Check that relevant context or decider was identified
        assert "Sarah" in answer_text or "Sarah" in str(query_res.get("raw_results", ""))

    finally:
        # 3. Cleanup / reset and verify FalkorDB GRAPH.LIST assertion
        remaining = await reset(dataset_name=isolated_dataset)
        graphs_after = await list_falkordb_graphs()
        assert isolated_dataset not in remaining
        assert isolated_dataset not in graphs_after


@pytest.mark.integration
@pytest.mark.skipif(
    not has_cloud_credentials,
    reason="Integration tests require FALKORDB_HOST and LLM_API_KEY credentials.",
)
@pytest.mark.asyncio
async def test_custom_extraction_and_reset_deletion():
    """Verify custom extraction creates Decision nodes and reset deletes FalkorDB graph."""
    isolated_dataset = "test_custom_extraction_dataset"

    doc = (
        "Ticket ID: TICKET-101\n"
        "Title: Session store latency\n"
        "Dave Miller decided: Migrate session storage from Postgres to Redis cluster. "
        "System: Redis."
    )

    try:
        # 1. Ingest with CompanyBrainGraph custom extraction
        res = await ingest_text(
            doc,
            dataset_name=isolated_dataset,
            run_cognify=True,
            graph_model=CompanyBrainGraph,
        )
        assert res["status"] == "success"

        # 2. Verify Decision and Person nodes exist in FalkorDB Cloud
        engine = await get_graph_engine()
        decisions = await engine.query("MATCH (d:Decision) RETURN d.title")
        assert len(decisions) >= 1

        decided_by = await engine.query(
            "MATCH (d:Decision)-[:decided_by]->(p:Person) RETURN d.title, p.name"
        )
        assert len(decided_by) >= 1
        assert any("Dave Miller" in str(row) for row in decided_by)

    finally:
        # 3. Reset and assert GRAPH.LIST confirms dataset graph is deleted
        remaining = await reset(dataset_name=isolated_dataset)
        graphs_after = await list_falkordb_graphs()
        assert isolated_dataset not in remaining
        assert isolated_dataset not in graphs_after


@pytest.mark.integration
@pytest.mark.skipif(
    not has_cloud_credentials,
    reason="Integration tests require FALKORDB_HOST and LLM_API_KEY credentials.",
)
@pytest.mark.asyncio
async def test_reset_safety_preserves_other_graphs():
    """Verify reset() with delete_all_graphs=False only deletes target dataset graph."""
    engine = await get_graph_engine()
    driver = getattr(engine, "driver", None)
    if not driver:
        pytest.skip("FalkorDB driver unavailable.")

    # Create dummy secondary graph
    secondary_graph = "keep_me_safe_graph"
    target_graph = "delete_me_target_graph"

    driver.execute_command("GRAPH.QUERY", secondary_graph, "CREATE (:System {name: 'SafeSystem'})")
    driver.execute_command("GRAPH.QUERY", target_graph, "CREATE (:System {name: 'TargetSystem'})")

    try:
        graphs_before = await list_falkordb_graphs()
        assert secondary_graph in graphs_before
        assert target_graph in graphs_before

        # Reset target only (delete_all_graphs defaults to False)
        remaining = await reset(dataset_name=target_graph, delete_all_graphs=False)
        assert target_graph not in remaining
        assert secondary_graph in remaining

    finally:
        # Clean up dummy test graphs
        driver.execute_command("GRAPH.DELETE", secondary_graph)
        try:
            driver.execute_command("GRAPH.DELETE", target_graph)
        except Exception:
            pass
