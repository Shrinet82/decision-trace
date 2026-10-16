"""Decision Health Assessment Engine using OpenCypher over FalkorDB.

Computes decision health deterministically from graph edges and properties:
- superseded: incoming supersedes edge (reason: which decision, when)
- contradicted: contradicts edge with another decision that is not itself superseded (reason: which one, decided by whom)
- possibly_stale: a person who DECIDED it has left the company (leave_date in past or inactive),
  or the decision is older than a configurable number of days with no newer decision about its
  system. Superseded and contradicted decisions are never reported as stale.
- active: none of the above
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.brain.memory import query_graph, query_graph_threaded
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
    system: Optional[str] = Field(default=None, description="Associated system name(s)")
    decided_by: Optional[str] = Field(default=None, description="Decider name(s)")
    decider_departed: bool = Field(
        default=False,
        description="True if any person who decided this has left the company, whatever its health",
    )
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

    # The four whole-graph queries are independent: issue them together
    (
        decisions_raw,
        superseded_raw,
        contradicts_raw,
        departed_deciders_raw,
    ) = await asyncio.gather(
        query_graph_threaded(
            "MATCH (d:Decision) "
            "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
            "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
            "OPTIONAL MATCH (d)-[:based_on]->(t:Ticket) "
            "OPTIONAL MATCH (d)-[:based_on]->(m:Meeting) "
            "RETURN d.id, d.title, collect(DISTINCT s.name), collect(DISTINCT p.name), "
            "d.decided_on, collect(DISTINCT m.date), collect(DISTINCT t.closed), "
            "collect(DISTINCT t.opened), d.created_at",
            dataset_name=target_dataset,
        ),
        query_graph_threaded(
            "MATCH (d2:Decision)-[:supersedes]->(d:Decision) "
            "OPTIONAL MATCH (d2)-[:based_on]->(t:Ticket) "
            "OPTIONAL MATCH (d2)-[:based_on]->(m:Meeting) "
            "RETURN d.id, d2.id, d2.title, "
            "coalesce(d2.decided_on, m.date, t.closed, t.opened, d2.created_at, 'unknown')",
            dataset_name=target_dataset,
        ),
        query_graph_threaded(
            "MATCH (d:Decision)-[:contradicts]-(d2:Decision) "
            "OPTIONAL MATCH (d2)-[:decided_by]->(p2:Person) "
            "RETURN d.id, d2.id, d2.title, p2.name",
            dataset_name=target_dataset,
        ),
        query_graph_threaded(
            "MATCH (d:Decision)-[:decided_by]->(p:Person) "
            "WHERE p.is_active = false "
            "   OR (p.leave_date IS NOT NULL AND p.leave_date <> '' AND p.leave_date <= $today) "
            "RETURN d.id, p.name, p.leave_date",
            dataset_name=target_dataset,
            params={"today": ref_date_str},
        ),
    )

    # 1. Fetch all decisions with their systems, deciders, and dates

    decisions: dict[str, dict[str, Any]] = {}
    for row in decisions_raw:
        if not row or not row[0]:
            continue
        d_id = str(row[0])
        d_title = str(row[1]) if row[1] else "Untitled"
        systems = sorted({str(x) for x in (row[2] or []) if x})
        deciders = sorted({str(x) for x in (row[3] or []) if x})
        candidates = [row[4], *(row[5] or []), *(row[6] or []), *(row[7] or []), row[8]]
        d_date_str = next((str(c) for c in candidates if c), "2026-01-01")
        d_dt = _parse_date(d_date_str) or datetime(2026, 1, 1)

        decisions[d_id] = {
            "id": d_id,
            "title": d_title,
            "systems": systems,
            "system": ", ".join(systems) or None,
            "decided_by": ", ".join(deciders) or None,
            "date": d_date_str,
            "datetime": d_dt,
        }

    # 2. Check SUPERSEDED decisions via incoming supersedes edges
    # (d2)-[:supersedes]->(d)
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

    # 4. Check POSSIBLY STALE
    # A. A person who decided it has left the company:
    # (d)-[:decided_by]->(p:Person) where p.is_active = false or leave_date in the past
    departed_deciders: dict[str, list[dict[str, str]]] = {}
    for row in departed_deciders_raw:
        if not row or not row[0]:
            continue
        departed_deciders.setdefault(str(row[0]), []).append(
            {"person": str(row[1]), "leave_date": str(row[2]) if row[2] else "past"}
        )

    # B. Decision age & system update recency
    # Latest decision date per system, to tell whether a newer decision exists
    system_latest_date: dict[str, datetime] = {}
    for d in decisions.values():
        for sys_name in d["systems"]:
            dt = d["datetime"]
            if sys_name not in system_latest_date or dt > system_latest_date[sys_name]:
                system_latest_date[sys_name] = dt

    # 5. Classify each decision with precedence: superseded -> contradicted -> possibly_stale -> active
    health_results: dict[str, DecisionHealthInfo] = {}

    for d_id, d in decisions.items():
        title = d["title"]
        sys = d["system"]
        decider = d["decided_by"]
        d_dt = d["datetime"]
        departed = departed_deciders.get(d_id, [])
        decider_departed = bool(departed)

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
                decider_departed=decider_departed,
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
                decider_departed=decider_departed,
                details={"contradicted_by": contradicted_map[d_id]},
            )
            continue

        # Rule 3: Possibly Stale
        # Sub-rule 3a: a decider has left the company
        if departed:
            first = departed[0]
            reason = (
                f"Decider '{first['person']}' has left the company "
                f"(leave_date: {first['leave_date']})"
            )
            health_results[d_id] = DecisionHealthInfo(
                id=d_id,
                title=title,
                status="possibly_stale",
                reason=reason,
                system=sys,
                decided_by=decider,
                decider_departed=True,
                details={"deciders_departed": departed},
            )
            continue

        # Sub-rule 3b: Decision older than stale_days with no newer decision for that system
        days_old = (ref_dt - d_dt).days
        if days_old > stale_days:
            # Stale only if no newer decision exists for any of its systems
            latest_sys_dt = max(
                (system_latest_date.get(name, d_dt) for name in d["systems"]), default=d_dt
            )
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
                    decider_departed=False,
                    details={"days_old": days_old, "stale_threshold_days": stale_days},
                )
                continue

        # Rule 4: Active
        health_results[d_id] = DecisionHealthInfo(
            id=d_id,
            title=title,
            status="active",
            reason="Active decision; its deciders are still at the company and nothing conflicts with or supersedes it.",
            system=sys,
            decided_by=decider,
            decider_departed=False,
            details={"days_old": max(0, (ref_dt - d_dt).days)},
        )

    return health_results



def is_departed(is_active: Any, leave_date: Any, today: str) -> bool:
    """A person has left if marked inactive or their leave_date is on or before today."""
    if is_active is False or str(is_active).lower() == "false":
        return True
    return bool(leave_date) and str(leave_date) != "None" and str(leave_date)[:10] <= today


class SystemOrphanInfo(BaseModel):
    """A system whose owner (OWNS edge) has left the company."""

    system: str
    owner: str
    leave_date: Optional[str] = None


async def evaluate_system_orphans(
    dataset_name: Optional[str] = None, reference_date: Optional[str] = None
) -> dict[str, SystemOrphanInfo]:
    """Orphaned systems: (p:Person)-[:owns]->(s:System) where p has left the company."""
    target_dataset = dataset_name or _settings.DATASET_NAME
    ref_dt = _parse_date(reference_date) or datetime.now(timezone.utc).replace(tzinfo=None)
    rows = await query_graph(
        "MATCH (p:Person)-[:owns]->(s:System) "
        "WHERE p.is_active = false "
        "   OR (p.leave_date IS NOT NULL AND p.leave_date <> '' AND p.leave_date <= $today) "
        "RETURN s.name, p.name, p.leave_date",
        dataset_name=target_dataset,
        params={"today": ref_dt.strftime("%Y-%m-%d")},
    )
    return {
        str(r[0]): SystemOrphanInfo(
            system=str(r[0]), owner=str(r[1]), leave_date=str(r[2]) if r[2] else None
        )
        for r in rows
        if r and r[0]
    }


async def get_health_map(dataset_name: Optional[str] = None) -> dict[str, DecisionHealthInfo]:
    """evaluate_graph_health, cached for five minutes (it runs several whole-graph queries)."""
    from app.brain.cache import cached

    target = dataset_name or _settings.DATASET_NAME
    return await cached("health", target, 300, lambda: evaluate_graph_health(dataset_name=target))
