"""People: decisions made, systems owned (orphaned when they have left), teams and projects."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas import PersonDetail, PersonSummary
from app.brain.codes import get_decision_codes_cached
from app.brain.health import get_health_map, is_departed
from app.brain.trace import CypherTrace
from app.config import get_settings

router = APIRouter(prefix="/people", tags=["People"])
_settings = get_settings()

_PEOPLE_QUERY = (
    "MATCH (p:Person) {where}"
    "OPTIONAL MATCH (p)-[:member_of]->(t:Team) "
    "OPTIONAL MATCH (p)-[:owns]->(s:System) "
    "OPTIONAL MATCH (d:Decision)-[:decided_by]->(p) "
    "RETURN properties(p), collect(DISTINCT t.name), collect(DISTINCT s.name), count(DISTINCT d)"
)


_PERSON_DECISIONS_QUERY = (
    "MATCH (d:Decision)-[:decided_by]->(p:Person) WHERE toLower(p.name) = toLower($name) "
    "OPTIONAL MATCH (d)-[:decided_by]->(co:Person) "
    "WITH d, collect(DISTINCT co.name) AS deciders "
    "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
    "RETURN d.id, d.title, d.decided_on, deciders, collect(DISTINCT s.name) "
    "ORDER BY d.decided_on"
)

_PERSON_ACTIVITY_QUERY = (
    "MATCH (p:Person) WHERE toLower(p.name) = toLower($name) "
    "OPTIONAL MATCH (p)-[:leads]->(lt:Team) "
    "WITH p, collect(DISTINCT lt.name) AS teams_led "
    "OPTIONAL MATCH (p)-[:leads]->(lp:Project) "
    "WITH p, teams_led, collect(DISTINCT lp.name) AS projects_led "
    "OPTIONAL MATCH (raised:Ticket)-[:raised_by]->(p) "
    "WITH p, teams_led, projects_led, count(DISTINCT raised) AS raised "
    "OPTIONAL MATCH (assigned:Ticket)-[:assigned_to]->(p) "
    "WITH p, teams_led, projects_led, raised, count(DISTINCT assigned) AS assigned "
    "OPTIONAL MATCH (m:Meeting)-[:attended_by]->(p) "
    "RETURN teams_led, projects_led, raised, assigned, count(DISTINCT m)"
)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _summary(row: list[Any], today: str) -> Optional[dict[str, Any]]:
    props = dict(row[0] or {})
    if not props.get("name"):
        return None
    return {
        "name": str(props["name"]),
        "role": props.get("role") or None,
        "departed": is_departed(props.get("is_active"), props.get("leave_date"), today),
        "leave_date": props.get("leave_date") or None,
        "teams": sorted({str(x) for x in (row[1] or []) if x}),
        "systems_owned": sorted({str(x) for x in (row[2] or []) if x}),
        "decision_count": int(row[3] or 0),
        "_props": props,
    }


@router.get("", response_model=list[PersonSummary])
async def list_people(
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> list[PersonSummary]:
    """Everyone, with teams, systems owned, decision count and whether they have left."""
    dataset = dataset_name or _settings.DATASET_NAME
    rows = await CypherTrace(dataset).run("people", _PEOPLE_QUERY.format(where=""))
    today = _today()
    items = [s for s in (_summary(r, today) for r in rows if r) if s]
    items.sort(key=lambda p: (-p["decision_count"], p["name"]))
    return [PersonSummary(**{k: v for k, v in p.items() if k != "_props"}) for p in items]


@router.get("/{name}", response_model=PersonDetail)
async def get_person(
    name: str,
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> PersonDetail:
    """A person's decisions (oldest first), systems owned, teams led or joined, and activity."""
    dataset = dataset_name or _settings.DATASET_NAME
    trace = CypherTrace(dataset)
    params = {"name": name}
    (rows, decision_rows, activity), codes, health = await asyncio.gather(
        trace.gather(
            ("person", _PEOPLE_QUERY.format(where="WHERE toLower(p.name) = toLower($name) "), params),
            ("person_decisions", _PERSON_DECISIONS_QUERY, params),
            ("person_activity", _PERSON_ACTIVITY_QUERY, params),
        ),
        get_decision_codes_cached(dataset),
        get_health_map(dataset),
    )
    today = _today()
    found = [s for s in (_summary(r, today) for r in rows if r) if s]
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person '{name}' not found.")
    person = found[0]
    props = person.pop("_props")

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

    act = activity[0] if activity and activity[0] else [[], [], 0, 0, 0]

    return PersonDetail(
        **person,
        start_date=props.get("start_date") or None,
        email=props.get("email") or None,
        teams_led=sorted({str(x) for x in (act[0] or []) if x}),
        projects_led=sorted({str(x) for x in (act[1] or []) if x}),
        # A departed owner leaves every system they own orphaned
        owned=[{"name": s, "orphaned": person["departed"]} for s in person["systems_owned"]],
        decisions=decisions,
        tickets_raised=int(act[2] or 0),
        tickets_assigned=int(act[3] or 0),
        meetings_attended=int(act[4] or 0),
        cypher=trace.as_dict(),
    )
