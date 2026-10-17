"""Systems: ownership (with orphaned flag), decisions timeline, people and teams."""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas import SystemDetail, SystemSummary
from app.brain.cache import cached_endpoint
from app.brain.codes import get_decision_codes_cached
from app.brain.health import get_health_map, is_departed
from app.brain.trace import CypherTrace
from app.config import get_settings

router = APIRouter(prefix="/systems", tags=["Systems"])
_settings = get_settings()

# One row per system: owner(s), decision and ticket counts, and teams of its owners and deciders
_SYSTEMS_QUERY = (
    "MATCH (s:System) {where}"
    "OPTIONAL MATCH (s)<-[:owns]-(o:Person) "
    "WITH s, collect(DISTINCT o {{.name, .role, .is_active, .leave_date}}) AS owners "
    "OPTIONAL MATCH (s)<-[:about_system]-(d:Decision) "
    "WITH s, owners, count(DISTINCT d) AS decisions "
    "OPTIONAL MATCH (s)<-[:mentions]-(t:Ticket) "
    "WITH s, owners, decisions, count(DISTINCT t) AS tickets "
    "OPTIONAL MATCH (s)<-[:owns|about_system]-(x) "
    "OPTIONAL MATCH (x)-[:decided_by*0..1]->(:Person)-[:member_of|leads]->(team:Team) "
    "RETURN s.name, s.system_type, s.vendor, owners, decisions, tickets, "
    "collect(DISTINCT team.name)"
)
_WHERE_NAME = "WHERE toLower(s.name) = toLower($name) "

_DECISIONS_QUERY = (
    "MATCH (s:System)<-[:about_system]-(d:Decision) " + _WHERE_NAME +
    "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
    "WITH d, collect(DISTINCT p.name) AS deciders "
    "OPTIONAL MATCH (d)-[:about_system]->(s2:System) "
    "RETURN d.id, d.title, d.decided_on, deciders, collect(DISTINCT s2.name) "
    "ORDER BY d.decided_on"
)

_PEOPLE_QUERY = (
    "MATCH (s:System) " + _WHERE_NAME +
    "OPTIONAL MATCH (s)<-[:owns]-(o:Person) "
    "WITH s, collect(DISTINCT o {.name, .role, .is_active, .leave_date}) AS owners "
    "OPTIONAL MATCH (s)<-[:about_system]-(:Decision)-[:decided_by]->(dp:Person) "
    "WITH s, owners, collect(DISTINCT dp {.name, .role, .is_active, .leave_date}) AS deciders "
    "OPTIONAL MATCH (s)<-[:mentions]-(t:Ticket)-[:raised_by|assigned_to]->(tp:Person) "
    "RETURN owners, deciders, "
    "collect(DISTINCT [tp.name, tp.role, tp.is_active, tp.leave_date, t.ticket_id])"
)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _person(p: dict[str, Any], today: str) -> dict[str, Any]:
    return {
        "name": str(p["name"]),
        "role": p.get("role") or None,
        "departed": is_departed(p.get("is_active"), p.get("leave_date"), today),
        "leave_date": p.get("leave_date") or None,
    }


def _summary(row: list[Any], today: str) -> Optional[dict[str, Any]]:
    if not row or not row[0]:
        return None
    owners = sorted(
        (_person(o, today) for o in (row[3] or []) if o and o.get("name")), key=lambda o: o["name"]
    )
    owner = owners[0] if owners else None
    return {
        "name": str(row[0]),
        "system_type": row[1] or None,
        "vendor": row[2] or None,
        "owner": owner,
        # Orphaned: its owner has left (same rule as health.evaluate_system_orphans)
        "orphaned": bool(owners) and any(o["departed"] for o in owners),
        "decision_count": int(row[4] or 0),
        "ticket_count": int(row[5] or 0),
        "teams": sorted({str(t) for t in (row[6] or []) if t}),
    }


@router.get("", response_model=list[SystemSummary])
@cached_endpoint("systems.list_systems", 120.0)
async def list_systems(
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> list[SystemSummary]:
    """Every system with its owner, orphaned flag, and decision/ticket counts.
    Orphaned systems first, then by number of decisions. One Cypher query."""
    dataset = dataset_name or _settings.DATASET_NAME
    rows = await CypherTrace(dataset).run("systems", _SYSTEMS_QUERY.format(where=""))
    today = _today()
    items = [s for s in (_summary(r, today) for r in rows) if s]
    items.sort(key=lambda s: (not s["orphaned"], -s["decision_count"], s["name"].lower()))
    return [SystemSummary(**s) for s in items]


@router.get("/{name}", response_model=SystemDetail)
@cached_endpoint("systems.get_system", 120.0)
async def get_system(
    name: str,
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> SystemDetail:
    """A system's owner, orphaned flag, decisions (oldest first), people and teams.
    Three Cypher queries, run concurrently."""
    dataset = dataset_name or _settings.DATASET_NAME
    trace = CypherTrace(dataset)
    params = {"name": name}
    (summary_rows, decision_rows, people_rows), codes, health = await _gather(
        trace.gather(
            ("system", _SYSTEMS_QUERY.format(where=_WHERE_NAME), params),
            ("system_decisions", _DECISIONS_QUERY, params),
            ("system_people", _PEOPLE_QUERY, params),
        ),
        get_decision_codes_cached(dataset),
        get_health_map(dataset),
    )
    today = _today()
    found = [s for s in (_summary(r, today) for r in summary_rows) if s]
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"System '{name}' not found.")
    summary = found[0]

    decisions = []
    for r in decision_rows:
        if not r or not r[0]:
            continue
        h = health.get(str(r[0]))
        decisions.append(
            {
                "id": str(r[0]),
                "decision_code": codes.get(str(r[0])),
                "title": r[1] or "Untitled",
                "health": h.status if h else "active",
                "decided_on": r[2],
                "deciders": sorted({str(x) for x in (r[3] or []) if x}),
                "systems": sorted({str(x) for x in (r[4] or []) if x}),
            }
        )

    people: dict[str, dict[str, Any]] = {}

    def add(p: dict[str, Any], why: str) -> dict[str, Any]:
        entry = people.setdefault(p["name"], {**p, "roles": [], "ticket_count": 0})
        if why not in entry["roles"]:
            entry["roles"].append(why)
        return entry

    if people_rows and people_rows[0]:
        owners, deciders, ticket_people = people_rows[0]
        for o in owners or []:
            if o and o.get("name"):
                add(_person(o, today), "owner")
        for p in deciders or []:
            if p and p.get("name"):
                add(_person(p, today), "decider")
        tickets_by_person: dict[str, set[str]] = {}
        for row in ticket_people or []:
            if row and row[0]:
                person = {"name": row[0], "role": row[1], "is_active": row[2], "leave_date": row[3]}
                add(_person(person, today), "tickets")
                tickets_by_person.setdefault(str(row[0]), set()).add(str(row[4]))
        for person_name, tickets in tickets_by_person.items():
            people[person_name]["ticket_count"] = len(tickets)

    order = {"owner": 0, "decider": 1, "tickets": 2}
    ranked = sorted(
        people.values(),
        key=lambda p: (min(order[r] for r in p["roles"]), -p["ticket_count"], p["name"]),
    )
    return SystemDetail(**summary, decisions=decisions, people=ranked, cypher=trace.as_dict())


async def _gather(*aws: Any) -> list[Any]:
    import asyncio

    return list(await asyncio.gather(*aws))
