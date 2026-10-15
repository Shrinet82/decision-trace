"""Audit all Decision nodes in FalkorDB company_brain graph."""

import asyncio
from pathlib import Path
import csv
from app.brain.memory import query_graph
from app.brain.health import evaluate_graph_health

TICKETS_CSV = Path("data/tickets.csv")
NOTES_DIR = Path("data/meeting_notes")


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
    health_map = await evaluate_graph_health("company_brain")

    # 1. Fetch all decision nodes
    q_decisions = (
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:based_on]->(t:Ticket) "
        "OPTIONAL MATCH (d)-[:based_on]->(m:Meeting) "
        "RETURN d.id, d.title, coalesce(d.status, 'accepted'), coalesce(s.name, ''), "
        "coalesce(p.name, ''), coalesce(t.ticket_id, ''), coalesce(m.file_name, m.title, '')"
    )
    d_rows = await query_graph(q_decisions, dataset_name="company_brain")

    # 2. Fetch all supersedes edges
    q_supersedes = (
        "MATCH (d1:Decision)-[r:supersedes]->(d2:Decision) "
        "OPTIONAL MATCH (d1)-[:based_on]->(t1:Ticket) "
        "OPTIONAL MATCH (d1)-[:based_on]->(m1:Meeting) "
        "OPTIONAL MATCH (d2)-[:based_on]->(t2:Ticket) "
        "OPTIONAL MATCH (d2)-[:based_on]->(m2:Meeting) "
        "RETURN d1.id, d1.title, coalesce(t1.ticket_id, m1.file_name, ''), "
        "d2.id, d2.title, coalesce(t2.ticket_id, m2.file_name, '')"
    )
    super_rows = await query_graph(q_supersedes, dataset_name="company_brain")

    print(f"=== TOTAL DECISION NODES: {len(d_rows)} ===")
    for idx, r in enumerate(d_rows, 1):
        d_id, title, status, sys_name, decider, t_id, m_file = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        src_id = t_id or m_file
        health_info = health_map.get(d_id)
        health_status = health_info.status if health_info else "unknown"
        health_reason = health_info.reason if health_info else ""
        src_text = sources.get(src_id, "")
        snippet = src_text.replace("\n", " ")[:160] if src_text else "NO SOURCE TEXT"
        print(f"\n[{idx}/{len(d_rows)}] ID: {d_id}")
        print(f"  Title: '{title}'")
        print(f"  Decider: '{decider}' | System: '{sys_name}' | Status: '{status}'")
        print(f"  Source: '{src_id}' | Health: {health_status} ({health_reason})")
        print(f"  Source snippet: {snippet}")

    print(f"\n=== TOTAL SUPERSEDES EDGES: {len(super_rows)} ===")
    for idx, r in enumerate(super_rows, 1):
        d1_id, d1_title, d1_src, d2_id, d2_title, d2_src = r[0], r[1], r[2], r[3], r[4], r[5]
        print(f"\n[Supersedes {idx}]")
        print(f"  Source ({d1_id}, '{d1_title}', src: {d1_src})")
        print(f"  -> Target ({d2_id}, '{d2_title}', src: {d2_src})")
        d1_text = sources.get(d1_src, "")
        d1_snip = d1_text.replace("\n", " ")[:200] if d1_text else "NO SOURCE"
        print(f"  Source document text supporting this: {d1_snip}")

if __name__ == "__main__":
    asyncio.run(main())
