"""Live ingest end to end on an isolated copy of the graph (real FalkorDB and LLM).

GRAPH.COPY the configured graph into a throwaway graph, run preset (a) "standardise on Kafka"
and preset (b) "Alice Vance leaves", assert the diff, reset, and assert the copy is identical to
before. The source graph is only read. Both throwaway graphs are deleted afterwards.
"""

import hashlib
import json
import uuid

import pytest

from app.brain.memory import get_graph_engine, query_graph
from app.config import get_settings
from app.ingest.live import IngestRequest, changes_graph_name, list_changes, reset_demo, run_ingest

settings = get_settings()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (settings.FALKORDB_HOST and settings.FALKORDB_GRAPH_NAME),
        reason="Requires FalkorDB and LLM credentials.",
    ),
]

PRESET_KAFKA = IngestRequest(
    type="meeting",
    title="Architecture sync",
    date="2026-10-16",
    text=(
        "Architecture sync, 2026-10-16. Attendees: Alice Vance, Bob Martin, Kevin Flynn. Decision: we "
        "standardise on Kafka for all event messaging across services. RabbitMQ is retired; Bob agreed "
        "to migrate remaining queues by Q1. Owner: Alice Vance."
    ),
    participants=["Alice Vance", "Bob Martin", "Kevin Flynn"],
)
PRESET_ALICE = IngestRequest(
    type="announcement",
    title="People update: Alice Vance",
    date="2026-10-16",
    text=(
        "People update, 2026-10-16: Alice Vance has left the company effective today. Her "
        "responsibilities are pending reassignment."
    ),
)


async def fingerprint(dataset: str) -> tuple[int, int, str]:
    """Node/edge counts plus a hash of every label, property and relationship."""
    nodes = await query_graph("MATCH (n) RETURN labels(n)[0], properties(n)", dataset_name=dataset)
    edges = await query_graph(
        "MATCH (a)-[r]->(b) RETURN labels(a)[0], properties(a), type(r), properties(r), "
        "labels(b)[0], properties(b)",
        dataset_name=dataset,
    )

    def canon(rows):
        return "\n".join(sorted(json.dumps(r, sort_keys=True, default=str) for r in rows))

    digest = hashlib.sha256((canon(nodes) + "|" + canon(edges)).encode()).hexdigest()
    return len(nodes), len(edges), digest


async def run(req: IngestRequest, dataset: str) -> tuple[list[dict], dict]:
    events = [e async for e in run_ingest(req, dataset)]
    errors = [e for e in events if e["event"] == "error"]
    assert not errors, errors
    steps = [e["data"]["step"] for e in events if e["event"] == "step" and e["data"]["status"] == "done"]
    assert steps == ["reading", "extracting_decisions", "extracting_people", "matching", "linking", "writing", "health"]
    assert events[-1]["event"] == "diff"
    return events, events[-1]["data"]


@pytest.mark.asyncio
async def test_presets_change_health_then_reset_restores_graph_exactly():
    driver = (await get_graph_engine()).driver
    source = settings.FALKORDB_GRAPH_NAME
    test_graph = f"dt_ingest_test_{uuid.uuid4().hex[:6]}"
    driver.execute_command("GRAPH.COPY", source, test_graph)
    source_before = await fingerprint(source)
    try:
        before = await fingerprint(test_graph)
        assert before == source_before

        # (a) standardise on Kafka: a new decision supersedes RabbitMQ (DEC-07), resolving the conflict
        _, diff_a = await run(PRESET_KAFKA, test_graph)
        new_codes = [n["decision_code"] for n in diff_a["nodes_added"] if n["label"] == "Decision"]
        assert new_codes and all(code > "DEC-17" for code in new_codes)
        assert any(
            link["relation"] == "supersedes" and link["existing_code"] == "DEC-07" and link["new_code"] in new_codes
            for link in diff_a["links"]
        )
        # The judge must not mark the Kafka decision as superseded: the new one reaffirms it
        assert not any(link["relation"] == "supersedes" and link["existing_code"] == "DEC-04" for link in diff_a["links"])
        changes_a = {s["decision_code"]: (s["before"], s["after"]) for s in diff_a["status_changes"]}
        assert changes_a["DEC-07"] == ("contradicted", "superseded")
        assert changes_a["DEC-04"] == ("contradicted", "active")
        assert "conflict resolved" in diff_a["summary"]
        assert not any(n["label"] == "System" for n in diff_a["nodes_added"])  # no junk systems

        # (b) Alice Vance leaves: her live decisions go possibly_stale, her systems are orphaned
        _, diff_b = await run(PRESET_ALICE, test_graph)
        assert diff_b["person_changes"] == [
            {"name": "Alice Vance", "field": "departed", "before": False, "after": True}
        ]
        changes_b = {s["decision_code"]: (s["before"], s["after"]) for s in diff_b["status_changes"]}
        assert changes_b["DEC-04"] == ("active", "possibly_stale")
        assert changes_b["DEC-11"] == ("active", "possibly_stale")
        assert "DEC-01" not in changes_b  # superseded stays superseded
        assert {o["system"] for o in diff_b["orphan_changes"] if o["after"]} == {"Kafka", "Redis"}

        feed = await list_changes(test_graph)
        assert [c["kind"] for c in feed[:2]] == ["ingest", "ingest"]

        # Reset: only tagged data removed, Alice restored, graph identical to before
        result = await reset_demo(test_graph)
        assert result["restored_properties"] == 1
        assert (result["nodes"], result["edges"]) == before[:2]
        assert await fingerprint(test_graph) == before
        assert (await list_changes(test_graph))[0]["kind"] == "reset"
    finally:
        for graph in (test_graph, changes_graph_name(test_graph)):
            try:
                driver.execute_command("GRAPH.DELETE", graph)
            except Exception:  # noqa: BLE001
                pass
    assert await fingerprint(source) == source_before  # the source graph was never touched
