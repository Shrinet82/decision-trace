"""Decision Health Assessment Engine using OpenCypher over FalkorDB.

Computes decision health deterministically from graph edges and properties:
- superseded: incoming supersedes edge (reason: which decision, when)
- contradicted: contradicts edge with another decision that is not itself superseded (reason: which one, decided by whom)
- possibly_stale: system owner has left the company (leave_date in past or inactive),
  or decision older than configurable days with no newer decision about that system
- active: none of the above
"""

import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.brain.memory import query_graph
from app.config import get_settings

logger = logging.getLogger("decision_trace.brain.health")
_settings = get_settings()

HealthStatus = Literal["active", "superseded", "contradicted", "possibly_stale"]


class DecisionHealthInfo(BaseModel):
    """Structured health assessment of a single architectural decision."""

    id: str = Field(..., description="Decision node ID")
    title: str = Field(..., description="Decision title")
    status: HealthStatus = Field(..., description="Computed health status")
    reason: str = Field(..., description="Human-readable justification for the health status")
    system: Optional[str] = Field(default=None, description="Associated system name")
    decided_by: Optional[str] = Field(default=None, description="Decider name")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Structured metadata supporting the health evaluation"
    )


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string into a datetime object."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(date_str).strip()[:10], "%Y-%m-%d")
        except ValueError:
            continue
    return None


