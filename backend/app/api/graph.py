"""Graph topology exploration API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from app.api.schemas import GraphEdge, GraphNode, GraphResponse
from app.brain.memory import query_graph
from app.config import get_settings

logger = logging.getLogger("decision_trace.api.graph")
router = APIRouter(prefix="/graph", tags=["Graph Exploration"])
_settings = get_settings()


@router.get("", response_model=GraphResponse)
async def get_graph(
    types: Optional[list[str]] = Query(
        None, description="Filter by node labels (e.g. Decision, Person, System, Ticket, Meeting)"
    ),
    limit: int = Query(default=100, ge=1, le=500, description="Max nodes to return"),
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> GraphResponse:
    """Retrieve nodes and edges with optional type filters and node limits for visualization."""
    target_dataset = dataset_name or _settings.DATASET_NAME

    # 1. Fetch nodes
    if types:
        labels_filter = " OR ".join(f"labels(n) = ['{t}']" for t in types)
        n_query = (
            f"MATCH (n) WHERE {labels_filter} RETURN id(n), labels(n), properties(n) LIMIT $limit"
        )
    else:
        n_query = "MATCH (n) RETURN id(n), labels(n), properties(n) LIMIT $limit"

    n_rows = await query_graph(n_query, dataset_name=target_dataset, params={"limit": limit})

    nodes: list[GraphNode] = []
    node_ids: set[str] = set()

    for row in n_rows:
        if not row:
            continue
        internal_id = str(row[0])
        labels = row[1] if len(row) > 1 and row[1] else ["Entity"]
        label = labels[0] if isinstance(labels, list) and labels else str(labels)
        props = row[2] if len(row) > 2 and isinstance(row[2], dict) else {}

        # Canonical key: id property if present, else title/name, else internal id
        n_id = str(
            props.get("id")
            or props.get("ticket_id")
            or props.get("name")
            or props.get("title")
            or internal_id
        )
        if n_id in node_ids:
            continue
        node_ids.add(n_id)
        nodes.append(GraphNode(id=n_id, label=label, properties=props))

    # 2. Fetch edges connecting returned nodes
    edges: list[GraphEdge] = []
    if node_ids:
        e_query = (
            "MATCH (a)-[r]->(b) "
            "RETURN id(a), properties(a), type(r), properties(r), id(b), properties(b) "
            "LIMIT $edge_limit"
        )
        e_rows = await query_graph(
            e_query, dataset_name=target_dataset, params={"edge_limit": limit * 3}
        )
        seen_edges: set[tuple[str, str, str]] = set()

        for row in e_rows:
            if not row or len(row) < 6:
                continue
            a_props = row[1] if isinstance(row[1], dict) else {}
            rel_type = str(row[2]) if row[2] else "relates_to"
            rel_props = row[3] if isinstance(row[3], dict) else {}
            b_props = row[5] if isinstance(row[5], dict) else {}

            a_id = str(
                a_props.get("id")
                or a_props.get("ticket_id")
                or a_props.get("name")
                or a_props.get("title")
                or row[0]
            )
            b_id = str(
                b_props.get("id")
                or b_props.get("ticket_id")
                or b_props.get("name")
                or b_props.get("title")
                or row[4]
            )

            if a_id in node_ids and b_id in node_ids:
                edge_key = (a_id, b_id, rel_type)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append(
                        GraphEdge(source=a_id, target=b_id, type=rel_type, properties=rel_props)
                    )

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
    )
