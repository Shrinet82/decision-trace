"""Decision management API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas import DecisionDetail, DecisionSummary, HealthStatus, SourceRef
from app.brain.codes import get_decision_codes
from app.brain.health import evaluate_graph_health
from app.brain.memory import query_graph
from app.config import get_settings

logger = logging.getLogger("decision_trace.api.decisions")
router = APIRouter(prefix="/decisions", tags=["Decisions"])
_settings = get_settings()


@router.get("", response_model=list[DecisionSummary])
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


@router.get("/{decision_id}", response_model=DecisionDetail)
async def get_decision(
    decision_id: str,
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> DecisionDetail:
    """Retrieve detailed decision profile with full lineage, people, systems, and evidence sources."""
    target_dataset = dataset_name or _settings.DATASET_NAME

    # Query the decision node
    d_rows = await query_graph(
        "MATCH (d:Decision) WHERE d.id = $id OR d.title = $id "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "RETURN d.id, d.title, coalesce(d.summary, ''), coalesce(d.rationale, ''), "
        "coalesce(d.status, 'accepted'), coalesce(d.decided_on, ''), s.name, p.name",
        dataset_name=target_dataset,
        params={"id": decision_id},
    )
    if not d_rows or not d_rows[0]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision with ID or title '{decision_id}' not found.",
        )

    row = d_rows[0]
    canonical_id = str(row[0])
    title = str(row[1]) if row[1] else "Untitled"
    summary = str(row[2]) if row[2] else ""
    rationale = str(row[3]) if row[3] else ""
    d_status = str(row[4]) if row[4] else "accepted"
    decided_on = str(row[5]) if row[5] else None
    sys_name = str(row[6]) if row[6] else None
    p_name = str(row[7]) if row[7] else None

    # People: decider + attendees / assignees
    people_rows = await query_graph(
        "MATCH (d:Decision {id: $id}) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p1:Person) "
        "OPTIONAL MATCH (d)-[:based_on]->(m:Meeting)-[:attended_by]->(p2:Person) "
        "OPTIONAL MATCH (d)-[:based_on]->(t:Ticket)-[:assigned_to]->(p3:Person) "
        "OPTIONAL MATCH (d)-[:based_on]->(t)-[:raised_by]->(p4:Person) "
        "RETURN DISTINCT coalesce(p1.name, p2.name, p3.name, p4.name)",
        dataset_name=target_dataset,
        params={"id": canonical_id},
    )
    people = sorted({str(r[0]) for r in people_rows if r and r[0] and str(r[0]).strip()})

    # Systems: about_system + mentions
    sys_rows = await query_graph(
        "MATCH (d:Decision {id: $id}) "
        "OPTIONAL MATCH (d)-[:about_system]->(s1:System) "
        "OPTIONAL MATCH (d)-[:based_on]->(t:Ticket)-[:mentions]->(s2:System) "
        "RETURN DISTINCT coalesce(s1.name, s2.name)",
        dataset_name=target_dataset,
        params={"id": canonical_id},
    )
    systems_set = {str(r[0]) for r in sys_rows if r and r[0] and str(r[0]).strip()}
    if sys_name:
        systems_set.add(sys_name)
    systems = sorted(systems_set)

    # Sources: tickets or meetings
    sources: list[SourceRef] = []
    source_tickets = await query_graph(
        "MATCH (d:Decision {id: $id})-[:based_on]->(t:Ticket) "
        "RETURN t.ticket_id, t.title, coalesce(t.closed, t.opened, '')",
        dataset_name=target_dataset,
        params={"id": canonical_id},
    )
    for r in source_tickets:
        if r and r[0]:
            sources.append(
                SourceRef(
                    type="ticket",
                    id=str(r[0]),
                    title=str(r[1]) if r[1] else str(r[0]),
                    date=str(r[2]) if r[2] else None,
                )
            )

    source_meetings = await query_graph(
        "MATCH (d:Decision {id: $id})-[:based_on]->(m:Meeting) "
        "RETURN m.title, coalesce(m.date, '')",
        dataset_name=target_dataset,
        params={"id": canonical_id},
    )
    for r in source_meetings:
        if r and r[0]:
            sources.append(
                SourceRef(
                    type="meeting",
                    id=str(r[0]),
                    title=str(r[0]),
                    date=str(r[1]) if r[1] else None,
                )
            )

    # Supersedes chain (outgoing: d -> d_old)
    supersedes_rows = await query_graph(
        "MATCH (d:Decision {id: $id})-[:supersedes]->(target:Decision) RETURN target.title",
        dataset_name=target_dataset,
        params={"id": canonical_id},
    )
    supersedes = [str(r[0]) for r in supersedes_rows if r and r[0]]

    # Superseded by chain (incoming: d_newer -> d)
    superseded_by_rows = await query_graph(
        "MATCH (source:Decision)-[:supersedes]->(d:Decision {id: $id}) RETURN source.title",
        dataset_name=target_dataset,
        params={"id": canonical_id},
    )
    superseded_by = [str(r[0]) for r in superseded_by_rows if r and r[0]]

    # Contradicts chain (bidirectional)
    contradicts_rows = await query_graph(
        "MATCH (d:Decision {id: $id})-[:contradicts]-(other:Decision) RETURN other.title",
        dataset_name=target_dataset,
        params={"id": canonical_id},
    )
    contradicts = [str(r[0]) for r in contradicts_rows if r and r[0]]

    # Health evaluation
    health_map = await evaluate_graph_health(dataset_name=target_dataset)
    h_info = health_map.get(canonical_id)
    computed_health: HealthStatus = h_info.status if h_info else "active"
    computed_reason: str = (
        h_info.reason if h_info else "Active decision with valid system ownership."
    )

    codes = await get_decision_codes(target_dataset)
    return DecisionDetail(
        id=canonical_id,
        decision_code=codes.get(canonical_id),
        decider_departed=h_info.decider_departed if h_info else False,
        title=title,
        summary=summary,
        rationale=rationale,
        status=d_status,
        health=computed_health,
        health_reason=computed_reason,
        decided_on=decided_on,
        decided_by=p_name,
        people=people,
        systems=systems,
        sources=sources,
        supersedes=supersedes,
        superseded_by=superseded_by,
        contradicts=contradicts,
    )
