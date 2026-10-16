"""Unit and integration tests for Decision Health Engine in app.brain.health."""

import pytest

from app.brain.health import evaluate_graph_health
from app.brain.memory import query_graph, reset
from app.config import get_settings

has_credentials = bool(
    get_settings().FALKORDB_HOST and get_settings().LLM_API_KEY.get_secret_value()
)


@pytest.mark.skipif(not has_credentials, reason="Requires FalkorDB credentials.")
@pytest.mark.asyncio
async def test_health_rules_on_hand_built_graph():
    """Unit-test each decision health rule on a small, hand-built synthetic graph topology."""
    test_ds = "test_health_hand_built_ds"
    try:
        await reset(dataset_name=test_ds)

        # Build hand-crafted graph topology directly via Cypher
        # 1. People
        await query_graph(
            "CREATE (:Person {name: 'Alice Vance', is_active: true, leave_date: ''}) "
            "CREATE (:Person {name: 'Bob Martin', is_active: true, leave_date: ''}) "
            "CREATE (:Person {name: 'Marcus Aurelius', is_active: false, leave_date: '2025-11-30'})",
            dataset_name=test_ds,
        )

        # 2. Systems with owners
        await query_graph(
            "MATCH (a:Person {name: 'Alice Vance'}), (m:Person {name: 'Marcus Aurelius'}) "
            "CREATE (s_pg:System {name: 'Postgres'}) "
            "CREATE (s_redis:System {name: 'Redis'}) "
            "CREATE (s_kafka:System {name: 'Kafka'}) "
            "CREATE (s_es:System {name: 'Elasticsearch'}) "
            "CREATE (a)-[:owns]->(s_pg) "
            "CREATE (a)-[:owns]->(s_redis) "
            "CREATE (a)-[:owns]->(s_kafka) "
            "CREATE (m)-[:owns]->(s_es)",
            dataset_name=test_ds,
        )

        # 3. Decisions
        # d1: Active decision
        # d2: Superseded decision (superseded by d3)
        # d3: Active decision that supersedes d2
        # d4: Contradicted decision (contradicted by d5)
        # d5: Contradicting decision
        # d6: Possibly stale decision (decided by Marcus Aurelius, who has left)
        # d8: Superseded decision also decided by Marcus (stays superseded; decider_departed is True)
        # d9: Active decision (by Alice) that supersedes d8
        # d7: Possibly stale decision (decision older than 180 days with no newer update)
        await query_graph(
            "MATCH (a:Person {name: 'Alice Vance'}), (b:Person {name: 'Bob Martin'}), "
            "      (m:Person {name: 'Marcus Aurelius'}), "
            "      (s_pg:System {name: 'Postgres'}), (s_redis:System {name: 'Redis'}), "
            "      (s_kafka:System {name: 'Kafka'}), (s_es:System {name: 'Elasticsearch'}) "
            "CREATE (d1:Decision {id: 'd1', title: 'Adopt Postgres 16', decided_on: '2026-08-01'}) "
            "CREATE (d2:Decision {id: 'd2', title: 'Use Redis for sessions', decided_on: '2026-02-01'}) "
            "CREATE (d3:Decision {id: 'd3', title: 'Use Keycloak for sessions', decided_on: '2026-05-01'}) "
            "CREATE (d4:Decision {id: 'd4', title: 'Use Kafka for messaging', decided_on: '2026-03-01'}) "
            "CREATE (d5:Decision {id: 'd5', title: 'Use RabbitMQ for messaging', decided_on: '2026-03-10'}) "
            "CREATE (d6:Decision {id: 'd6', title: 'Use Elasticsearch for log indexing', decided_on: '2026-06-01'}) "
            "CREATE (d7:Decision {id: 'd7', title: 'Use Legacy Auth', decided_on: '2025-01-01'}) "
            "CREATE (d8:Decision {id: 'd8', title: 'Old Elasticsearch plan', decided_on: '2026-04-01'}) "
            "CREATE (d9:Decision {id: 'd9', title: 'New Elasticsearch plan', decided_on: '2026-07-01'}) "
            # Edges
            "CREATE (d1)-[:about_system]->(s_pg) "
            "CREATE (d1)-[:decided_by]->(a) "
            "CREATE (d2)-[:about_system]->(s_redis) "
            "CREATE (d2)-[:decided_by]->(a) "
            "CREATE (d3)-[:about_system]->(s_redis) "
            "CREATE (d3)-[:decided_by]->(a) "
            "CREATE (d3)-[:supersedes]->(d2) "
            "CREATE (d4)-[:about_system]->(s_kafka) "
            "CREATE (d4)-[:decided_by]->(a) "
            "CREATE (d5)-[:about_system]->(s_kafka) "
            "CREATE (d5)-[:decided_by]->(b) "
            "CREATE (d5)-[:contradicts]->(d4) "
            "CREATE (d6)-[:about_system]->(s_es) "
            "CREATE (d6)-[:decided_by]->(m) "
            "CREATE (d8)-[:about_system]->(s_es) "
            "CREATE (d8)-[:decided_by]->(m) "
            "CREATE (d9)-[:about_system]->(s_es) "
            "CREATE (d9)-[:decided_by]->(a) "
            "CREATE (d9)-[:supersedes]->(d8)",
            dataset_name=test_ds,
        )

        health_map = await evaluate_graph_health(
            dataset_name=test_ds,
            stale_days=180,
            reference_date="2026-10-01",
        )

        # Verify d1 is ACTIVE
        assert "d1" in health_map
        assert health_map["d1"].status == "active"

        # Verify d2 is SUPERSEDED
        assert "d2" in health_map
        assert health_map["d2"].status == "superseded"
        assert "Keycloak" in health_map["d2"].reason

        # Verify d3 is ACTIVE (it supersedes d2, but is not itself superseded)
        assert "d3" in health_map
        assert health_map["d3"].status == "active"

        # Verify d4 is CONTRADICTED (by d5)
        assert "d4" in health_map
        assert health_map["d4"].status == "contradicted"
        assert "RabbitMQ" in health_map["d4"].reason

        # Verify d5 is CONTRADICTED (by d4)
        assert "d5" in health_map
        assert health_map["d5"].status == "contradicted"

        # Verify d6 is POSSIBLY STALE (its decider Marcus Aurelius departed)
        assert "d6" in health_map
        assert health_map["d6"].status == "possibly_stale"
        assert "Marcus Aurelius" in health_map["d6"].reason
        assert health_map["d6"].decider_departed is True

        # Superseded beats stale, but the departed decider is still reported
        assert health_map["d8"].status == "superseded"
        assert health_map["d8"].decider_departed is True
        assert health_map["d9"].status == "active"
        assert health_map["d9"].decider_departed is False

        # A departed SYSTEM OWNER alone no longer makes a decision stale
        assert health_map["d1"].decider_departed is False

        # Verify d7 is POSSIBLY STALE (decision older than 180 days)
        assert "d7" in health_map
        assert health_map["d7"].status == "possibly_stale"
        assert "older than 180 days" in health_map["d7"].reason

    finally:
        await reset(dataset_name=test_ds)
