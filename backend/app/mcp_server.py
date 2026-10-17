"""MCP server: the Company Brain as tools an agent can call (Streamable HTTP, mounted at /mcp).

Every tool is a thin wrapper over a service the web app already uses (the Ask pipeline, the
decision page builder, the health map, the systems list, live ingest), so an agent and the UI
always see the same answers. Tools return concise JSON with DEC codes and source references.
Six tools only read. `add_source` writes tagged demo data through the normal ingest pipeline
(single-run lock, 3/min rate limit, automatic reset after 10 idle minutes); set
MCP_READ_ONLY=true to disable it. Each call is rate limited per IP and logged to the /changes
feed as agent activity.
"""

import inspect
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal, Optional

from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from app.api import systems as systems_api
from app.api.rate_limiter import check_ingest_rate_limit, check_rate_limits
from app.askflow.pipeline import collect_ask
from app.brain.codes import get_decision_codes_cached
from app.brain.health import get_health_map
from app.brain.lineage import build_decision_detail
from app.brain.memory import query_graph
from app.config import get_settings
from app.ingest.live import INGEST_LOCK, IngestRequest, record_change, run_ingest

logger = logging.getLogger("decision_trace.mcp")
_settings = get_settings()

INSTRUCTIONS = (
    "Decision Trace is a company's decision memory: a knowledge graph of decisions, the people who "
    "made them, the systems they affect and the tickets or meeting notes they are based on. Use it "
    "to answer 'why did we decide X', 'what breaks if we change Y', 'who knows about Z' and 'what "
    "needs attention'. Decisions have stable codes like DEC-11; pass them to get_decision. Answers "
    "come from the graph with source references (TICK-105, meeting titles)."
)

mcp = FastMCP(
    "Decision Trace",
    instructions=INSTRUCTIONS,
    # Stateless: each request stands alone, so any Railway instance can serve it
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    # The app is served on a public hostname; the default only allows localhost
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_ToolFn = Callable[..., Awaitable[dict[str, Any]]]


def _dataset() -> str:
    return _settings.DATASET_NAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _client_request(ctx: Context) -> Any:
    return ctx.request_context.request


def logged(name: str, summarize: Callable[..., str], *, ingest: bool = False) -> Callable[[_ToolFn], _ToolFn]:
    """Rate limit the caller per IP, run the tool, and record it in the /changes feed."""

    def wrap(fn: _ToolFn) -> _ToolFn:
        async def inner(*args: Any, ctx: Context, **kwargs: Any) -> dict[str, Any]:
            request = _client_request(ctx)
            try:
                if request is not None:
                    (check_ingest_rate_limit if ingest else check_rate_limits)(request)
            except HTTPException as exc:
                raise ToolError(str(exc.detail)) from exc
            try:
                result = await fn(*args, **kwargs)
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001 - agents get a short message, details go to the log
                logger.exception("MCP tool %s failed", name)
                raise ToolError("The Company Brain could not complete that request. Try again in a moment.") from exc
            try:
                await record_change(_dataset(), {
                    "id": f"agent-{uuid.uuid4().hex[:12]}", "kind": "agent", "title": name,
                    "type": "mcp", "created_at": _now(), "summary": summarize(*args, **kwargs),
                })
            except Exception:  # noqa: BLE001 - logging a call must never fail the call
                logger.warning("Could not record MCP call %s in the change feed", name)
            return result

        # FastMCP builds the tool schema from the signature and injects `ctx` by its annotation
        sig = inspect.signature(fn)
        inner.__signature__ = sig.replace(parameters=[
            *sig.parameters.values(),
            inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context),
        ])
        inner.__annotations__ = {**getattr(fn, "__annotations__", {}), "ctx": Context}
        inner.__name__, inner.__doc__, inner.__module__ = fn.__name__, fn.__doc__, fn.__module__
        return inner

    return wrap


