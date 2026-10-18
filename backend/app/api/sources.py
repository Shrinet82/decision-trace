"""Sources: every document the graph was built from (tickets, meeting notes, ingested documents) and
the organisational records loaded from company.db (people, teams, projects, systems)."""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.schemas import CypherTraceOut, HealthStatus
from app.askflow.assemble import norm_date
from app.brain import orgctx
from app.brain.cache import cached_endpoint
from app.brain.codes import get_decision_codes_cached
from app.brain.health import get_health_map, is_departed
from app.brain.trace import CypherTrace
from app.config import get_settings
from app.ingest.source_text import quote_in

router = APIRouter(prefix="/sources", tags=["Sources"])
_settings = get_settings()

SourceKind = Literal["ticket", "meeting", "document", "person", "team", "project", "system"]
_LABEL: dict[str, str] = {
    "ticket": "Ticket", "meeting": "Meeting", "document": "Document",
    "person": "Person", "team": "Team", "project": "Project", "system": "System",
}
_DOCUMENT_KINDS = {"ticket", "meeting", "document"}
# Properties that are bookkeeping rather than content
_HIDDEN = {"id", "body", "demo_ingest_id", "ingested_at", "demo_modified_by", "email"}

_DOCS_QUERY = (
    "MATCH (n) WHERE n:Ticket OR n:Meeting OR n:Document "
    "OPTIONAL MATCH (n)<-[:based_on]-(d:Decision) "
    "RETURN labels(n)[0], coalesce(n.ticket_id, n.title), n.title, "
    "coalesce(n.date, n.meeting_date, n.opened), n.status, n.demo_ingest_id, count(DISTINCT d)"
)
_RECORDS_QUERY = (
    "MATCH (n) WHERE (n:Person OR n:Team OR n:Project OR n:System) AND n.demo_ingest_id IS NULL "
    "OPTIONAL MATCH (n)-[:decided_by|about_system]-(d:Decision) "
    "RETURN labels(n)[0], n.name, coalesce(n.role, n.system_type, n.department, n.status), count(DISTINCT d)"
)
_DOC_DETAIL = (
    "MATCH (n:{label}) WHERE coalesce(n.ticket_id, n.title) = $key "
    "OPTIONAL MATCH (n)<-[bo:based_on]-(d:Decision) "
    "WITH n, collect(DISTINCT [d.id, d.title, bo.quote, d.evidence_quote]) AS decisions "
    "OPTIONAL MATCH (n)-[r:raised_by|assigned_to|attended_by]->(p:Person) "
    "WITH n, decisions, collect(DISTINCT [p.name, type(r), p.is_active, p.leave_date, p.role]) AS people "
    "OPTIONAL MATCH (n)<-[:based_on]-(:Decision)-[:decided_by]->(dp:Person) "
    "WITH n, decisions, people, collect(DISTINCT [dp.name, 'decided', dp.is_active, dp.leave_date, dp.role]) AS deciders "
    "OPTIONAL MATCH (n)-[:mentions]->(s:System) "
    "RETURN properties(n), decisions, people + deciders, collect(DISTINCT s.name)"
)
_RECORD_DETAIL = (
    "MATCH (n:{label}) WHERE n.name = $key "
    "OPTIONAL MATCH (n)-[:decided_by|about_system]-(d:Decision) "
    "WITH n, collect(DISTINCT [d.id, d.title, null, null]) AS decisions "
    "OPTIONAL MATCH (n)-[r:member_of|leads|owns]-(x) "
    "RETURN properties(n), decisions, collect(DISTINCT [labels(x)[0], x.name, type(r)])"
)


class SourceItem(BaseModel):
    kind: SourceKind
    key: str = Field(..., description="Ticket ID, meeting / document title, or record name")
    title: str
    detail: Optional[str] = Field(default=None, description="Ticket status, or a record's role / type")
    date: Optional[str] = None
    linked_decisions: int = 0
    demo: bool = Field(default=False, description="Added by a live demo ingest")


class SourceList(BaseModel):
    items: list[SourceItem] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict, description="Items per kind")


class SourceDecision(BaseModel):
    id: str
    decision_code: Optional[str] = None
    title: str
    health: HealthStatus = "active"
    quote: Optional[str] = Field(default=None, description="Verbatim evidence from this source")


class SourcePerson(BaseModel):
    name: str
    relation: str
    role: Optional[str] = None
    departed: bool = False


class SourceRelated(BaseModel):
    label: str
    name: str
    relation: str


class SourceDocument(BaseModel):
    kind: SourceKind
    key: str
    title: str
    date: Optional[str] = None
    status: Optional[str] = None
    text: Optional[str] = Field(default=None, description="Verbatim body (first 1,500 characters)")
    fields: dict[str, Any] = Field(default_factory=dict, description="Record fields (company.db rows)")
    decisions: list[SourceDecision] = Field(default_factory=list)
    people: list[SourcePerson] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    related: list[SourceRelated] = Field(default_factory=list)
    demo: bool = False
    cypher: CypherTraceOut = Field(default_factory=CypherTraceOut)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@router.get("", response_model=SourceList)
