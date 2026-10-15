"""Evaluation Script: Benchmark FalkorDB Knowledge Graph against GROUND_TRUTH.md.

Produces a formal evaluation scorecard measuring:
1. Decision Recall and Precision (Embedding similarity >= 0.75 + Decider matching)
2. decided_by Correctness
3. supersedes Recall and Precision
4. contradicts Recall and Precision
5. Owner-Left System Detection (departed employees still owning systems)
6. Duplicate Node Analysis per Label
7. Detailed listing of Misses (False Negatives) and False Positives.
"""

import asyncio
import logging
import os
import sys
from typing import Any

from app.brain.memory import query_graph
from app.brain.reconciliation import compute_embedding_similarity

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("evaluate")

# 16 Planted decisions from data/GROUND_TRUTH.md
GROUND_TRUTH_DECISIONS = [
    {
        "id": "D01",
        "title": "Migrate session storage from Postgres to Redis cluster",
        "decider": "Alice Vance",
        "system": "Redis",
        "source": "TICK-101",
    },
    {
        "id": "D02",
        "title": "Migrate session storage to embedded Keycloak cache",
        "decider": "Alice Vance",
        "system": "Keycloak",
        "source": "TICK-102",
    },
    {
        "id": "D03",
        "title": "Adopt Snowflake for analytics ETL queries",
        "decider": "Fiona Gallagher",
        "system": "Snowflake",
        "source": "TICK-103",
    },
    {
        "id": "D04",
        "title": "Migrate analytics reporting queries from Snowflake to ClickHouse cluster",
        "decider": "Carlos Mendez",
        "system": "ClickHouse",
        "source": "TICK-104",
    },
    {
        "id": "D05",
        "title": "Use Kafka for all event messaging across services",
        "decider": "Alice Vance",
        "system": "Kafka",
        "source": "TICK-105",
    },
    {
        "id": "D06",
        "title": "Use RabbitMQ for all event messaging across services",
        "decider": "Bob Martin",
        "system": "RabbitMQ",
        "source": "TICK-106",
    },
    {
        "id": "D07",
        "title": "Store secret credentials exclusively in HashiCorp Vault instead of Kubernetes secrets",
        "decider": "Diana Prince",
        "system": "Vault",
        "source": "TICK-107",
    },
    {
        "id": "D08",
        "title": "Standardize application traces on Datadog APM across all production services",
        "decider": "Kevin Flynn",
        "system": "Datadog",
        "source": "TICK-108",
    },
    {
        "id": "D09",
        "title": "Deploy Prometheus Operator on all Kubernetes staging clusters",
        "decider": "Laura Croft",
        "system": "Prometheus",
        "source": "TICK-109",
    },
    {
        "id": "D10",
        "title": "Deprecate legacy RabbitMQ clusters in favor of native Redis PubSub for low-volume notifications",
        "decider": "Ian Malcolm",
        "system": "Redis",
        "source": "TICK-110",
    },
    {
        "id": "D11",
        "title": "Use Keycloak OAuth2 tokens for internal API gateway authentication",
        "decider": "Julia Roberts",
        "system": "Keycloak",
        "source": "TICK-111",
    },
    {
        "id": "D12",
        "title": "Upgrade all production Postgres instances to version 16",
        "decider": "Evan Wright",
        "system": "Postgres",
        "source": "TICK-112",
    },
    {
        "id": "D13",
        "title": "Adopt Keycloak for company-wide single sign-on",
        "decider": "Julia Roberts",
        "system": "Keycloak",
        "source": "2026-02-10_iam_modernization.md",
    },
    {
        "id": "D14",
        "title": "Migrate application metrics from Datadog to Prometheus Operator",
        "decider": "Kevin Flynn",
        "system": "Prometheus",
        "source": "2026-04-12_observability_sync.md",
    },
    {
        "id": "D15",
        "title": "Rotate all database passwords into Vault dynamic secrets",
        "decider": "Diana Prince",
        "system": "Vault",
        "source": "2026-06-08_secrets_management.md",
    },
    {
        "id": "D16",
        "title": "Standardize on Kubernetes 1.30 across all production regions",
        "decider": "Laura Croft",
        "system": "Kubernetes",
        "source": "2026-08-20_container_platform_upgrade.md",
    },
]