def _short(text: str, n: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _ask_payload(result: dict[str, Any], codes: dict[str, str]) -> dict[str, Any]:
    """The parts of an Ask result an agent needs: answer, primary decision, sources, evidence path."""
    primary_id = result.get("primary_decision_id")
    nodes = result["graph_path"]["nodes"]
    edges = result["graph_path"]["edges"]
    def name_of(n: dict[str, Any]) -> str:
        props = n.get("properties", {})
        return (props.get("decision_code") or codes.get(n["id"]) or codes.get(n["id"].split(":", 1)[-1])
                or props.get("name") or props.get("ticket_id") or props.get("title") or n["id"])

    label = {n["id"]: name_of(n) for n in nodes}
    return {
        "answer": result["answer"],
        "intent": result.get("intent"),
        "primary_decision": codes.get(primary_id) if primary_id else None,
        "citations": [{"type": c["type"], "id": c["id"], "title": c["title"]} for c in result["citations"]],
        # Compact: nodes as "Type: name", edges as "from -relation-> to"
        "graph_path": {
            "nodes": [f"{n['label']}: {label[n['id']]}" for n in nodes],
            "edges": [f"{label.get(e['source'], e['source'])} -{e['type']}-> {label.get(e['target'], e['target'])}"
                      for e in edges],
        },
    }


def _sections(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"title": s["title"], "total": s["total"],
         "items": [{"kind": i["kind"], "name": i["name"], "code": i.get("code"), "health": i.get("health")}
                   for i in s["items"]]}
        for s in result.get("sections", [])
    ]


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
@logged("ask", lambda question: _short(question))
async def ask(question: str) -> dict[str, Any]:
    """Ask a free-form question about the company's decisions and get a grounded answer with
    sources. Best for 'why did we choose X', 'who decided Y', 'what replaced Z' and 'do any
    decisions conflict'. Returns the answer, the primary decision (DEC code), citations (ticket IDs
    and meeting titles) and the evidence path through the graph. For impact or expertise questions
    prefer impact_of and who_knows, which return structured results."""
    result = await collect_ask(question, _dataset())
    codes = await get_decision_codes_cached(_dataset())
    return _ask_payload(result, codes)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
