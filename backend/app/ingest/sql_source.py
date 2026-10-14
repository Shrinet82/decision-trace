"""Deterministic SQL Source Ingestion (No LLM).

Reads organizational metadata from an SQLite database (e.g. data/company.db)
and deterministic entities (Person, Team, Project, System) and relationships
(member_of, owns, leads) into FalkorDB using domain DataPoint identity keys.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from app.brain.memory import get_or_create_dataset_graph_name, query_graph
from app.brain.models import Person, Project, System, Team
from app.config import get_settings

logger = logging.getLogger("decision_trace.ingest.sql")
_settings = get_settings()

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "company.db"


async def ingest_sql_source(
    db_path: Optional[str | Path] = None,
    dataset_name: Optional[str] = None,
) -> dict[str, Any]:
    """Ingest deterministic entities and edges from SQLite into FalkorDB.

    Args:
        db_path: Path to the SQLite company database.
        dataset_name: Target dataset name.

    Returns:
        dict: Summary counts of ingested nodes and edges.
    """
    path = Path(db_path or DEFAULT_DB_PATH)
    if not path.exists():
        raise FileNotFoundError(f"SQLite database not found at: {path}")

    target_dataset = dataset_name or _settings.DATASET_NAME
    # Ensure Cognee dataset/graph is registered
    graph_name = await get_or_create_dataset_graph_name(target_dataset)
    logger.info("Ingesting SQL organizational source from %s into dataset '%s' (graph: %s)...", path, target_dataset, graph_name)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    counts = {"teams": 0, "people": 0, "projects": 0, "systems": 0, "edges": 0}

    try:
        # 1. Ingest Teams using Team DataPoint identity
        cur.execute("SELECT id, name, department, lead_id FROM teams")
        teams = cur.fetchall()
        for t in teams:
            t_dp = Team(name=t["name"])
            t_id = str(t_dp.id)
            t_name = t["name"].replace("'", "\\'")
            t_dept = (t["department"] or "").replace("'", "\\'")
            await query_graph(
                f"MERGE (t:Team {{id: '{t_id}'}}) "
                f"ON CREATE SET t.name = '{t_name}', t.department = '{t_dept}' "
                f"ON MATCH SET t.name = '{t_name}', t.department = '{t_dept}'",
                dataset_name=target_dataset,
            )
            counts["teams"] += 1

        # 2. Ingest People using Person DataPoint identity
        cur.execute("SELECT id, name, email, role, team_id, start_date, leave_date FROM people")
        people = cur.fetchall()
        for p in people:
            p_dp = Person(name=p["name"])
            p_id = str(p_dp.id)
            p_name = p["name"].replace("'", "\\'")
            p_email = p["email"].replace("'", "\\'")
            p_role = (p["role"] or "").replace("'", "\\'")
            p_start = p["start_date"] or ""
            p_leave = p["leave_date"] or ""
            is_active = p["leave_date"] is None
            await query_graph(
                f"MERGE (p:Person {{id: '{p_id}'}}) "
                f"ON CREATE SET p.name = '{p_name}', p.email = '{p_email}', p.role = '{p_role}', "
                f"p.start_date = '{p_start}', p.leave_date = '{p_leave}', p.is_active = {str(is_active).lower()} "
                f"ON MATCH SET p.name = '{p_name}', p.email = '{p_email}', p.role = '{p_role}', "
                f"p.start_date = '{p_start}', p.leave_date = '{p_leave}', p.is_active = {str(is_active).lower()}",
                dataset_name=target_dataset,
            )
            counts["people"] += 1

        # 3. Ingest Projects using Project DataPoint identity
        cur.execute("SELECT id, name, description, status, lead_id FROM projects")
        projects = cur.fetchall()
        for pr in projects:
            pr_dp = Project(name=pr["name"])
            pr_id = str(pr_dp.id)
            pr_name = pr["name"].replace("'", "\\'")
            pr_desc = (pr["description"] or "").replace("'", "\\'")
            pr_status = pr["status"] or "active"
            await query_graph(
                f"MERGE (pr:Project {{id: '{pr_id}'}}) "
                f"ON CREATE SET pr.name = '{pr_name}', pr.description = '{pr_desc}', pr.status = '{pr_status}' "
                f"ON MATCH SET pr.name = '{pr_name}', pr.description = '{pr_desc}', pr.status = '{pr_status}'",
                dataset_name=target_dataset,
            )
            counts["projects"] += 1

        # 4. Ingest Systems using System DataPoint identity
        cur.execute("SELECT id, name, system_type, vendor, owner_id, status FROM systems")
        systems = cur.fetchall()
        for s in systems:
            s_dp = System(name=s["name"])
            s_id = str(s_dp.id)
            s_name = s["name"].replace("'", "\\'")
            s_type = (s["system_type"] or "").replace("'", "\\'")
            s_vendor = (s["vendor"] or "").replace("'", "\\'")
            s_status = s["status"] or "active"
            await query_graph(
                f"MERGE (s:System {{id: '{s_id}'}}) "
                f"ON CREATE SET s.name = '{s_name}', s.system_type = '{s_type}', s.vendor = '{s_vendor}', s.status = '{s_status}' "
                f"ON MATCH SET s.name = '{s_name}', s.system_type = '{s_type}', s.vendor = '{s_vendor}', s.status = '{s_status}'",
                dataset_name=target_dataset,
            )
            counts["systems"] += 1

        # 5. Ingest Relationships:
        # 5a. Person -> member_of -> Team
        cur.execute("""
            SELECT p.name AS person_name, t.name AS team_name
            FROM people p
            JOIN teams t ON p.team_id = t.id
        """)
        memberships = cur.fetchall()
        for m in memberships:
            p_name = m["person_name"].replace("'", "\\'")
            t_name = m["team_name"].replace("'", "\\'")
            await query_graph(
                f"MATCH (p:Person {{name: '{p_name}'}}), (t:Team {{name: '{t_name}'}}) "
                f"MERGE (p)-[r:member_of]->(t)",
                dataset_name=target_dataset,
            )
            counts["edges"] += 1

        # 5b. Person -> owns -> System
        cur.execute("""
            SELECT p.name AS owner_name, s.name AS system_name
            FROM systems s
            JOIN people p ON s.owner_id = p.id
        """)
        ownerships = cur.fetchall()
        for o in ownerships:
            p_name = o["owner_name"].replace("'", "\\'")
            s_name = o["system_name"].replace("'", "\\'")
            await query_graph(
                f"MATCH (p:Person {{name: '{p_name}'}}), (s:System {{name: '{s_name}'}}) "
                f"MERGE (p)-[r:owns]->(s)",
                dataset_name=target_dataset,
            )
            counts["edges"] += 1

        # 5c. Person -> leads -> Team
        cur.execute("""
            SELECT p.name AS lead_name, t.name AS team_name
            FROM teams t
            JOIN people p ON t.lead_id = p.id
        """)
        team_leads = cur.fetchall()
        for tl in team_leads:
            p_name = tl["lead_name"].replace("'", "\\'")
            t_name = tl["team_name"].replace("'", "\\'")
            await query_graph(
                f"MATCH (p:Person {{name: '{p_name}'}}), (t:Team {{name: '{t_name}'}}) "
                f"MERGE (p)-[r:leads]->(t)",
                dataset_name=target_dataset,
            )
            counts["edges"] += 1

        # 5d. Person -> leads -> Project
        cur.execute("""
            SELECT p.name AS lead_name, pr.name AS project_name
            FROM projects pr
            JOIN people p ON pr.lead_id = p.id
        """)
        project_leads = cur.fetchall()
        for pl in project_leads:
            p_name = pl["lead_name"].replace("'", "\\'")
            pr_name = pl["project_name"].replace("'", "\\'")
            await query_graph(
                f"MATCH (p:Person {{name: '{p_name}'}}), (pr:Project {{name: '{pr_name}'}}) "
                f"MERGE (p)-[r:leads]->(pr)",
                dataset_name=target_dataset,
            )
            counts["edges"] += 1

    finally:
        conn.close()

    logger.info("SQL organizational ingestion completed: %s", counts)
    return counts
