"""The "needs attention" queue on the home page: conflicts, orphaned systems, possibly stale
decisions, and superseded decisions whose systems are still seeing new tickets. Each item carries
the reason it is on the list, and links to the page that explains it."""

from typing import Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.systems import list_systems
from app.brain.cache import cached_endpoint
from app.brain.codes import get_decision_codes_cached
from app.brain.health import get_health_map
from app.brain.memory import query_graph
from app.config import get_settings

router = APIRouter(tags=["Home"])
_settings = get_settings()

# Superseded decisions and the tickets about their systems opened after the replacement was made
_SUPERSEDED_QUERY = (
    "MATCH (d:Decision)<-[:supersedes]-(n:Decision) "
    "MATCH (d)-[:about_system]->(s:System)<-[:mentions]-(t:Ticket) "
    "WHERE t.opened > n.decided_on "
    "RETURN d.id, n.id, n.decided_on, s.name, collect(DISTINCT t.ticket_id)"
)
_CONFLICT_QUERY = "MATCH (a:Decision)-[:contradicts]->(b:Decision) RETURN a.id, b.id"


class AttentionItem(BaseModel):
    kind: Literal["conflict", "orphaned", "stale", "superseded"]
    title: str
    reason: str
    decision_code: Optional[str] = Field(default=None, description="Decision page to open")
    system: Optional[str] = Field(default=None, description="System page to open")


class Attention(BaseModel):
    items: list[AttentionItem] = Field(default_factory=list)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


@router.get("/attention", response_model=Attention)
@cached_endpoint("attention.attention", 120.0)
async def attention(
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> Attention:
    """What needs a person's attention now, most urgent first."""
    dataset = dataset_name or _settings.DATASET_NAME
    health, codes, systems, pairs, superseded = await _gather(
        get_health_map(dataset), get_decision_codes_cached(dataset), list_systems(dataset_name=dataset),
        query_graph(_CONFLICT_QUERY, dataset_name=dataset), query_graph(_SUPERSEDED_QUERY, dataset_name=dataset),
    )
    items: list[AttentionItem] = []

    seen: set[frozenset[str]] = set()
    for row in pairs:
        if not row or not row[0] or not row[1]:
            continue
        pair = frozenset((str(row[0]), str(row[1])))
        if pair in seen:
            continue
        seen.add(pair)
        a, b = sorted(pair, key=lambda i: codes.get(i, i))
        info = health.get(a)
        items.append(AttentionItem(
            kind="conflict", decision_code=codes.get(a),
            title=f"{codes.get(a, 'Decision')} and {codes.get(b, 'Decision')} conflict",
            reason=info.reason if info else "Two accepted decisions contradict each other.",
        ))

    for s in systems:
        if s.orphaned and s.owner:
            items.append(AttentionItem(
                kind="orphaned", system=s.name, title=f"{s.name} has no active owner",
                reason=f"{s.owner.name} left on {s.owner.leave_date}." if s.owner.leave_date
                else f"{s.owner.name} has left.",
            ))

    for d_id, info in sorted(health.items(), key=lambda kv: codes.get(kv[0], kv[0])):
        if info.status == "possibly_stale":
            items.append(AttentionItem(
                kind="stale", decision_code=codes.get(d_id),
                title=f"{codes.get(d_id, 'Decision')} may be out of date", reason=info.reason,
            ))

    by_decision: dict[str, tuple[str, str, set[str]]] = {}
    for row in superseded:
        if not row or not row[0]:
            continue
        d_id = str(row[0])
        _, _, tickets = by_decision.setdefault(d_id, (str(row[1]), str(row[2]), set()))
        tickets.update(str(t) for t in (row[4] or []) if t)
    for d_id, (new_id, when, tickets) in sorted(by_decision.items(), key=lambda kv: codes.get(kv[0], kv[0])):
        items.append(AttentionItem(
            kind="superseded", decision_code=codes.get(d_id),
            title=f"{codes.get(d_id, 'Decision')} was superseded but its system is still active",
            reason=f"Replaced by {codes.get(new_id, 'a newer decision')} on {when}; "
                   f"{_plural(len(tickets), 'ticket')} since ({', '.join(sorted(tickets)[:3])}).",
        ))
    return Attention(items=items)


async def _gather(*aws):  # noqa: ANN002, ANN202
    import asyncio

    return list(await asyncio.gather(*aws))