@logged("get_decision", lambda code: _short(code))
async def get_decision(code: str) -> dict[str, Any]:
    """Get one decision by DEC code (for example DEC-11), with its health (active, superseded,
    contradicted, possibly stale), why it has that health, who decided it, the systems it is about,
    the supersedes and contradicts lineage, and the sources it is based on with verbatim quotes."""
    detail = await build_decision_detail(code, dataset_name=_dataset())
    if detail is None:
        raise ToolError(f"Decision '{code}' not found. Use list_decisions to see valid DEC codes.")

    def ref(d: Any) -> dict[str, Any]:
        d = d if isinstance(d, dict) else d.model_dump()
        return {"code": d.get("decision_code"), "title": d["title"], "health": d.get("health")}

    lineage = detail["lineage"]
    lineage = lineage if isinstance(lineage, dict) else lineage.model_dump()
    return {
        "code": detail["decision_code"], "title": detail["title"], "status": detail["status"],
        "health": detail["health"], "health_reason": detail["health_reason"],
        "decided_on": detail.get("decided_on"), "decided_by": detail.get("decided_by"),
        "decider_departed": detail.get("decider_departed", False),
        "rationale": detail.get("rationale") or detail.get("summary"),
        "systems": detail.get("system_names") or detail.get("systems", []),
        "lineage": {k: [ref(d) for d in lineage.get(k, [])]
                    for k in ("supersedes", "superseded_by", "contradicts", "contradicted_by")},
        "sources": [{"type": s["type"] if isinstance(s, dict) else s.type,
                     "id": s["id"] if isinstance(s, dict) else s.id,
                     "title": s.get("title") if isinstance(s, dict) else s.title,
                     "date": s.get("date") if isinstance(s, dict) else s.date,
                     "quote": s.get("quote") if isinstance(s, dict) else s.quote}
                    for s in detail.get("sources", [])],
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
@logged("list_decisions", lambda status=None, system=None: _short(
    " · ".join(x for x in (f"status={status}" if status else "", f"system={system}" if system else "") if x)
    or "all decisions"))
async def list_decisions(
    status: Optional[Literal["active", "superseded", "contradicted", "possibly_stale"]] = None,
    system: Optional[str] = None,
) -> dict[str, Any]:
    """List decisions with their DEC code, title, health and deciders. Optionally filter by health
    status (active, superseded, contradicted, possibly_stale) and/or by system name (for example
    Kafka). Use this to find the DEC code to pass to get_decision."""
    from app.api.decisions import list_decisions as list_decisions_api

    rows = await list_decisions_api(system=system, person=None, health=status, limit=100, dataset_name=_dataset())
    return {"count": len(rows), "decisions": [
        {"code": d.decision_code, "title": d.title, "health": d.health, "reason": d.health_reason,
         "systems": d.systems, "decided_by": d.deciders, "decided_on": d.decided_on}
        for d in rows]}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
@logged("impact_of", lambda system: _short(system))
async def impact_of(system: str) -> dict[str, Any]:
    """What is affected if a system is dropped or changed: the decisions on it (and which are already
    superseded), the people to involve (owner first), the teams and projects, and open or recent
    tickets. Pass a system name such as Snowflake or Kafka. Returns a short summary plus the
    structured lists, each decision with its DEC code."""
    result = await collect_ask(f"What's affected if we drop {system}?", _dataset())
    codes = await get_decision_codes_cached(_dataset())
    return {**_ask_payload(result, codes), "affected": _sections(result)}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
@logged("who_knows", lambda topic: _short(topic))
async def who_knows(topic: str) -> dict[str, Any]:
    """Who to ask about a system or technology (for example Kafka). Returns people ranked by recorded
    evidence: decisions they made (weight 3), systems they own (3), meetings they attended (2) and
    tickets they worked on (1), with counts and the DEC codes, meetings and ticket IDs behind them.
    People who have left the company are flagged and ranked last."""
    result = await collect_ask(f"Who knows the most about {topic}?", _dataset())
    return {
        "answer": result["answer"],
        "experts": [
            {"name": e["name"], "role": e.get("role"), "departed": e["departed"], "score": e["score"],
             "evidence": e["evidence"], "decisions": e["decisions"], "meetings": e["meetings"],
             "tickets": e["tickets"]}
            for e in result.get("experts", [])[:5]
        ],
    }


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
@logged("find_conflicts", lambda: "decision conflicts and orphaned systems")
async def find_conflicts() -> dict[str, Any]:
    """What needs attention right now: pairs of decisions that contradict each other, and systems
    whose owner has left the company so nobody owns them. Takes no arguments."""
    dataset = _dataset()
    health, codes, systems = await _gather_all(
        get_health_map(dataset), get_decision_codes_cached(dataset),
        systems_api.list_systems(dataset_name=dataset),
    )
    pairs = await query_graph(
        "MATCH (a:Decision)-[:contradicts]->(b:Decision) RETURN a.id, a.title, b.id, b.title", dataset_name=dataset
    )
    conflicts = [
        {"decisions": [{"code": codes.get(str(r[0])), "title": r[1]}, {"code": codes.get(str(r[2])), "title": r[3]}],
         "reason": health[str(r[0])].reason if str(r[0]) in health else None}
        for r in pairs if r and r[0] and r[2]
    ]
    return {
        "conflicts": conflicts,
        "orphaned_systems": [
            {"system": s.name, "former_owner": s.owner.name if s.owner else None,
             "left_on": s.owner.leave_date if s.owner else None, "decisions": s.decision_count}
            for s in systems if s.orphaned
        ],
    }


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
                       "openWorldHint": False})
@logged("add_source", lambda type, title, date, text, participants=None: _short(f"{type}: {title}"), ingest=True)
async def add_source(
    type: Literal["meeting", "ticket", "announcement"],
    title: str,
    date: str,
    text: str,
    participants: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Add one new source document (meeting notes, a ticket or an announcement) to the Company Brain.
    The text is read, decisions and people are extracted, matched to existing systems and people,
    and judged against existing decisions for supersession or conflict. Returns the diff: what was
    created and which decisions changed health. Everything added is tagged as demo data and removed
    automatically after 10 idle minutes. `date` is YYYY-MM-DD; `text` is at most 5,000 characters.
    Runs one at a time and is limited to 3 per minute."""
    if _settings.MCP_READ_ONLY:
        raise ToolError("This server is read-only: add_source is disabled.")
    if INGEST_LOCK.locked():
        raise ToolError("Another ingest or reset is running. Try again in a moment.")
    try:
        req = IngestRequest(type=type, title=title, date=date, text=text, participants=participants or [])
    except ValueError as exc:
        raise ToolError(f"Invalid source: {exc}") from exc
    async with INGEST_LOCK:
        async for event in run_ingest(req, _dataset()):
            if event["event"] == "error":
                raise ToolError(event["data"]["message"])
            if event["event"] == "diff":
                return event["data"]
    raise ToolError("The ingest ended without a result.")


async def _gather_all(*aws: Awaitable[Any]) -> list[Any]:
    import asyncio

    return list(await asyncio.gather(*aws))
