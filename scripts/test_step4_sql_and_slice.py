"""Step 4 Evaluation: SQL Ingestion, Entity Resolution with Roster, and Ticket Slice.

Executes:
1. Baseline FalkorDB memory measurement.
2. Deterministic SQL source ingestion from data/company.db.
3. Memory measurement post-SQL ingestion.
4. Roster verification.
5. Ingestion and extraction of a 10-ticket slice from data/tickets.csv.
6. Verification of reference resolution (resolves to existing Person/System nodes vs duplicates).
7. Memory measurement post-slice.
8. Output Cypher queries and node/relationship counts.
"""

import asyncio
import csv
import logging
from pathlib import Path

from app.brain.memory import (
    get_entity_roster,
    get_falkordb_memory_usage,
    ingest_text,
    query_graph,
    reset,
)
from app.ingest.sql_source import ingest_sql_source

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("step4_eval")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TICKETS_CSV = DATA_DIR / "tickets.csv"


async def run_step4_eval():
    dataset = "step4_eval_dataset"
    print("\n=======================================================")
    print("STEP 4: SQL INGESTION, ROSTER RESOLUTION, & TICKET SLICE")
    print("=======================================================")

    # 1. Reset dataset and measure baseline memory
    await reset(dataset_name=dataset)
    mem_baseline = await get_falkordb_memory_usage()
    print(
        f"\n[FalkorDB Memory Baseline]: {mem_baseline.get('used_memory_human', 'N/A')} ({mem_baseline.get('used_memory')} bytes)"
    )

    # 2. Ingest SQL Source
    print("\n--- 1. Ingesting SQL Source (data/company.db) ---")
    sql_counts = await ingest_sql_source(
        db_path=DATA_DIR / "company.db", dataset_name=dataset
    )
    print("SQL Ingestion Counts:", sql_counts)

    # 3. Memory post-SQL
    mem_post_sql = await get_falkordb_memory_usage()
    print(
        f"\n[FalkorDB Memory Post-SQL]: {mem_post_sql.get('used_memory_human', 'N/A')} ({mem_post_sql.get('used_memory')} bytes)"
    )

    # Verify SQL nodes in FalkorDB
    sql_people = await query_graph(
        "MATCH (p:Person) RETURN count(p), collect(p.name)", dataset_name=dataset
    )
    sql_systems = await query_graph(
        "MATCH (s:System) RETURN count(s), collect(s.name)", dataset_name=dataset
    )
    sql_teams = await query_graph(
        "MATCH (t:Team) RETURN count(t)", dataset_name=dataset
    )
    sql_projects = await query_graph(
        "MATCH (pr:Project) RETURN count(pr)", dataset_name=dataset
    )
    print(
        f"Verified SQL Nodes in FalkorDB: {sql_people[0][0]} People, {sql_systems[0][0]} Systems, {sql_teams[0][0]} Teams, {sql_projects[0][0]} Projects"
    )

    # Verify owner-left case
    orphan_query = (
        "MATCH (p:Person)-[:owns]->(s:System) WHERE p.is_active = false "
        "RETURN s.name, p.name, p.leave_date"
    )
    orphan_res = await query_graph(orphan_query, dataset_name=dataset)
    print("\n--- Orphaned System (Owner Left Company) ---")
    for row in orphan_res:
        print(
            f"  System '{row[0]}' is owned by departed employee '{row[1]}' (left: {row[2]})"
        )

    # 4. Fetch Roster
    roster = await get_entity_roster(dataset_name=dataset)
    print("\n--- Entity Roster Loaded for Extraction ---")
    print(f"  People ({len(roster['people'])}):", roster["people"])
    print(f"  Systems ({len(roster['systems'])}):", roster["systems"])

    # 5. Load and Ingest 10-ticket slice
    print("\n--- 2. Ingesting Slice of 10 Tickets ---")
    tickets_slice = []
    with open(TICKETS_CSV, mode="r", encoding="utf-8") as f:  # noqa: ASYNC230
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 10:
                break
            tickets_slice.append(row)

    print(f"Loaded {len(tickets_slice)} tickets:")
    for t in tickets_slice:
        print(
            f"  {t['ticket_id']}: {t['title']} (Reporter: {t['reporter']}, Assignee: {t['assignee']}, System: {t['system']})"
        )

    # Ingest each ticket as text document
    for i, t in enumerate(tickets_slice, 1):
        ticket_text = (
            f"Ticket ID: {t['ticket_id']}\n"
            f"Title: {t['title']}\n"
            f"Status: {t['status']}\n"
            f"Opened: {t['opened']}\n"
            f"Reporter: {t['reporter']}\n"
            f"Assignee: {t['assignee']}\n"
            f"System: {t['system']}\n"
            f"Comments: {t['comments']}"
        )
        print(f"\n[{i}/10] Ingesting {t['ticket_id']}...")
        await ingest_text(ticket_text, dataset_name=dataset, run_cognify=True)

    # 6. Memory post-slice
    mem_post_slice = await get_falkordb_memory_usage()
    print(
        f"\n[FalkorDB Memory Post-Ticket Slice]: {mem_post_slice.get('used_memory_human', 'N/A')} ({mem_post_slice.get('used_memory')} bytes)"
    )

    # 7. Check Entity Resolution & Duplicate Counts
    print("\n=======================================================")
    print("ENTITY RESOLUTION & DUPLICATION ANALYSIS")
    print("=======================================================")
    people_after = await query_graph(
        "MATCH (p:Person) RETURN count(p), collect(p.name)", dataset_name=dataset
    )
    systems_after = await query_graph(
        "MATCH (s:System) RETURN count(s), collect(s.name)", dataset_name=dataset
    )
    tickets_after = await query_graph(
        "MATCH (t:Ticket) RETURN count(t)", dataset_name=dataset
    )
    decisions_after = await query_graph(
        "MATCH (d:Decision) RETURN count(d)", dataset_name=dataset
    )

    print(f"People count before: {sql_people[0][0]} -> after: {people_after[0][0]}")
    print(f"Systems count before: {sql_systems[0][0]} -> after: {systems_after[0][0]}")
    print(f"Tickets in graph: {tickets_after[0][0]}")
    print(f"Decisions extracted: {decisions_after[0][0]}")

    if people_after[0][0] == sql_people[0][0]:
        print(
            ">> SUCCESS: Zero duplicate Person nodes created! All references resolved to existing roster."
        )
    else:
        new_people = set(people_after[0][1]) - set(sql_people[0][1])
        print(f">> WARNING: New Person nodes created: {new_people}")

    if systems_after[0][0] == sql_systems[0][0]:
        print(
            ">> SUCCESS: Zero duplicate System nodes created! All references resolved to existing catalog."
        )
    else:
        new_systems = set(systems_after[0][1]) - set(sql_systems[0][1])
        print(f">> WARNING: New System nodes created: {new_systems}")

    # 8. Cypher Queries of Extracted Decisions and Relationships
    print("\n--- Extracted Decisions ---")
    decisions = await query_graph(
        "MATCH (d:Decision) RETURN id(d), d.title, d.status ORDER BY id(d)",
        dataset_name=dataset,
    )
    for d in decisions:
        print(f"  id={d[0]}, title='{d[1]}', status='{d[2]}'")

    print("\n--- Decided By Relationships ---")
    decided_by = await query_graph(
        "MATCH (d:Decision)-[r:decided_by]->(p:Person) RETURN d.title, p.name",
        dataset_name=dataset,
    )
    for r in decided_by:
        print(
            f"  (:Decision {{title: '{r[0]}'}})-[:decided_by]->(:Person {{name: '{r[1]}' }})"
        )

    print("\n--- About System Relationships ---")
    about_sys = await query_graph(
        "MATCH (d:Decision)-[r:about_system]->(s:System) RETURN d.title, s.name",
        dataset_name=dataset,
    )
    for r in about_sys:
        print(
            f"  (:Decision {{title: '{r[0]}'}})-[:about_system]->(:System {{name: '{r[1]}' }})"
        )

    print("\n--- Supersedes Chains ---")
    supersedes = await query_graph(
        "MATCH (d1:Decision)-[r:supersedes]->(d2:Decision) RETURN d1.title, d2.title",
        dataset_name=dataset,
    )
    for r in supersedes:
        print(
            f"  (:Decision {{title: '{r[0]}'}})-[:supersedes]->(:Decision {{title: '{r[1]}' }})"
        )

    print("\n--- Contradicts Relationships ---")
    contradicts = await query_graph(
        "MATCH (d1:Decision)-[r:contradicts]->(d2:Decision) "
        "OPTIONAL MATCH (d1)-[:decided_by]->(p1:Person) "
        "OPTIONAL MATCH (d2)-[:decided_by]->(p2:Person) "
        "RETURN d1.title, p1.name, d2.title, p2.name",
        dataset_name=dataset,
    )
    for r in contradicts:
        print(
            f"  (:Decision {{title: '{r[0]}', by: '{r[1]}'}})-[:contradicts]->(:Decision {{title: '{r[2]}', by: '{r[3]}' }})"
        )

    print("\n=======================================================")
    print("STEP 4 EVALUATION COMPLETED")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(run_step4_eval())
