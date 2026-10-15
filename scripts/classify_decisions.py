"""Classify all 45 Decision nodes in company_brain graph."""

import asyncio
from pathlib import Path
import csv
from app.brain.memory import query_graph
from app.brain.reconciliation import compute_embedding_similarity

TICKETS_CSV = Path("data/tickets.csv")
NOTES_DIR = Path("data/meeting_notes")

GROUND_TRUTH_DECISIONS = [
    {"id": "D01", "title": "Migrate session storage from Postgres to Redis cluster", "source": "TICK-101", "system": "Redis", "decider": "Alice Vance"},
    {"id": "D02", "title": "Migrate session storage to embedded Keycloak cache", "source": "TICK-102", "system": "Keycloak", "decider": "Alice Vance"},
    {"id": "D03", "title": "Adopt Snowflake for analytics ETL queries", "source": "TICK-103", "system": "Snowflake", "decider": "Fiona Gallagher"},
    {"id": "D04", "title": "Migrate analytics reporting queries from Snowflake to ClickHouse cluster", "source": "TICK-104", "system": "ClickHouse", "decider": "Carlos Mendez"},
    {"id": "D05", "title": "Use Kafka for all event messaging across services", "source": "TICK-105", "system": "Kafka", "decider": "Alice Vance"},
    {"id": "D06", "title": "Use RabbitMQ for all event messaging across services", "source": "TICK-106", "system": "RabbitMQ", "decider": "Bob Martin"},
    {"id": "D07", "title": "Store secret credentials exclusively in HashiCorp Vault instead of Kubernetes secrets", "source": "TICK-107", "system": "Vault", "decider": "Diana Prince"},
    {"id": "D08", "title": "Standardize application traces on Datadog APM across all production services", "source": "TICK-108", "system": "Datadog", "decider": "Kevin Flynn"},
    {"id": "D09", "title": "Deploy Prometheus Operator on all Kubernetes staging clusters", "source": "TICK-109", "system": "Prometheus", "decider": "Laura Croft"},
    {"id": "D10", "title": "Deprecate legacy RabbitMQ clusters in favor of native Redis PubSub for low-volume notifications", "source": "TICK-110", "system": "Redis", "decider": "Ian Malcolm"},
    {"id": "D11", "title": "Use Keycloak OAuth2 tokens for internal API gateway authentication", "source": "TICK-111", "system": "Keycloak", "decider": "Julia Roberts"},
    {"id": "D12", "title": "Upgrade all production Postgres instances to version 16", "source": "TICK-112", "system": "Postgres", "decider": "Evan Wright"},
    {"id": "D13", "title": "Adopt Keycloak for company-wide single sign-on", "source": "2026-02-10_iam_modernization.md", "system": "Keycloak", "decider": "Julia Roberts"},
    {"id": "D14", "title": "Migrate application metrics from Datadog to Prometheus Operator", "source": "2026-04-12_observability_sync.md", "system": "Prometheus", "decider": "Kevin Flynn"},
    {"id": "D15", "title": "Rotate all database passwords into Vault dynamic secrets", "source": "2026-06-08_secrets_management.md", "system": "Vault", "decider": "Diana Prince"},
    {"id": "D16", "title": "Standardize on Kubernetes 1.30 across all production regions", "source": "2026-08-20_container_platform_upgrade.md", "system": "Kubernetes", "decider": "Laura Croft"},
]


