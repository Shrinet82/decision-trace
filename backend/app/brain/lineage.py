"""Decision page builder: lineage, system timeline, impact and subgraph, all via Cypher.

Every graph traversal here is a Cypher query (variable-length paths for supersedes chains,
multi-type 2-hop patterns for impact). Python only merges the result rows into a response and
records each query in a CypherTrace so the UI can show exactly what ran.
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.brain.codes import get_decision_codes_cached
from app.brain.health import DecisionHealthInfo, get_health_map, is_departed
from app.brain.trace import CypherTrace

_CODE = re.compile(r"^DEC-\d+$", re.IGNORECASE)
MAX_CHAIN_DEPTH = 10

# Properties kept on Decision nodes in the subgraph (summary/rationale would bloat it)
_DECISION_PROPS = ("id", "title", "decided_on", "status")


def node_key(label: str, props: dict[str, Any]) -> str:
    """Stable subgraph id: 'Decision:dec_x', 'Ticket:TICK-101', 'Meeting:<title>', else 'Label:name'."""
    if label == "Decision":
        key = props.get("id")
    elif label == "Ticket":
        key = props.get("ticket_id")
    elif label == "Meeting":
        key = props.get("title")
    else:
        key = props.get("name")
    return f"{label}:{key if key is not None else props.get('id', '?')}"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class _Subgraph:
    """Accumulates deduplicated nodes and edges."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    def node(self, label: str, props: dict[str, Any]) -> str:
        key = node_key(label, props)
        if label == "Decision":
            props = {k: props[k] for k in _DECISION_PROPS if k in props}
        if key in self.nodes:
            self.nodes[key]["properties"].update(props)
        else:
            self.nodes[key] = {"id": key, "label": label, "properties": dict(props)}
        return key

    def edge(self, source: str, rel_type: str, target: str) -> None:
        self.edges.setdefault(
            (source, rel_type, target),
            {"source": source, "target": target, "type": rel_type, "properties": {}},
        )

    def as_dict(self) -> dict[str, Any]:
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values())}


def _ref(
    d_id: str,
    info: dict[str, Any],
    codes: dict[str, str],
    health: dict[str, DecisionHealthInfo],
    **extra: Any,
) -> dict[str, Any]:
    h = health.get(d_id)
    return {
        "id": d_id,
        "decision_code": codes.get(d_id),
        "title": info.get("title") or "Untitled",
        "health": h.status if h else "active",
        "decided_on": info.get("decided_on"),
        "deciders": info.get("deciders", []),
        "systems": info.get("systems", []),
        **extra,
    }


_DECISION_QUERY = (
    "MATCH (d:Decision) WHERE d.id = $id "
    "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
    "WITH d, collect(DISTINCT p {.name, .role, .is_active, .leave_date}) AS deciders "
    "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
    "WITH d, deciders, collect(DISTINCT s.name) AS systems "
    "OPTIONAL MATCH down = (d)-[:supersedes*1..%(depth)d]->(older:Decision) "
    "WITH d, deciders, systems, collect(DISTINCT [older.id, length(down)]) AS supersedes "
    "OPTIONAL MATCH up = (d)<-[:supersedes*1..%(depth)d]-(newer:Decision) "
    "WITH d, deciders, systems, supersedes, collect(DISTINCT [newer.id, length(up)]) AS superseded_by "
    "OPTIONAL MATCH (d)-[c:contradicts]-(rival:Decision) "
    "WITH d, deciders, systems, supersedes, superseded_by, "
    "collect(DISTINCT [rival.id, startNode(c).id = d.id]) AS conflicts "
    "OPTIONAL MATCH (d)-[:about_system]->(:System)<-[:about_system]-(peer:Decision) "
    "RETURN properties(d), deciders, systems, supersedes, superseded_by, conflicts, "
    "collect(DISTINCT peer.id)"
) % {"depth": MAX_CHAIN_DEPTH}