@cached_endpoint("sources.list_sources", 120.0)
async def list_sources(dataset_name: Optional[str] = Query(None)) -> SourceList:
    """All source documents and company.db records, with how many decisions each one backs."""
    trace = CypherTrace(dataset_name or _settings.DATASET_NAME)
    # In your own organization everything ingested is permanent, so records are not "demo" data
    records_query = _RECORDS_QUERY.replace(" AND n.demo_ingest_id IS NULL", "") if orgctx.current_graph() else _RECORDS_QUERY
    docs, records = await trace.gather(("documents", _DOCS_QUERY, {}), ("records", records_query, {}))
    items: list[SourceItem] = []
    for label, key, title, date, state, demo, linked in docs:
        if not key:
            continue
        items.append(SourceItem(kind=str(label).lower(), key=str(key), title=str(title or key), detail=state or None,
                                date=norm_date(date), linked_decisions=int(linked or 0), demo=bool(demo) and not orgctx.current_graph()))
    for label, name, detail, linked in records:
        if name:
            items.append(SourceItem(kind=str(label).lower(), key=str(name), title=str(name), detail=detail or None,
                                    linked_decisions=int(linked or 0)))
    order = {"ticket": 0, "meeting": 1, "document": 2, "system": 3, "person": 4, "team": 5, "project": 6}
    items.sort(key=lambda i: (order[i.kind], -(int((i.date or "0").replace("-", "")[:8] or 0)), i.key))
    counts: dict[str, int] = {}
    for i in items:
        counts[i.kind] = counts.get(i.kind, 0) + 1
    return SourceList(items=items, counts=counts)


@router.get("/{kind}/{key}", response_model=SourceDocument)
@cached_endpoint("sources.get_source", 120.0)
async def get_source(kind: SourceKind, key: str, dataset_name: Optional[str] = Query(None)) -> SourceDocument:
    """One source: full text with each linked decision's verbatim quote, plus people and systems.
    For a company.db record: its fields and what it is connected to."""
    dataset = dataset_name or _settings.DATASET_NAME
    trace = CypherTrace(dataset)
    label = _LABEL[kind]
    is_doc = kind in _DOCUMENT_KINDS
    query = (_DOC_DETAIL if is_doc else _RECORD_DETAIL).format(label=label)
    rows = await trace.run("source", query, {"key": key})
    if not rows or not rows[0] or not rows[0][0]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} '{key}' not found.")
    codes, health = await get_decision_codes_cached(dataset), await get_health_map(dataset)
    props = dict(rows[0][0])
    text = props.get("body") or None
    today = _today()

    decisions = []
    for d_id, d_title, edge_quote, evidence_quote in rows[0][1] or []:
        if not d_id:
            continue
        # Prefer the quote stored on this source's edge; fall back to the decision's quote only when
        # it is verbatim in this text
        quote = edge_quote or (evidence_quote if quote_in(evidence_quote, text) else None)
        h = health.get(str(d_id))
        decisions.append(SourceDecision(id=str(d_id), decision_code=codes.get(str(d_id)), title=str(d_title or d_id),
                                        health=h.status if h else "active", quote=quote))
    decisions.sort(key=lambda d: d.decision_code or d.title)

    doc = SourceDocument(
        kind=kind, key=key, title=str(props.get("title") or props.get("name") or key),
        date=norm_date(props.get("date") or props.get("meeting_date") or props.get("opened")),
        status=props.get("status") or None, text=text, decisions=decisions,
        demo=bool(props.get("demo_ingest_id")) and not orgctx.current_graph(), cypher=trace.as_dict(),
    )
    if is_doc:
        people: dict[str, SourcePerson] = {}
        for name, rel, is_active, leave_date, role in rows[0][2] or []:
            if not name:
                continue
            relation = {"raised_by": "raised", "assigned_to": "assignee", "attended_by": "attendee"}.get(rel, rel)
            if name in people:
                if relation not in people[name].relation.split(" · "):
                    people[name].relation += f" · {relation}"
            else:
                people[name] = SourcePerson(name=name, relation=relation, role=role or None,
                                            departed=is_departed(is_active, leave_date, today))
        doc.people = list(people.values())
        doc.systems = sorted({str(s) for s in rows[0][3] or [] if s})
    else:
        doc.fields = {k: v for k, v in sorted(props.items()) if k not in _HIDDEN and v not in (None, "")}
        doc.related = [SourceRelated(label=str(lbl), name=str(n), relation=str(r))
                       for lbl, n, r in rows[0][2] or [] if n]
    return doc