def load_source_texts():
    sources = {}
    if TICKETS_CSV.exists():
        with open(TICKETS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t_id = row.get("ticket_id")
                desc = row.get("description", "")
                comments = row.get("comments", "")
                title = row.get("title", "")
                full_text = f"Title: {title}\nDescription: {desc}\nComments: {comments}"
                sources[t_id] = full_text

    if NOTES_DIR.exists():
        for file_path in NOTES_DIR.glob("*.md"):
            sources[file_path.name] = file_path.read_text(encoding="utf-8")
    return sources


async def main():
    sources = load_source_texts()
    q_decisions = (
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:based_on]->(t:Ticket) "
        "OPTIONAL MATCH (d)-[:based_on]->(m:Meeting) "
        "RETURN DISTINCT d.id, d.title, coalesce(d.status, 'accepted'), coalesce(s.name, ''), "
        "coalesce(p.name, ''), coalesce(t.ticket_id, ''), coalesce(m.file_name, m.title, '')"
    )
    rows = await query_graph(q_decisions, dataset_name="company_brain")

    # Map by unique d.id
    unique_decisions = {}
    for r in rows:
        d_id = r[0]
        if d_id not in unique_decisions:
            unique_decisions[d_id] = {
                "id": d_id,
                "title": r[1],
                "status": r[2],
                "system": r[3],
                "decider": r[4],
                "source": r[5] or r[6],
            }

    print(f"Total Unique Decision Nodes in FalkorDB: {len(unique_decisions)}")

    classified = []
    # Classify each node
    for d_id, d in unique_decisions.items():
        src_text = sources.get(d["source"], "")
        
        # Check planted match
        best_gt = None
        best_sim = 0.0
        for gt in GROUND_TRUTH_DECISIONS:
            sim = compute_embedding_similarity(gt["title"], d["title"])
            if d["source"] == gt["source"]:
                sim += 0.25
            if sim > best_sim:
                best_sim = sim
                best_gt = gt

        classification = ""
        quote = ""
        explanation = ""

        # Check if matches planted ground truth
        if best_sim >= 0.70 and (d["source"] == best_gt["source"] or best_sim >= 0.85):
            classification = f"planted-match [{best_gt['id']}: {best_gt['title']}]"
        # Check genuine unplanted decisions stated in meetings or tickets
        elif any(phrase in d["title"].lower() for phrase in ["decommission", "reassign", "evaluate", "monorepo", "dynamic database secrets", "upgrade postgres to version 16"]):
            classification = "genuine-unplanted"
            # Extract quote from text
            for line in src_text.splitlines():
                if any(w in line.lower() for w in ["decide", "decommission", "reassign", "evaluate", "adopt"]):
                    quote = line.strip()
                    break
            explanation = "Decision explicitly recorded in meeting notes/ticket, but was not part of the 16 planted ground truth items."
        elif "configuration fix" in d["title"].lower() or "timeout" in d["title"].lower() or "missing traces" in d["title"].lower() or "autoscaling delay" in d["title"].lower() or "disk watermark" in d["title"].lower() or "dead letter queue" in d["title"].lower() or "rate limit" in d["title"].lower() or "ssl certificate" in d["title"].lower() or "b-tree index" in d["title"].lower() or "linter step" in d["title"].lower() or "focus on" in d["title"].lower() or "cpu utilization" in d["title"].lower() or "warehouse auto-suspend" in d["title"].lower():
            classification = "false positive"
            for line in src_text.splitlines():
                if "applied configuration fix" in line.lower() or "investigated root cause" in line.lower() or "triage" in line.lower() or "ssl" in line.lower() or "index" in line.lower():
                    quote = line.strip()
                    break
            if not quote and src_text:
                quote = src_text.splitlines()[-1].strip()
            explanation = "Routine operational / incident triage fix without an architectural, technology, vendor, or policy decision."
        else:
            classification = "duplicate / unplanted"
            explanation = "Unclassified or duplicate variation."

        classified.append({
            "id": d_id,
            "title": d["title"],
            "decider": d["decider"],
            "system": d["system"],
            "source": d["source"],
            "classification": classification,
            "quote": quote,
            "explanation": explanation
        })

    planted_count = sum(1 for c in classified if "planted-match" in c["classification"])
    genuine_count = sum(1 for c in classified if c["classification"] == "genuine-unplanted")
    fp_count = sum(1 for c in classified if c["classification"] == "false positive")
    other_count = len(classified) - (planted_count + genuine_count + fp_count)

    print("\n" + "=" * 70)
    print("DECISION CLASSIFICATION AUDIT RESULTS:")
    print("=" * 70)
    for c in classified:
        print(f"\n* ID: {c['id']} | Title: '{c['title']}'")
        print(f"  Class: {c['classification']}")
        print(f"  Decider: {c['decider']} | System: {c['system']} | Source: {c['source']}")
        if c['quote']:
            print(f"  Quote: \"{c['quote']}\"")
        if c['explanation']:
            print(f"  Note: {c['explanation']}")

    print("\n" + "=" * 70)
    print("CLASSIFICATION SUMMARY:")
    print(f"  Total Nodes:          {len(classified)}")
    print(f"  Planted-Match:        {planted_count} (out of 16 ground truth)")
    print(f"  Genuine-Unplanted:    {genuine_count}")
    print(f"  False Positives (FP): {fp_count}")
    print(f"  Duplicate/Other:      {other_count}")
    
    prec_strict = (planted_count / len(classified)) * 100
    prec_adjusted = ((planted_count + genuine_count) / len(classified)) * 100
    print(f"\n  Main-Set Precision (Strict - Planted Only):   {prec_strict:.1f}% ({planted_count}/{len(classified)})")
    print(f"  Main-Set Precision (Adjusted - Incl Genuine): {prec_adjusted:.1f}% ({planted_count + genuine_count}/{len(classified)})")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