# Finds the same decisions as the lineage query on its own (supersedes walk in either direction,
# conflicts, same-system peers), so all three statements can run in one round trip.
_RELATED_INDEPENDENT_QUERY = (
    "MATCH (d:Decision {id: $id}) "
    "OPTIONAL MATCH (d)-[:supersedes*0..%(depth)d]-(c:Decision) "
    "WITH d, collect(DISTINCT c) AS chain "
    "OPTIONAL MATCH (d)-[:contradicts]-(r:Decision) "
    "WITH d, chain, collect(DISTINCT r) AS rivals "
    "WITH d, chain + rivals AS lineage "
    "OPTIONAL MATCH (d)-[:about_system]->(:System)<-[:about_system]-(p:Decision) "
    "WITH lineage, collect(DISTINCT p) AS peers "
    "UNWIND (lineage + peers) AS x "
    "WITH DISTINCT x, [n IN lineage | n.id] AS lineage_ids "
    "OPTIONAL MATCH (x)-[:decided_by]->(pp:Person) "
    "WITH x, lineage_ids, collect(DISTINCT pp.name) AS deciders "
    "OPTIONAL MATCH (x)-[:about_system]->(s:System) "
    "WITH x, lineage_ids, deciders, collect(DISTINCT s.name) AS systems "
    "OPTIONAL MATCH (x)-[l:supersedes|contradicts]->(y:Decision) WHERE y.id IN lineage_ids "
    "WITH x, lineage_ids, deciders, systems, collect(DISTINCT [type(l), y.id]) AS links "
    "OPTIONAL MATCH (x)-[bo:based_on]->(src) WHERE x.id IN lineage_ids "
    "RETURN x.id, x.title, x.decided_on, x.evidence_quote, deciders, systems, links, "
    "collect(DISTINCT [labels(src)[0], properties(src), properties(bo)])"
) % {"depth": MAX_CHAIN_DEPTH}

_IMPACT_BY_DECISION_QUERY = (
    "MATCH (d:Decision {id: $id})-[:about_system]->(s:System) "
    "MATCH path = (s)-[:owns|member_of|leads|about_system|decided_by*1..2]-(x) "
    "WHERE x:Person OR x:Team OR x:Project "
    "UNWIND relationships(path) AS r "
    "RETURN DISTINCT labels(startNode(r))[0], properties(startNode(r)), type(r), "
    "labels(endNode(r))[0], properties(endNode(r))"
)

_SOURCE_TEXT_LIMIT = 1500


def _pairs(rows: Any) -> list[list[Any]]:
    """collect([a, b]) yields [null, null] when the OPTIONAL MATCH found nothing; drop those."""
    return [r for r in (rows or []) if r and r[0] is not None]


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _source_entry(label: str, props: dict[str, Any], edge: dict[str, Any]) -> dict[str, Any]:
    is_ticket = label == "Ticket"
    text = props.get("body") or None
    return {
        "type": "ticket" if is_ticket else ("meeting" if label == "Meeting" else "document"),
        "id": str(props.get("ticket_id") if is_ticket else props.get("title")),
        "title": props.get("title"),
        "date": props.get("closed") or props.get("opened") or props.get("date"),
        "quote": edge.get("quote") or None,
        "text": text[:_SOURCE_TEXT_LIMIT] if text else None,
    }


def attribute_quotes(sources: list[dict[str, Any]], evidence_quote: Optional[str]) -> None:
    """Fill missing per-source quotes from the decision-level quote, only where that is safe.

    Per-source quotes come from the BASED_ON edge. If an edge has none, the decision's quote is
    used for a source whose text contains it, or for the only source. Otherwise it stays unset.
    """
    if not evidence_quote:
        return
    missing = [s for s in sources if not s.get("quote")]
    if not missing:
        return
    needle = _norm(evidence_quote)
    containing = [s for s in missing if s.get("text") and needle and needle in _norm(s["text"])]
    if containing:
        for s in containing:
            s["quote"] = evidence_quote
    elif len(sources) == 1:
        sources[0]["quote"] = evidence_quote


