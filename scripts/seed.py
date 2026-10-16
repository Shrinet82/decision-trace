"""Seed Script: Rebuild the entire Company Brain graph from scratch.

Executes end-to-end:
1. Dataset reset (FalkorDB graph + Cognee relational metadata)
2. Memory baseline measurement
3. Deterministic SQL source ingestion (Teams, People, Projects, Systems, ownership/membership edges)
4. Deterministic Ticket source ingestion (Tickets, raised_by, assigned_to, mentions)
5. Deterministic Meeting Notes ingestion (Meetings, attended_by)
6. LLM Decision extraction (ticket comments, meeting bodies, linking based_on, supersedes, contradicts)
7. Final Decision reconciliation
8. FalkorDB memory telemetry, token usage, and runtime metrics report.
"""

import asyncio
import logging
import sys
import time
from typing import Any

from app.config import get_settings

_settings = get_settings()

from app.brain.memory import (
    get_falkordb_memory_usage,
    get_or_create_dataset_graph_name,
    query_graph,
    reset,
)
from app.brain.reconciliation import split_composite_nodes
from app.ingest.decisions_extractor import extract_all_decisions
from app.ingest.notes_source import ingest_notes_source
from app.ingest.sql_source import ingest_sql_source
from app.ingest.tickets_source import ingest_tickets_source

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("seed")
_settings = get_settings()