async def evaluate_graph_health(
    dataset_name: Optional[str] = None,
    stale_days: int = 180,
    reference_date: Optional[str] = None,
) -> dict[str, DecisionHealthInfo]:
    """Evaluate health for all decisions in the FalkorDB knowledge graph.

    Args:
        dataset_name: Target dataset name.
        stale_days: Number of days without updates before a decision is deemed possibly stale.
        reference_date: Reference date string (YYYY-MM-DD) for evaluation (defaults to today).

    Returns:
        dict[str, DecisionHealthInfo]: Map of decision ID to health info.
    """
    target_dataset = dataset_name or _settings.DATASET_NAME
    ref_dt = _parse_date(reference_date) or datetime.now(timezone.utc).replace(tzinfo=None)
    ref_date_str = ref_dt.strftime("%Y-%m-%d")

    # 1. Fetch all decisions with their basic attributes, systems, deciders, and dates
    decisions_raw = await query_graph(
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:based_on]->(t:Ticket) "
        "OPTIONAL MATCH (d)-[:based_on]->(m:Meeting) "
        "RETURN d.id, d.title, s.name, p.name, "
        "coalesce(d.decided_on, m.date, t.closed, t.opened, d.created_at, '2026-01-01')",
        dataset_name=target_dataset,
    )

    decisions: dict[str, dict[str, Any]] = {}
    for row in decisions_raw:
        if not row or not row[0]:
            continue
        d_id = str(row[0])
        d_title = str(row[1]) if row[1] else "Untitled"
        s_name = str(row[2]) if row[2] else None
        p_name = str(row[3]) if row[3] else None
        d_date_str = str(row[4]) if row[4] else "2026-01-01"
        d_dt = _parse_date(d_date_str) or datetime(2026, 1, 1)

        decisions[d_id] = {
            "id": d_id,
            "title": d_title,
            "system": s_name,
            "decided_by": p_name,
            "date": d_date_str,
            "datetime": d_dt,
        }

    # 2. Check SUPERSEDED decisions via incoming supersedes edges
    # (d2)-[:supersedes]->(d)
    superseded_raw = await query_graph(
        "MATCH (d2:Decision)-[:supersedes]->(d:Decision) "
        "OPTIONAL MATCH (d2)-[:based_on]->(t:Ticket) "
        "OPTIONAL MATCH (d2)-[:based_on]->(m:Meeting) "
        "RETURN d.id, d2.id, d2.title, "
        "coalesce(d2.decided_on, m.date, t.closed, t.opened, d2.created_at, 'unknown')",
        dataset_name=target_dataset,
    )
    superseded_map: dict[str, list[dict[str, Any]]] = {}
    superseding_decision_ids: set[str] = set()
    for row in superseded_raw:
        if not row or not row[0]:
            continue
        target_id = str(row[0])
        sup_id = str(row[1])
        sup_title = str(row[2])
        sup_when = str(row[3])
        superseded_map.setdefault(target_id, []).append(
            {"id": sup_id, "title": sup_title, "when": sup_when}
        )
        superseding_decision_ids.add(target_id)

    # 3. Check CONTRADICTED decisions
    # (d)-[:contradicts]-(d2) where d2 is NOT itself superseded
    contradicts_raw = await query_graph(
        "MATCH (d:Decision)-[:contradicts]-(d2:Decision) "
        "OPTIONAL MATCH (d2)-[:decided_by]->(p2:Person) "
        "RETURN d.id, d2.id, d2.title, p2.name",
        dataset_name=target_dataset,
    )
    contradicted_map: dict[str, list[dict[str, Any]]] = {}
    for row in contradicts_raw:
        if not row or not row[0]:
            continue
        d_id = str(row[0])
        d2_id = str(row[1])
        d2_title = str(row[2])
        d2_decider = str(row[3]) if row[3] else "Unknown"

        # Check if d2 is itself superseded
        if d2_id in superseded_map:
            continue

        contradicted_map.setdefault(d_id, []).append(
            {"id": d2_id, "title": d2_title, "decided_by": d2_decider}
        )

    # 4. Check POSSIBLY STALE:
    # A. System owner has left the company
    # (d)-[:about_system]->(s:System)<-[:owns]-(p:Person) where p.is_active = false or leave_date in past
    departed_owners_raw = await query_graph(
        "MATCH (d:Decision)-[:about_system]->(s:System)<-[:owns]-(p:Person) "
        "WHERE p.is_active = false "
        "   OR (p.leave_date IS NOT NULL AND p.leave_date <> '' AND p.leave_date <= $today) "
        "RETURN d.id, s.name, p.name, p.leave_date",
        dataset_name=target_dataset,
        params={"today": ref_date_str},
    )
    departed_system_owners: dict[str, dict[str, Any]] = {}
    for row in departed_owners_raw:
        if not row or not row[0]:
            continue
        d_id = str(row[0])
        departed_system_owners[d_id] = {
            "system": str(row[1]),
            "owner": str(row[2]),
            "leave_date": str(row[3]) if row[3] else "past",
        }

    # B. Decision age & system update recency
    # Group decisions by system to find latest decision date per system
    system_latest_date: dict[str, datetime] = {}
    for d in decisions.values():
        sys = d["system"]
        if sys:
            dt = d["datetime"]
            if sys not in system_latest_date or dt > system_latest_date[sys]:
                system_latest_date[sys] = dt

    # 5. Classify each decision with precedence: superseded -> contradicted -> possibly_stale -> active
    health_results: dict[str, DecisionHealthInfo] = {}

    for d_id, d in decisions.items():
        title = d["title"]
        sys = d["system"]
        decider = d["decided_by"]
        d_dt = d["datetime"]

        # Rule 1: Superseded
        if d_id in superseded_map:
            sup_info = superseded_map[d_id][0]
            reason = f"Superseded by '{sup_info['title']}' (date: {sup_info['when']})"
            health_results[d_id] = DecisionHealthInfo(
                id=d_id,
                title=title,
                status="superseded",
                reason=reason,
                system=sys,
                decided_by=decider,
                details={"superseded_by": superseded_map[d_id]},
            )
            continue

        # Rule 2: Contradicted
        if d_id in contradicted_map and contradicted_map[d_id]:
            con_info = contradicted_map[d_id][0]
            reason = f"Contradicted by '{con_info['title']}' decided by {con_info['decided_by']}"
            health_results[d_id] = DecisionHealthInfo(
                id=d_id,
                title=title,
                status="contradicted",
                reason=reason,
                system=sys,
                decided_by=decider,
                details={"contradicted_by": contradicted_map[d_id]},
            )
            continue

        # Rule 3: Possibly Stale
        # Sub-rule 3a: System owner departed
        if d_id in departed_system_owners:
            dep_info = departed_system_owners[d_id]
            reason = (
                f"System owner '{dep_info['owner']}' has left the company "
                f"(leave_date: {dep_info['leave_date']}) for system '{dep_info['system']}'"
            )
            health_results[d_id] = DecisionHealthInfo(
                id=d_id,
                title=title,
                status="possibly_stale",
                reason=reason,
                system=sys,
                decided_by=decider,
                details={"owner_departed": dep_info},
            )
            continue

        # Sub-rule 3b: Decision older than stale_days with no newer decision for that system
        days_old = (ref_dt - d_dt).days
        if days_old > stale_days:
            # Check if there is a newer decision for the same system
            latest_sys_dt = system_latest_date.get(sys or "", d_dt)
            if latest_sys_dt <= d_dt:
                reason = (
                    f"Decision is {days_old} days old (older than {stale_days} days) "
                    f"with no newer decision recorded for system '{sys or 'N/A'}'"
                )
                health_results[d_id] = DecisionHealthInfo(
                    id=d_id,
                    title=title,
                    status="possibly_stale",
                    reason=reason,
                    system=sys,
                    decided_by=decider,
                    details={"days_old": days_old, "stale_threshold_days": stale_days},
                )
                continue

        # Rule 4: Active
        health_results[d_id] = DecisionHealthInfo(
            id=d_id,
            title=title,
            status="active",
            reason="Active decision with active system ownership and no conflicting or superseding decisions.",
            system=sys,
            decided_by=decider,
            details={"days_old": max(0, (ref_dt - d_dt).days)},
        )

    return health_results


async def get_decision_health(
    decision_id: str,
    dataset_name: Optional[str] = None,
    stale_days: int = 180,
) -> Optional[DecisionHealthInfo]:
    """Get health status for a specific decision by ID."""
    all_health = await evaluate_graph_health(dataset_name=dataset_name, stale_days=stale_days)
    return all_health.get(decision_id)