async def build_decision_detail(ref: str, dataset_name: Optional[str] = None) -> Optional[dict]:
    """Assemble the full decision page payload, or None if the decision does not exist.

    Three Cypher statements: the decision with its whole lineage (one round trip), then the
    related decisions' attributes/edges/sources and the impact neighbourhood, concurrently.
    """
    trace = CypherTrace(dataset_name)
    codes, health = await asyncio.gather(
        get_decision_codes_cached(dataset_name), get_health_map(dataset_name)
    )
    today = _today()

    if _CODE.match(ref):
        wanted = ref.upper()
        d_id = next((i for i, code in codes.items() if code.upper() == wanted), None)
    else:
        by_title = {
            info.title: i for i, info in health.items() if getattr(info, "title", None)
        }
        d_id = ref if ref in codes else by_title.get(ref)
    if not d_id:
        return None

    sub = _Subgraph()

    # One round trip: the decision with its lineage, every related decision (attributes, links,
    # sources) and the impact neighbourhood, issued concurrently
    core, related_rows, impact_rows = await trace.gather(
        ("decision_and_lineage", _DECISION_QUERY, {"id": d_id}),
        ("related_decisions", _RELATED_INDEPENDENT_QUERY, {"id": d_id}),
        ("impact", _IMPACT_BY_DECISION_QUERY, {"id": d_id}),
    )
    if not core or not core[0] or not core[0][0]:
        return None
    d_props, decider_rows, system_rows, down, up, conflict_rows, peers = core[0]
    d_props = dict(d_props)
    deciders = sorted(
        (
            {
                "name": str(p["name"]),
                "role": p.get("role") or None,
                "departed": is_departed(p.get("is_active"), p.get("leave_date"), today),
                "leave_date": p.get("leave_date") or None,
            }
            for p in (decider_rows or [])
            if p and p.get("name")
        ),
        key=lambda p: p["name"],
    )
    system_names = sorted({str(s) for s in (system_rows or []) if s})
    supersedes_depth: dict[str, int] = {}
    for x_id, depth in _pairs(down):
        supersedes_depth[str(x_id)] = min(int(depth), supersedes_depth.get(str(x_id), 99))
    superseded_by_depth: dict[str, int] = {}
    for x_id, depth in _pairs(up):
        superseded_by_depth[str(x_id)] = min(int(depth), superseded_by_depth.get(str(x_id), 99))
    contradicts_ids = sorted({str(x) for x, outgoing in _pairs(conflict_rows) if outgoing})
    contradicted_by_ids = sorted({str(x) for x, outgoing in _pairs(conflict_rows) if not outgoing})
    timeline_ids = {str(x) for x in (peers or []) if x} | {d_id}

    focus_key = sub.node("Decision", d_props)
    for p in deciders:
        sub.edge(focus_key, "decided_by", sub.node("Person", {"name": p["name"]}))
    for s in system_names:
        sub.edge(focus_key, "about_system", sub.node("System", {"name": s}))

    lineage_ids = (
        {d_id}
        | set(supersedes_depth)
        | set(superseded_by_depth)
        | set(contradicts_ids)
        | set(contradicted_by_ids)
    )

    info: dict[str, dict[str, Any]] = {}
    focus_sources: list[dict[str, Any]] = []
    for row in related_rows:
        if not row or not row[0]:
            continue
        x_id, title, decided_on, quote, x_deciders, x_systems, links, sources = row
        x_id = str(x_id)
        # The undirected supersedes walk can reach chain siblings; keep only real members
        if x_id not in lineage_ids and x_id not in timeline_ids:
            continue
        info[x_id] = {
            "title": title,
            "decided_on": decided_on,
            "deciders": sorted({str(n) for n in (x_deciders or []) if n}),
            "systems": sorted({str(n) for n in (x_systems or []) if n}),
        }
        key = sub.node("Decision", {"id": x_id, "title": title, "decided_on": decided_on})
        if x_id in timeline_ids:
            for s in info[x_id]["systems"]:
                if s in system_names:
                    sub.edge(key, "about_system", sub.node("System", {"name": s}))
        for rel, target in _pairs(links):
            if str(target) in lineage_ids:
                sub.edge(key, str(rel), f"Decision:{target}")
        for label, props, edge in _pairs(sources) if x_id in lineage_ids else []:
            props, edge = dict(props or {}), dict(edge or {})
            sub.edge(key, "based_on", sub.node(str(label), props))
            if x_id == d_id and label in ("Ticket", "Meeting", "Document"):
                focus_sources.append(_source_entry(str(label), props, edge))

    evidence_quote = d_props.get("evidence_quote") or None
    focus_sources.sort(key=lambda s: (s["type"] != "ticket", s["id"]))
    attribute_quotes(focus_sources, evidence_quote)

    teams: set[str] = set()
    projects: set[str] = set()
    people: dict[str, dict[str, Any]] = {}
    for a_label, a_props, rel, b_label, b_props in (r for r in impact_rows if r and len(r) >= 5):
        a_props, b_props = dict(a_props or {}), dict(b_props or {})
        sub.edge(sub.node(str(a_label), a_props), str(rel), sub.node(str(b_label), b_props))
        for label, props in ((a_label, a_props), (b_label, b_props)):
            name = props.get("name")
            if not name:
                continue
            if label == "Team":
                teams.add(str(name))
            elif label == "Project":
                projects.add(str(name))
            elif label == "Person":
                people[str(name)] = {
                    "name": str(name),
                    "role": props.get("role") or None,
                    "departed": is_departed(props.get("is_active"), props.get("leave_date"), today),
                    "leave_date": props.get("leave_date") or None,
                }

    # Annotate decision nodes with code and health for the UI
    for key, node in sub.nodes.items():
        if node["label"] == "Decision":
            x_id = node["properties"].get("id")
            node["properties"]["decision_code"] = codes.get(x_id)
            h = health.get(x_id)
            node["properties"]["health"] = h.status if h else "active"

    h_info = health.get(d_id)
    title = d_props.get("title") or "Untitled"

    def refs(ids: list[str]) -> list[dict[str, Any]]:
        return [_ref(i, info.get(i, {}), codes, health) for i in ids]

    lineage = {
        "supersedes": sorted(
            (_ref(i, info.get(i, {}), codes, health, depth=dep) for i, dep in supersedes_depth.items()),
            key=lambda x: (x["depth"], x["decided_on"] or ""),
        ),
        "superseded_by": sorted(
            (_ref(i, info.get(i, {}), codes, health, depth=dep) for i, dep in superseded_by_depth.items()),
            key=lambda x: (x["depth"], x["decided_on"] or ""),
        ),
        "contradicts": refs(contradicts_ids),
        "contradicted_by": refs(contradicted_by_ids),
    }
    timeline = sorted(
        refs(sorted(timeline_ids)), key=lambda x: (x["decided_on"] or "9999", x["title"].lower())
    )

    return {
        "id": d_id,
        "decision_code": codes.get(d_id),
        "decider_departed": h_info.decider_departed if h_info else any(p["departed"] for p in deciders),
        "title": title,
        "summary": d_props.get("summary") or "",
        "rationale": d_props.get("rationale") or "",
        "status": d_props.get("status") or "accepted",
        "health": h_info.status if h_info else "active",
        "health_reason": h_info.reason if h_info else "Active decision.",
        "decided_on": d_props.get("decided_on"),
        "decided_by": ", ".join(p["name"] for p in deciders) or None,
        "people": sorted({p["name"] for p in deciders} | set(people)),
        "systems": system_names,
        "system_names": system_names,
        "sources": focus_sources,
        # Legacy title lists (direct neighbours), used by the Ask properties panel
        "supersedes": [x["title"] for x in lineage["supersedes"] if x["depth"] == 1],
        "superseded_by": [x["title"] for x in lineage["superseded_by"] if x["depth"] == 1],
        "contradicts": [x["title"] for x in lineage["contradicts"] + lineage["contradicted_by"]],
        "evidence_quote": evidence_quote,
        "deciders": deciders,
        "lineage": lineage,
        "timeline": timeline,
        "impact": {
            "teams": sorted(teams),
            "projects": sorted(projects),
            "people": sorted(people.values(), key=lambda p: p["name"]),
        },
        "subgraph": sub.as_dict(),
        "cypher": trace.as_dict(),
    }
