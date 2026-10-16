"""Holdout 2 Dataset Extraction & Scoring Script (Anti-Overfitting Validation).

Evaluates the 8 holdout 2 documents (4 tickets, 4 meeting notes) against data/HOLDOUT2_TRUTH.md.
Ground truth contains 5 expected decisions and 3 negative documents (expecting 0 decisions).
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

logger = logging.getLogger("decision_trace.scripts.evaluate_holdout2")

HOLDOUT2_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "holdout2"
HOLDOUT2_TICKETS = HOLDOUT2_DATA_DIR / "tickets.csv"
HOLDOUT2_NOTES = HOLDOUT2_DATA_DIR / "meeting_notes"

# Ground truth expectations from data/HOLDOUT2_TRUTH.md
EXPECTED_HOLDOUT2 = [
    {
        "id": "H201",
        "title": "Adopt OpenTelemetry for distributed tracing across all microservices",
        "source": "TICK-H201",
        "decider": "Alice Vance",
        "system": "OpenTelemetry",
        "status": "accepted",
    },
    {
        "id": "H202",
        "title": "Upgrade Elasticsearch cluster to version 8.13 across all logging nodes",
        "source": "TICK-H202",
        "decider": "Carlos Mendez",
        "system": "Elasticsearch",
        "status": "accepted",
    },
    {
        "id": "H203",
        "title": "Reduce TCP keepalive probe timeout to 60 seconds on egress gateways",
        "source": "TICK-H203",
        "decider": "Dave Miller",
        "system": "Kubernetes",
        "status": "accepted",
    },
    {
        "id": "H204",
        "title": "Standardize on Envoy proxy as the unified ingress gateway for all public services",
        "source": "2026-11-05_gateway_standardization.md",
        "decider": "Laura Croft",
        "system": "Envoy",
        "status": "accepted",
    },
    {
        "id": "H205",
        "title": "Deprecate legacy Jenkins build agents in favor of GitHub Actions self-hosted runners",
        "source": "2026-11-12_ci_pipeline_sync.md",
        "decider": "Ian Malcolm",
        "system": "Jenkins",
        "status": "accepted",
    },
]


async def run_holdout2_evaluation(
    dataset_name: str = "holdout2_brain",
    bypass_cache: bool = False,
) -> dict[str, Any]:
    """Run extraction on holdout 2 documents and benchmark against ground truth."""
    active_model = os.getenv("LLM_MODEL", "bedrock/deepseek.v3.2")
    print("=" * 70)
    print(f"HOLDOUT 2 DATASET EVALUATION: '{dataset_name}'")
    print(f"ACTIVE LLM MODEL: {active_model}")
    print("=" * 70)

    # 1. Reset dataset
    await reset(dataset_name=dataset_name)
    await get_or_create_dataset_graph_name(dataset_name)

    # 2. Extract decisions from holdout 2 docs
    start_time = time.perf_counter()
    summary = await extract_all_decisions(
        dataset_name=dataset_name,
        tickets_path=HOLDOUT2_TICKETS,
        notes_dir=HOLDOUT2_NOTES,
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
    expected_titles = [e["title"] for e in EXPECTED_HOLDOUT2]
    matched_gt: set[str] = set()
    true_positives = 0
    decider_correct = 0

    print(f"\nExtracted {len(extracted_decisions)} decisions from 8 holdout 2 documents (5 GT, 3 negative):")
    for ext in extracted_decisions:
        sims = [
            compute_embedding_similarity(ext["title"], exp_title)
            for exp_title in expected_titles
        ]
        best_idx = int(max(range(len(sims)), key=lambda i: sims[i]))
        best_sim = sims[best_idx]
        best_gt = EXPECTED_HOLDOUT2[best_idx]

        is_match = best_sim >= 0.70
        if is_match and best_gt["id"] not in matched_gt:
            matched_gt.add(best_gt["id"])
            true_positives += 1
            if (
                ext["decided_by"]
                and (
                    ext["decided_by"].lower() in best_gt["decider"].lower()
                    or best_gt["decider"].lower() in ext["decided_by"].lower()
                )
            ):
                decider_correct += 1
            status_str = f"MATCH (sim={best_sim:.2f}) -> [{best_gt['id']}]"
        else:
            status_str = f"FP / extra (best sim={best_sim:.2f} with [{best_gt['id']}])"

        print(
            f"  * '{ext['title']}' | Decider: {ext['decided_by']} | System: {ext['system']} [{status_str}]"
        )

    total_gt = len(EXPECTED_HOLDOUT2)
    total_ext = len(extracted_decisions)
    recall = (true_positives / total_gt) * 100 if total_gt else 0.0
    precision = (true_positives / total_ext) * 100 if total_ext else 0.0
    f1 = (
        (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
    )

    print("\nHOLDOUT 2 SCORECARD:")
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
    asyncio.run(run_holdout2_evaluation())
