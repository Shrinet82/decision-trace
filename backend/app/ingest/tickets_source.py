"""Deterministic Ticket Source Ingestion (No LLM).

Reads tickets.csv and creates Ticket nodes plus raised_by, assigned_to,
and mentions edges without using an LLM, matching against canonical
Person and System nodes in FalkorDB.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Optional

from app.brain.memory import get_or_create_dataset_graph_name, query_graph
from app.brain.models import Ticket
from app.config import get_settings

logger = logging.getLogger("decision_trace.ingest.tickets")
_settings = get_settings()

DEFAULT_TICKETS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "tickets.csv"


async def ingest_tickets_source(
    csv_path: Optional[str | Path] = None,
    dataset_name: Optional[str] = None,
) -> dict[str, Any]:
    """Ingest deterministic Ticket nodes and edges from tickets.csv into FalkorDB.

    Args:
        csv_path: Path to tickets.csv file.
        dataset_name: Target dataset name.

    Returns:
        dict: Counts of tickets and edges created.
    """
    path = Path(csv_path or DEFAULT_TICKETS_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Tickets CSV not found at: {path}")

    target_dataset = dataset_name or _settings.DATASET_NAME
    graph_name = await get_or_create_dataset_graph_name(target_dataset)
    logger.info(
        "Ingesting tickets from %s into dataset '%s' (graph: %s)...",
        path,
        target_dataset,
        graph_name,
    )

    counts = {
        "tickets": 0,
        "raised_by_edges": 0,
        "assigned_to_edges": 0,
        "mentions_edges": 0,
    }

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        tickets = list(reader)

    # 1. Ingest Ticket nodes in batches of Cypher queries
    for t in tickets:
        t_id_str = t["ticket_id"].strip()
        t_dp = Ticket(ticket_id=t_id_str)
        t_node_id = str(t_dp.id)
        title = t.get("title", "").replace("'", "\\'")
        status = t.get("status", "open").replace("'", "\\'")
        opened = t.get("opened", "").replace("'", "\\'")
        closed = t.get("closed", "").replace("'", "\\'")
        system = t.get("system", "").replace("'", "\\'")
        reporter = t.get("reporter", "").strip().replace("'", "\\'")
        assignee = t.get("assignee", "").strip().replace("'", "\\'")

        # Merge Ticket Node
        await query_graph(
            f"MERGE (t:Ticket {{id: '{t_node_id}'}}) "
            f"ON CREATE SET t.ticket_id = '{t_id_str}', t.title = '{title}', "
            f"t.status = '{status}', t.opened = '{opened}', t.closed = '{closed}', t.system = '{system}' "
            f"ON MATCH SET t.ticket_id = '{t_id_str}', t.title = '{title}', "
            f"t.status = '{status}', t.opened = '{opened}', t.closed = '{closed}', t.system = '{system}'",
            dataset_name=target_dataset,
        )
        counts["tickets"] += 1

        # Edge: raised_by -> Person
        if reporter:
            res_r = await query_graph(
                f"MATCH (t:Ticket {{id: '{t_node_id}'}}), (p:Person {{name: '{reporter}'}}) "
                f"MERGE (t)-[r:raised_by]->(p) RETURN count(r)",
                dataset_name=target_dataset,
            )
            if res_r and res_r[0][0] > 0:
                counts["raised_by_edges"] += 1

        # Edge: assigned_to -> Person
        if assignee:
            res_a = await query_graph(
                f"MATCH (t:Ticket {{id: '{t_node_id}'}}), (p:Person {{name: '{assignee}'}}) "
                f"MERGE (t)-[r:assigned_to]->(p) RETURN count(r)",
                dataset_name=target_dataset,
            )
            if res_a and res_a[0][0] > 0:
                counts["assigned_to_edges"] += 1

        # Edge: mentions -> System
        if system:
            res_m = await query_graph(
                f"MATCH (t:Ticket {{id: '{t_node_id}'}}), (s:System {{name: '{system}'}}) "
                f"MERGE (t)-[r:mentions]->(s) RETURN count(r)",
                dataset_name=target_dataset,
            )
            if res_m and res_m[0][0] > 0:
                counts["mentions_edges"] += 1

    logger.info("Ticket deterministic ingestion completed: %s", counts)
    return counts
