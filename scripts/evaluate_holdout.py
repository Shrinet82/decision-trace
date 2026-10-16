"""Holdout Dataset Extraction & Scoring Script.

Ingests the 6 hand-written holdout documents (3 tickets, 3 meeting notes) into a
clean holdout dataset, extracts decisions, and benchmarks results against data/HOLDOUT_TRUTH.md.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from app.brain.memory import get_or_create_dataset_graph_name, query_graph, reset
from app.brain.reconciliation import compute_embedding_similarity
from app.ingest.decisions_extractor import extract_all_decisions

logger = logging.getLogger("decision_trace.scripts.evaluate_holdout")

HOLDOUT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "holdout"
HOLDOUT_TICKETS = HOLDOUT_DATA_DIR / "tickets.csv"
HOLDOUT_NOTES = HOLDOUT_DATA_DIR / "meeting_notes"

# Ground truth expectations from data/HOLDOUT_TRUTH.md
EXPECTED_HOLDOUT = [
    {
        "id": "H01",
        "title": "Partition the audit_events table by month",
        "source": "TICK-H01",
        "decider": "Evan Wright",
        "system": "Postgres",
        "status": "accepted",
    },
    {
        "id": "H02",
        "title": "Increase preStop sleep hook to 45 seconds across ingress deployments",
        "source": "TICK-H02",
        "decider": "Bob Martin",
        "system": "Kubernetes",
        "status": "accepted",
    },
    {
        "id": "H03",
        "title": "Revert jemalloc background thread defragmentation in favor of rolling node restarts",
        "source": "TICK-H03",
        "decider": "Ian Malcolm",
        "system": "Redis",
        "status": "reverted",
    },
    {
        "id": "H04",
        "title": "Transition raw event logs older than 90 days to Glacier Flexible Archive",
        "source": "2026-09-15_data_retention_sync.md",
        "decider": "Carlos Mendez",
        "system": "Snowflake",
        "status": "accepted",
    },
    {
        "id": "H05",
        "title": "Select Cilium Service Mesh with eBPF for inter-service encryption without sidecars",
        "source": "2026-09-28_service_mesh_evaluation.md",
        "decider": "Alice Vance",
        "system": "Kubernetes",
        "status": "accepted",
    },
    {
        "id": "H06",
        "title": "Route all distributed session state through centralized Keycloak cache instead of in-memory pod caching",
        "source": "2026-10-02_cache_strategy_reversal.md",
        "decider": "Alice Vance",
        "system": "Keycloak",
        "status": "accepted",
    },
]


async def run_holdout_evaluation(
    dataset_name: str = "holdout_brain",
    bypass_cache: bool = False,
) -> dict[str, Any]:
    """Run extraction on holdout documents and benchmark against ground truth."""
    active_model = os.getenv("LLM_MODEL", "bedrock/deepseek.v3.2")
    print("=" * 70)
    print(f"HOLDOUT DATASET EVALUATION: '{dataset_name}'")
    print(f"ACTIVE LLM MODEL: {active_model}")
    print("=" * 70)

    # 1. Reset holdout dataset
    await reset(dataset_name=dataset_name)
    await get_or_create_dataset_graph_name(dataset_name)

    # 2. Extract decisions from holdout docs
    start_time = time.perf_counter()
    summary = await extract_all_decisions(
        dataset_name=dataset_name,
        tickets_path=HOLDOUT_TICKETS,
        notes_dir=HOLDOUT_NOTES,
        concurrency_limit=3,
        include_all_tickets=True,
        pause_between_calls=0.5,
        bypass_cache=bypass_cache,
    )
    elapsed = time.perf_counter() - start_time

    # 3. Fetch extracted decisions
    d_rows = await query_graph(
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:based_on]->(t:Ticket) "
        "OPTIONAL MATCH (d)-[:based_on]->(m:Meeting) "
        "RETURN d.id, d.title, s.name, p.name, coalesce(t.ticket_id, m.title, '')",
        dataset_name=dataset_name,
    )

    # One record per decision (the query returns a row per decider x system x source combination)
    grouped: dict[str, dict[str, Any]] = {}
    for r in d_rows:
        if not (r and r[0]):
            continue
        rec = grouped.setdefault(
            str(r[0]),
            {"id": str(r[0]), "title": str(r[1]) if r[1] else "", "systems": [], "deciders": [], "source": ""},
        )
        if r[2] and str(r[2]) not in rec["systems"]:
            rec["systems"].append(str(r[2]))
        if r[3] and str(r[3]) not in rec["deciders"]:
            rec["deciders"].append(str(r[3]))
        if r[4] and not rec["source"]:
            rec["source"] = str(r[4])
    extracted_decisions: list[dict[str, Any]] = [
        {**rec, "system": ", ".join(rec["systems"]), "decided_by": ", ".join(rec["deciders"])}
        for rec in grouped.values()
    ]

    # 4. Score match using embedding similarity (threshold 0.70)
    expected_titles = [e["title"] for e in EXPECTED_HOLDOUT]
    matched_gt: set[str] = set()
    true_positives = 0
    decider_correct = 0

    print(f"\nExtracted {len(extracted_decisions)} decisions from 6 holdout documents:")
    for ext in extracted_decisions:
        sims = [
            compute_embedding_similarity(ext["title"], exp_title)
            for exp_title in expected_titles
        ]
        best_idx = int(max(range(len(sims)), key=lambda i: sims[i]))
        best_sim = sims[best_idx]
        best_gt = EXPECTED_HOLDOUT[best_idx]

        is_match = best_sim >= 0.70
        if is_match and best_gt["id"] not in matched_gt:
            matched_gt.add(best_gt["id"])
            true_positives += 1
            # Check decider
            if (
                any(d.lower() in best_gt["decider"].lower() for d in ext["deciders"])
            ):
                decider_correct += 1
            status_str = f"MATCH (sim={best_sim:.2f}) -> [{best_gt['id']}]"
        else:
            status_str = f"FP / extra (best sim={best_sim:.2f} with [{best_gt['id']}])"

        print(
            f"  * '{ext['title']}' | Decider: {ext['decided_by']} | System: {ext['system']} [{status_str}]"
        )

    total_gt = len(EXPECTED_HOLDOUT)
    total_ext = len(extracted_decisions)
    recall = (true_positives / total_gt) * 100 if total_gt else 0.0
    precision = (true_positives / total_ext) * 100 if total_ext else 0.0
    f1 = (
        (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
    )

    print("\nHOLDOUT SCORECARD:")
    print(f"  - Ground Truth:  {total_gt}")
    print(f"  - Extracted:     {total_ext}")
    print(f"  - True Positives:{true_positives}")
    print(f"  - Recall:        {recall:.1f}% ({true_positives}/{total_gt})")
    print(f"  - Precision:     {precision:.1f}% ({true_positives}/{total_ext})")
    print(f"  - F1 Score:      {f1:.1f}%")
    print(
        f"  - Decider Acc:   {(decider_correct / true_positives * 100) if true_positives else 0.0:.1f}% ({decider_correct}/{true_positives})"
    )
    print(f"  - Total Tokens:  {summary['total_tokens']}")
    print(f"  - Est Cost:      ${summary['estimated_cost_usd']:.5f}")
    print(f"  - Total Time:    {elapsed:.2f}s")
    print("=" * 70)

    return {
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "true_positives": true_positives,
        "total_extracted": total_ext,
        "total_tokens": summary["total_tokens"],
        "cost_usd": summary["estimated_cost_usd"],
        "time_seconds": elapsed,
    }


if __name__ == "__main__":
    asyncio.run(run_holdout_evaluation())
