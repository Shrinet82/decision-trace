"""Decision management API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas import DecisionDetail, DecisionSummary, HealthStatus
from app.brain.cache import cached_endpoint
from app.brain.codes import get_decision_codes
from app.brain.health import evaluate_graph_health
from app.brain.lineage import build_decision_detail
from app.brain.memory import query_graph
from app.config import get_settings

logger = logging.getLogger("decision_trace.api.decisions")
router = APIRouter(prefix="/decisions", tags=["Decisions"])
_settings = get_settings()


@router.get("", response_model=list[DecisionSummary])
@cached_endpoint("decisions.list_decisions", 120.0)
async def list_decisions(
    system: Optional[str] = Query(
        None, description="Filter decisions by system name (e.g. Redis, Kafka)"
    ),
    person: Optional[str] = Query(None, description="Filter decisions by decider name"),
    health: Optional[HealthStatus] = Query(None, description="Filter decisions by health status"),
    limit: int = Query(default=100, ge=1, le=500, description="Max decisions to return"),
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> list[DecisionSummary]:
    """Retrieve decisions filtered by system, person, and/or health status."""
    target_dataset = dataset_name or _settings.DATASET_NAME

    # 1. Evaluate graph health across all decisions
    health_map = await evaluate_graph_health(dataset_name=target_dataset)

    # 2. Query basic decision attributes from FalkorDB
    codes = await get_decision_codes(target_dataset)
    query = (
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:based_on]->(t:Ticket) "
        "OPTIONAL MATCH (d)-[:based_on]->(m:Meeting) "
        "RETURN d.id, d.title, coalesce(d.status, 'accepted'), collect(DISTINCT s.name), "
        "collect(DISTINCT p.name), d.decided_on, collect(DISTINCT m.date), "
        "collect(DISTINCT t.closed), collect(DISTINCT t.opened), d.created_at"
    )
    rows = await query_graph(query, dataset_name=target_dataset)

    summaries: list[DecisionSummary] = []
    seen_ids: set[str] = set()

    for row in rows:
        if not row or not row[0]:
            continue
        d_id = str(row[0])
        if d_id in seen_ids:
            continue
        seen_ids.add(d_id)

        title = str(row[1]) if row[1] else "Untitled"
        d_status = str(row[2]) if row[2] else "accepted"
        systems = sorted({str(x) for x in (row[3] or []) if x})
        deciders = sorted({str(x) for x in (row[4] or []) if x})
        dates = [row[5], *(row[6] or []), *(row[7] or []), *(row[8] or []), row[9]]
        dec_on = next((str(x) for x in dates if x), None)

        # Filter by system if provided
        if system and not any(system.lower() in name.lower() for name in systems):
            continue

        # Filter by person if provided
        if person and not any(person.lower() in name.lower() for name in deciders):
            continue

        h_info = health_map.get(d_id)
        computed_health: HealthStatus = h_info.status if h_info else "active"
        computed_reason: str = (
            h_info.reason if h_info else "Active decision; no conflicting or superseding decisions."
        )

        # Filter by health status if provided
        if health and computed_health != health:
            continue

        summaries.append(
            DecisionSummary(
                id=d_id,
                decision_code=codes.get(d_id),
                title=title,
                status=d_status,
                health=computed_health,
                health_reason=computed_reason,
                system=", ".join(systems) or None,
                systems=systems,
                decided_by=", ".join(deciders) or None,
                deciders=deciders,
                decider_departed=h_info.decider_departed if h_info else False,
                decided_on=dec_on,
            )
        )

    summaries.sort(key=lambda d: d.decision_code or "~")
    return summaries[:limit]


@router.get("/{decision_ref}", response_model=DecisionDetail)
@cached_endpoint("decisions.get_decision", 120.0)
async def get_decision(
    decision_ref: str,
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> DecisionDetail:
    """Full decision page: health, deciders, sources, lineage chains, system timeline, impact,
    the deduplicated subgraph, and the Cypher that produced it. Accepts a DEC code (DEC-11),
    a decision id, or an exact title."""
    target_dataset = dataset_name or _settings.DATASET_NAME
    detail = await build_decision_detail(decision_ref, dataset_name=target_dataset)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision '{decision_ref}' not found.",
        )
    return DecisionDetail(**detail)
