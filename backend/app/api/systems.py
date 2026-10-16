"""Systems: ownership (with orphaned flag), decisions timeline, people and teams."""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas import SystemDetail, SystemSummary
from app.brain.codes import get_decision_codes_cached
from app.brain.health import evaluate_system_orphans, get_health_map, is_departed
from app.brain.trace import CypherTrace
from app.config import get_settings

router = APIRouter(prefix="/systems", tags=["Systems"])
_settings = get_settings()

_SYSTEM_QUERY = (
    "MATCH (s:System) {where}"
    "OPTIONAL MATCH (s)<-[:owns]-(o:Person) "
    "OPTIONAL MATCH (s)<-[:about_system]-(d:Decision) "
    "OPTIONAL MATCH (s)<-[:mentions]-(t:Ticket) "
    "RETURN s.name, s.system_type, s.vendor, "
    "collect(DISTINCT o {{.name, .role, .is_active, .leave_date}}), "
    "count(DISTINCT d), count(DISTINCT t)"
)
_TEAMS_QUERY = (
    "MATCH (s:System)<-[:owns|about_system]-(x) {where}"
    "MATCH (x)-[:decided_by*0..1]->(p:Person)-[:member_of|leads]->(team:Team) "
    "RETURN s.name, collect(DISTINCT team.name)"
)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _owner(rows: list[dict[str, Any]], today: str) -> Optional[dict[str, Any]]:
    owners = [o for o in rows or [] if o and o.get("name")]
    if not owners:
        return None
    o = sorted(owners, key=lambda o: o["name"])[0]
    return {
        "name": str(o["name"]),
        "role": o.get("role") or None,
        "departed": is_departed(o.get("is_active"), o.get("leave_date"), today),
        "leave_date": o.get("leave_date") or None,
    }


async def _summaries(
    trace: CypherTrace, dataset: str, name: Optional[str] = None
) -> list[dict[str, Any]]:
    where = "WHERE toLower(s.name) = toLower($name) " if name else ""
    params = {"name": name} if name else {}
    rows = await trace.run("systems", _SYSTEM_QUERY.format(where=where), params)
    team_rows = await trace.run("system_teams", _TEAMS_QUERY.format(where=where), params)
    teams = {str(r[0]): sorted({str(t) for t in (r[1] or []) if t}) for r in team_rows if r}
    orphans = await evaluate_system_orphans(dataset_name=dataset)
    today = _today()

    out = []
    for r in rows:
        if not r or not r[0]:
            continue
        sys_name = str(r[0])
        out.append(
            {
                "name": sys_name,
                "system_type": r[1] or None,
                "vendor": r[2] or None,
                "owner": _owner(r[3], today),
                "orphaned": sys_name in orphans,
                "decision_count": int(r[4] or 0),
                "ticket_count": int(r[5] or 0),
                "teams": teams.get(sys_name, []),
            }
        )
    return out


@router.get("", response_model=list[SystemSummary])
async def list_systems(
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> list[SystemSummary]:
    """Every system with its owner, orphaned flag, and decision/ticket counts.
    Orphaned systems first, then by number of decisions."""
    dataset = dataset_name or _settings.DATASET_NAME
    items = await _summaries(CypherTrace(dataset), dataset)
    items.sort(key=lambda s: (not s["orphaned"], -s["decision_count"], s["name"].lower()))
    return [SystemSummary(**s) for s in items]


@router.get("/{name}", response_model=SystemDetail)
async def get_system(
    name: str,
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> SystemDetail:
    """A system's owner, orphaned flag, decisions (oldest first), people and teams."""
    dataset = dataset_name or _settings.DATASET_NAME
    trace = CypherTrace(dataset)
    found = await _summaries(trace, dataset, name)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"System '{name}' not found.")
    summary = found[0]
    sys_name = summary["name"]

    codes = await get_decision_codes_cached(dataset)
    health = await get_health_map(dataset)
    decision_rows = await trace.run(
        "system_decisions",
        "MATCH (s:System {name: $name})<-[:about_system]-(d:Decision) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:about_system]->(s2:System) "
        "RETURN d.id, d.title, d.decided_on, collect(DISTINCT p.name), collect(DISTINCT s2.name) "
        "ORDER BY d.decided_on",
        {"name": sys_name},
    )
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

    people_rows = await trace.run(
        "system_people",
        "MATCH (s:System {name: $name}) "
        "OPTIONAL MATCH (s)<-[:owns]-(o:Person) "
        "OPTIONAL MATCH (s)<-[:about_system]-(:Decision)-[:decided_by]->(dp:Person) "
        "OPTIONAL MATCH (s)<-[:mentions]-(t:Ticket)-[:raised_by|assigned_to]->(tp:Person) "
        "RETURN collect(DISTINCT o {.name, .role, .is_active, .leave_date}), "
        "collect(DISTINCT dp {.name, .role, .is_active, .leave_date}), "
        "collect(DISTINCT [tp.name, tp.role, tp.is_active, tp.leave_date, t.ticket_id])",
        {"name": sys_name},
    )
    today = _today()
    people: dict[str, dict[str, Any]] = {}

    def add(name: Any, role: Any, active: Any, leave: Any, why: str) -> dict[str, Any]:
        entry = people.setdefault(
            str(name),
            {
                "name": str(name),
                "role": role or None,
                "departed": is_departed(active, leave, today),
                "leave_date": leave or None,
                "roles": [],
                "ticket_count": 0,
            },
        )
        if why not in entry["roles"]:
            entry["roles"].append(why)
        return entry

    if people_rows and people_rows[0]:
        owners, deciders, ticket_people = people_rows[0]
        for o in owners or []:
            if o and o.get("name"):
                add(o["name"], o.get("role"), o.get("is_active"), o.get("leave_date"), "owner")
        for p in deciders or []:
            if p and p.get("name"):
                add(p["name"], p.get("role"), p.get("is_active"), p.get("leave_date"), "decider")
        tickets_by_person: dict[str, set[str]] = {}
        for row in ticket_people or []:
            if row and row[0]:
                add(row[0], row[1], row[2], row[3], "tickets")
                tickets_by_person.setdefault(str(row[0]), set()).add(str(row[4]))
        for person, tickets in tickets_by_person.items():
            people[person]["ticket_count"] = len(tickets)

    order = {"owner": 0, "decider": 1, "tickets": 2}
    ranked = sorted(
        people.values(),
        key=lambda p: (min(order[r] for r in p["roles"]), -p["ticket_count"], p["name"]),
    )
    return SystemDetail(**summary, decisions=decisions, people=ranked, cypher=trace.as_dict())