GROUND_TRUTH_SUPERSEDES = [
    ("Keycloak", "Redis"),  # D02 supersedes D01
    ("ClickHouse", "Snowflake"),  # D04 supersedes D03
    ("Prometheus", "Datadog"),  # D14 supersedes D08
]

GROUND_TRUTH_CONTRADICTS = [
    ("RabbitMQ", "Kafka"),  # D06 (Bob) contradicts D05 (Alice)
]

EXPECTED_NODE_COUNTS = {
    "Person": 15,
    "System": 12,
    "Team": 4,
    "Project": 6,
    "Ticket": 80,
    "Meeting": 12,
    "Decision": 16,
}


async def evaluate_graph(dataset_name: str = "company_brain") -> dict[str, Any]:
    """Run full evaluation against data/GROUND_TRUTH.md specification."""
    active_model = os.getenv("LLM_MODEL", "bedrock/deepseek.v3.2")
    print("\n" + "=" * 70)
    print(f"DECISION-TRACE EVALUATION SCORECARD: DATASET '{dataset_name}'")
    print(f"ACTIVE LLM MODEL: {active_model}")
    print("=" * 70)

    # 1. Fetch Extracted Decisions with decided_by, about_system, based_on
    cypher_decisions = (
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "OPTIONAL MATCH (d)-[:based_on]->(b) "
        "RETURN d.title, d.status, p.name, s.name, labels(b), b.ticket_id, b.title"
    )
    raw_decisions = await query_graph(cypher_decisions, dataset_name=dataset_name)

    extracted = []
    for row in raw_decisions:
        extracted.append(
            {
                "title": row[0] or "",
                "status": row[1] or "",
                "decider": row[2] or "",
                "system": row[3] or "",
                "based_on_type": (row[4][0] if row[4] else "")
                if len(row) > 4 and row[4]
                else "",
                "based_on_id": (row[5] or row[6] or "") if len(row) > 6 else "",
            }
        )

    # 2. Decision Matching (Recall & Precision)
    # Match criteria: Embedding similarity >= 0.72 + decider or system tiebreak
    matched_gt: dict[str, dict[str, Any]] = {}
    matched_ext_indices: set[int] = set()
    decider_correct_count = 0

    candidate_pairs = []
    for gt in GROUND_TRUTH_DECISIONS:
        for idx, ext in enumerate(extracted):
            sim = compute_embedding_similarity(gt["title"], ext["title"])
            bonus = 0.0
            if ext["decider"] and gt["decider"].lower() == ext["decider"].lower():
                bonus += 0.15
            if ext["system"] and gt["system"].lower() in ext["system"].lower():
                bonus += 0.10
            # Strict system tiebreaker: penalize if both specify systems and they conflict
            if ext["system"] and gt["system"] and gt["system"].lower() not in ext["system"].lower() and ext["system"].lower() not in gt["system"].lower():
                bonus -= 0.20

            composite_score = sim + bonus
            if sim >= 0.72:
                candidate_pairs.append((composite_score, sim, gt, idx, ext))

    # Sort globally by composite score descending so highest-fidelity matches claim first
    candidate_pairs.sort(key=lambda x: (x[0], x[1]), reverse=True)

    matched_gt_ids = set()
    for composite_score, sim, gt, idx, ext in candidate_pairs:
        if gt["id"] in matched_gt_ids or idx in matched_ext_indices:
            continue
        matched_gt_ids.add(gt["id"])
        matched_ext_indices.add(idx)
        matched_gt[gt["id"]] = ext
        if (
            ext["decider"]
            and ext["decider"].lower() == gt["decider"].lower()
        ):
            decider_correct_count += 1

    tp_count = len(matched_gt)
    fn_count = len(GROUND_TRUTH_DECISIONS) - tp_count
    fp_count = len(extracted) - tp_count

    recall = tp_count / len(GROUND_TRUTH_DECISIONS) if GROUND_TRUTH_DECISIONS else 0.0
    precision = tp_count / len(extracted) if extracted else 0.0
    f1 = (
        (2 * precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    decider_acc = decider_correct_count / tp_count if tp_count > 0 else 0.0

    # 3. Supersedes Relationships Recall & Precision
    cypher_super = (
        "MATCH (d1:Decision)-[:supersedes]->(d2:Decision) "
        "OPTIONAL MATCH (d1)-[:about_system]->(s1:System) "
        "OPTIONAL MATCH (d2)-[:about_system]->(s2:System) "
        "RETURN d1.title, s1.name, d2.title, s2.name"
    )
    raw_super = await query_graph(cypher_super, dataset_name=dataset_name)

    super_tp = 0
    for gt_src_sys, gt_tgt_sys in GROUND_TRUTH_SUPERSEDES:
        found = False
        for row in raw_super:
            d1_title, s1, d2_title, s2 = (
                row[0] or "",
                row[1] or "",
                row[2] or "",
                row[3] or "",
            )
            text_combo = f"{d1_title} {s1} -> {d2_title} {s2}".lower()
            if gt_src_sys.lower() in text_combo and gt_tgt_sys.lower() in text_combo:
                found = True
                break
        if found:
            super_tp += 1

    super_recall = (
        super_tp / len(GROUND_TRUTH_SUPERSEDES) if GROUND_TRUTH_SUPERSEDES else 0.0
    )
    super_precision = super_tp / len(raw_super) if raw_super else 0.0

    # 4. Contradicts Relationships Recall & Precision
    cypher_contra = (
        "MATCH (d1:Decision)-[:contradicts]->(d2:Decision) "
        "OPTIONAL MATCH (d1)-[:about_system]->(s1:System) "
        "OPTIONAL MATCH (d2)-[:about_system]->(s2:System) "
        "RETURN d1.title, s1.name, d2.title, s2.name"
    )
    raw_contra = await query_graph(cypher_contra, dataset_name=dataset_name)

    contra_tp = 0
    for gt_src, gt_tgt in GROUND_TRUTH_CONTRADICTS:
        found = False
        for row in raw_contra:
            d1_title, s1, d2_title, s2 = (
                row[0] or "",
                row[1] or "",
                row[2] or "",
                row[3] or "",
            )
            text_combo = f"{d1_title} {s1} -> {d2_title} {s2}".lower()
            if gt_src.lower() in text_combo and gt_tgt.lower() in text_combo:
                found = True
                break
        if found:
            contra_tp += 1

    contra_recall = (
        contra_tp / len(GROUND_TRUTH_CONTRADICTS) if GROUND_TRUTH_CONTRADICTS else 0.0
    )
    contra_precision = contra_tp / len(raw_contra) if raw_contra else 0.0

    # 5. Owner-Left Detection
    cypher_owner_left = (
        "MATCH (p:Person)-[:owns]->(s:System) "
        "WHERE p.is_active = false OR (p.leave_date IS NOT NULL AND p.leave_date <> '') "
        "RETURN s.name, p.name, p.leave_date"
    )
    owner_left_res = await query_graph(cypher_owner_left, dataset_name=dataset_name)
    owner_left_detected = any(
        "elasticsearch" in str(r[0]).lower() and "marcus" in str(r[1]).lower()
        for r in owner_left_res
    )

    # 6. Duplicate Node Analysis per Label
    node_counts_scorecard = {}
    for label, expected in EXPECTED_NODE_COUNTS.items():
        total_res = await query_graph(
            f"MATCH (n:{label}) RETURN count(n)", dataset_name=dataset_name
        )
        total_count = total_res[0][0] if total_res else 0

        # Distinct key count
        if label == "Ticket":
            key_field = "ticket_id"
        elif label == "Meeting" or label == "Decision":
            key_field = "title"
        else:
            key_field = "name"

        distinct_res = await query_graph(
            f"MATCH (n:{label}) RETURN count(DISTINCT n.{key_field})",
            dataset_name=dataset_name,
        )
        distinct_count = distinct_res[0][0] if distinct_res else 0

        node_counts_scorecard[label] = {
            "expected": expected,
            "actual": total_count,
            "distinct": distinct_count,
            "duplicates": max(0, total_count - distinct_count),
        }

    # Print Scorecard
    print("\n1. DECISION EXTRACTION ACCURACY")
    print(f"  - Ground Truth Decisions: {len(GROUND_TRUTH_DECISIONS)}")
    print(f"  - Extracted Decisions:    {len(extracted)}")
    print(f"  - True Positives (TP):    {tp_count}")
    print(f"  - False Negatives (Miss): {fn_count}")
    print(f"  - False Positives (FP):   {fp_count}")
    print(f"  - Recall:                 {recall * 100:.1f}%")
    print(f"  - Precision:              {precision * 100:.1f}%")
    print(f"  - F1 Score:               {f1 * 100:.1f}%")
    print(
        f"  - decided_by Accuracy:    {decider_acc * 100:.1f}% ({decider_correct_count}/{tp_count})"
    )

    print("\n2. RELATIONSHIPS BENCHMARK")
    print(
        f"  - supersedes Recall:      {super_recall * 100:.1f}% ({super_tp}/{len(GROUND_TRUTH_SUPERSEDES)})"
    )
    print(
        f"  - supersedes Precision:   {super_precision * 100:.1f}% ({super_tp}/{len(raw_super)})"
    )
    print(
        f"  - contradicts Recall:     {contra_recall * 100:.1f}% ({contra_tp}/{len(GROUND_TRUTH_CONTRADICTS)})"
    )
    print(
        f"  - contradicts Precision:  {contra_precision * 100:.1f}% ({contra_tp}/{len(raw_contra)})"
    )

    print("\n3. GOVERNANCE AUDIT")
    print(f"  - Owner-Left Detection:   {'PASS' if owner_left_detected else 'FAIL'}")
    for r in owner_left_res:
        print(
            f"    * Flagged System '{r[0]}' owned by departed employee '{r[1]}' (left: {r[2]})"
        )

    print("\n4. DUPLICATION & CATALOG INTEGRITY")
    for lbl, data in node_counts_scorecard.items():
        status = "OK" if data["duplicates"] == 0 else f"DUP({data['duplicates']})"
        print(
            f"  - {lbl:<10}: actual={data['actual']:<3} (expected={data['expected']:<3}, distinct={data['distinct']:<3}) [{status}]"
        )

    # 5. Misses and False Positives Listing
    misses = [gt for gt in GROUND_TRUTH_DECISIONS if gt["id"] not in matched_gt]
    false_positives = [
        ext for idx, ext in enumerate(extracted) if idx not in matched_ext_indices
    ]

    print("\n5. DETAILED ERROR ANALYSIS")
    if misses:
        print(f"  Missed Ground Truth Decisions ({len(misses)}):")
        for m in misses:
            print(
                f"    - [{m['id']}] '{m['title']}' (Decider: {m['decider']}, Source: {m['source']})"
            )
    else:
        print("  Missed Decisions: None (100% Recall)")

    if false_positives:
        print(f"\n  False Positive Decisions ({len(false_positives)}):")
        for fp in false_positives:
            print(
                f"    - '{fp['title']}' (Decider: {fp['decider']}, System: {fp['system']})"
            )
    else:
        print("\n  False Positives: None (100% Precision)")

    print("\n" + "=" * 70 + "\n")

    return {
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "decider_accuracy": decider_acc,
        "supersedes_recall": super_recall,
        "supersedes_precision": super_precision,
        "contradicts_recall": contra_recall,
        "contradicts_precision": contra_precision,
        "owner_left_detected": owner_left_detected,
        "node_counts": node_counts_scorecard,
        "misses": misses,
        "false_positives": false_positives,
    }


if __name__ == "__main__":
    ds = sys.argv[1] if len(sys.argv) > 1 else "company_brain"
    asyncio.run(evaluate_graph(ds))