async def run_seed(
    dataset_name: str = "company_brain",
    bypass_cache: bool = False,
) -> dict[str, Any]:
    """Rebuild the entire graph from scratch end to end."""
    print("\n" + "=" * 65)
    print(f"COMPANY BRAIN SEED PIPELINE: DATASET '{dataset_name}'")
    print("=" * 65)

    pipeline_start = time.perf_counter()

    # Step 1: Reset dataset
    print("\n[1/6] Resetting knowledge graph...")
    await reset(dataset_name=dataset_name, delete_all_graphs=True)
    active_graph_uuid = await get_or_create_dataset_graph_name(dataset_name)
    print(f"  Initialized active Cognee dataset graph: {active_graph_uuid}")
    mem_baseline = await get_falkordb_memory_usage()
    print(
        f"  FalkorDB Memory Baseline: {mem_baseline.get('used_memory_human', 'N/A')} ({mem_baseline.get('used_memory')} bytes)"
    )

    # Step 2: Ingest SQL organizational hierarchy
    print("\n[2/6] Ingesting SQL organizational source (company.db)...")
    sql_start = time.perf_counter()
    sql_counts = await ingest_sql_source(dataset_name=dataset_name)
    sql_time = time.perf_counter() - sql_start
    mem_post_sql = await get_falkordb_memory_usage()
    print(f"  SQL Ingested in {sql_time:.2f}s: {sql_counts}")
    print(
        f"  FalkorDB Memory Post-SQL: {mem_post_sql.get('used_memory_human', 'N/A')} ({mem_post_sql.get('used_memory')} bytes)"
    )

    # Step 3: Ingest deterministic Tickets
    print("\n[3/6] Ingesting deterministic Tickets source (tickets.csv)...")
    t_start = time.perf_counter()
    ticket_counts = await ingest_tickets_source(dataset_name=dataset_name)
    t_time = time.perf_counter() - t_start
    print(f"  Tickets Ingested in {t_time:.2f}s: {ticket_counts}")

    # Step 4: Ingest deterministic Meeting Notes
    print("\n[4/6] Ingesting deterministic Meeting Notes source (meeting_notes/)...")
    n_start = time.perf_counter()
    notes_counts = await ingest_notes_source(dataset_name=dataset_name)
    n_time = time.perf_counter() - n_start
    mem_post_determ = await get_falkordb_memory_usage()
    print(f"  Meeting Notes Ingested in {n_time:.2f}s: {notes_counts}")
    print(
        f"  FalkorDB Memory Post-Deterministic: {mem_post_determ.get('used_memory_human', 'N/A')} ({mem_post_determ.get('used_memory')} bytes)"
    )

    # Step 5: LLM Decision Extraction & Reconciliation
    print(
        "\n[5/6] Running LLM Decision extraction on ticket comments & meeting bodies..."
    )
    dec_start = time.perf_counter()
    decision_summary = await extract_all_decisions(
        dataset_name=dataset_name,
        concurrency_limit=3,
        include_all_tickets=True,  # Ingests ALL 80 tickets without keyword pre-filter
        pause_between_calls=0.05,
        bypass_cache=bypass_cache,
    )
    dec_time = time.perf_counter() - dec_start
    print(f"  Decisions extracted in {dec_time:.2f}s")
    print(
        f"  Total tokens: {decision_summary['total_tokens']} (prompt: {decision_summary['prompt_tokens']}, comp: {decision_summary['completion_tokens']})"
    )
    print(f"  Estimated LLM cost: ${decision_summary['estimated_cost_usd']:.5f} USD")

    # Step 6: Normalize based_on edges & run memory post-ingestion
    try:
        await query_graph(
            "MATCH (d:Decision)-[:based_on_meeting]->(m:Meeting) MERGE (d)-[:based_on]->(m)",
            dataset_name=dataset_name,
        )
    except Exception as norm_err:  # noqa: BLE001
        logger.warning("Could not normalize based_on_meeting edges: %s", norm_err)

    # Defensive: collapse any list-valued Person/System nodes into one node per entity
    split_result = await split_composite_nodes(dataset_name=dataset_name)
    if split_result["split"]:
        print(f"  Split composite nodes: {[s['name'] for s in split_result['split']]}")

    print("\n[6/6] Final Graph Inventory & Telemetry...")
    mem_final = await get_falkordb_memory_usage()
    total_time = time.perf_counter() - pipeline_start

    # Query counts for all labels
    labels = ["Person", "Team", "Project", "System", "Ticket", "Meeting", "Decision"]
    counts_by_label: dict[str, int] = {}
    for lbl in labels:
        res = await query_graph(
            f"MATCH (n:{lbl}) RETURN count(n)", dataset_name=dataset_name
        )
        counts_by_label[lbl] = res[0][0] if res else 0

    # Query counts for key relationships
    rel_types = [
        "member_of",
        "owns",
        "leads",
        "raised_by",
        "assigned_to",
        "mentions",
        "attended_by",
        "decided_by",
        "about_system",
        "based_on",
        "supersedes",
        "contradicts",
    ]
    counts_by_rel: dict[str, int] = {}
    for rel in rel_types:
        res = await query_graph(
            f"MATCH ()-[r:{rel}]->() RETURN count(r)", dataset_name=dataset_name
        )
        counts_by_rel[rel] = res[0][0] if res else 0

    print("\n" + "=" * 65)
    print("COMPANY BRAIN SEED SUMMARY")
    print("=" * 65)
    print(f"Total Pipeline Runtime: {total_time:.2f} seconds")
    print(
        f"Total LLM Tokens: {decision_summary['total_tokens']} | Est Cost: ${decision_summary['estimated_cost_usd']:.5f}"
    )
    print(f"FalkorDB Memory Baseline: {mem_baseline.get('used_memory_human', 'N/A')}")
    print(f"FalkorDB Memory Post-SQL: {mem_post_sql.get('used_memory_human', 'N/A')}")
    print(
        f"FalkorDB Memory Post-Deterministic: {mem_post_determ.get('used_memory_human', 'N/A')}"
    )
    print(
        f"FalkorDB Memory Final: {mem_final.get('used_memory_human', 'N/A')} ({mem_final.get('used_memory')} bytes)"
    )
    print("\nNode Counts:")
    for lbl, cnt in counts_by_label.items():
        print(f"  - {lbl}: {cnt}")
    print("\nRelationship Counts:")
    for rel, cnt in counts_by_rel.items():
        print(f"  - {rel}: {cnt}")

    return {
        "dataset_name": dataset_name,
        "total_time_sec": round(total_time, 2),
        "memory_baseline": mem_baseline,
        "memory_post_sql": mem_post_sql,
        "memory_post_determ": mem_post_determ,
        "memory_final": mem_final,
        "nodes": counts_by_label,
        "relationships": counts_by_rel,
        "tokens": decision_summary,
    }


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "company_brain"
    asyncio.run(run_seed(target))
