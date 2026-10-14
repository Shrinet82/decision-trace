"""End-to-End integration test against FalkorDB Cloud and Groq LLM.

Marked as 'integration' and conditionally executed only when valid
cloud credentials and RUN_INTEGRATION_TESTS=1 are present in the environment.
"""

import os

import pytest

from app.brain.memory import (
    ask,
    get_graph_engine,
    ingest_text,
    list_falkordb_graphs,
    query_graph,
    reset,
)
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


@pytest.mark.integration
@pytest.mark.skipif(
    not has_cloud_credentials,
    reason="Integration tests require FALKORDB_HOST and LLM_API_KEY credentials.",
)
@pytest.mark.asyncio
async def test_three_input_identity_and_supersedes():
    """Verify 3 inputs resolve exactly 3 decisions, zero stubs, and Keycloak supersedes Redis."""
    test_ds = "test_identity_3_inputs_ds"
    doc1 = (
        "Ticket ID: TICKET-842\n"
        "Title: Severe latency on Postgres session store under peak load\n"
        "Status: resolved\n"
        "Raised by: Dave Miller\n"
        "Mentions: Postgres, Redis\n"
        "Resolution note: After profiling connection exhaustion, Dave Miller decided: "
        "Migrate session storage from Postgres to Redis cluster to eliminate database connection pool contention. "
        "System: Redis."
    )
    doc2 = (
        "Meeting: Q3 Architecture Sync\n"
        "Date: 2026-08-15\n"
        "Attended by: Alice Chen, Dave Miller\n"
        "Notes: The team evaluated options for our analytics data pipeline. "
        "Alice Chen decided: Adopt ClickHouse for real-time analytics event processing. "
        "System: ClickHouse."
    )
    doc3 = (
        "Meeting: Architecture Review Update\n"
        "Date: 2026-09-20\n"
        "Attended by: Dave Miller, Alice Chen\n"
        "Notes: Given high operational maintenance of standalone Redis clusters, Dave Miller decided: "
        "Migrate session storage to embedded Keycloak cache. "
        "This decision supersedes Migrate session storage from Postgres to Redis cluster. "
        "System: Keycloak."
    )

    try:
        await reset(dataset_name=test_ds)
        await ingest_text(doc1, dataset_name=test_ds, run_cognify=True)
        await ingest_text(doc2, dataset_name=test_ds, run_cognify=True)
        await ingest_text(doc3, dataset_name=test_ds, run_cognify=True)
        from app.brain.reconciliation import reconcile_decisions

        await reconcile_decisions(dataset_name=test_ds)

        decisions = await query_graph("MATCH (d:Decision) RETURN d.title", dataset_name=test_ds)
        assert len(decisions) == 3, f"Expected exactly 3 decisions, got: {decisions}"

        supersedes = await query_graph(
            "MATCH (d1:Decision)-[r:supersedes]->(d2:Decision) RETURN d1.title, d2.title",
            dataset_name=test_ds,
        )
        assert len(supersedes) >= 1
        keycloak_supersedes_redis = any(
            "Keycloak" in str(r[0]) and "Redis" in str(r[1]) for r in supersedes
        )
        assert keycloak_supersedes_redis, (
            f"Expected Keycloak -> Redis supersedes, got: {supersedes}"
        )

    finally:
        await reset(dataset_name=test_ds)


@pytest.mark.integration
@pytest.mark.skipif(
    not has_cloud_credentials,
    reason="Integration tests require FALKORDB_HOST and LLM_API_KEY credentials.",
)
@pytest.mark.asyncio
async def test_contradicts_decisions():
    """Verify contradicting decisions about the same system by different people link via CONTRADICTS."""
    conflict_ds = "test_conflict_contradicts_ds"
    doc_kafka = (
        "Meeting: Core Infrastructure Review\n"
        "Date: 2026-10-01\n"
        "Attended by: Alice Chen, Bob Vance\n"
        "Notes: Alice Chen decided: Use Kafka for all event messaging across services. "
        "System: Kafka."
    )
    doc_rabbitmq = (
        "Meeting: Microservices Architecture Sync\n"
        "Date: 2026-10-05\n"
        "Attended by: Bob Vance, Alice Chen\n"
        "Notes: To simplify our cluster management, Bob Vance decided: Use RabbitMQ for all event messaging across services. "
        "This decision contradicts Use Kafka for all event messaging across services. "
        "System: Kafka."
    )

    try:
        await reset(dataset_name=conflict_ds)
        await ingest_text(doc_kafka, dataset_name=conflict_ds, run_cognify=True)
        await ingest_text(doc_rabbitmq, dataset_name=conflict_ds, run_cognify=True)

        contradicts = await query_graph(
            "MATCH (d1:Decision)-[r:contradicts]->(d2:Decision) "
            "OPTIONAL MATCH (d1)-[:decided_by]->(p1:Person) "
            "OPTIONAL MATCH (d2)-[:decided_by]->(p2:Person) "
            "RETURN d1.title, p1.name, d2.title, p2.name",
            dataset_name=conflict_ds,
        )
        assert len(contradicts) >= 1, f"Expected contradicts edge, got: {contradicts}"

    finally:
        await reset(dataset_name=conflict_ds)
