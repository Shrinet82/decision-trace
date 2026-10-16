"""Decision page builder: lineage, system timeline, impact and subgraph, all via Cypher.

Every graph traversal here is a Cypher query (variable-length paths for supersedes chains,
multi-type 2-hop patterns for impact). Python only merges the result rows into a response and
records each query in a CypherTrace so the UI can show exactly what ran.
"""

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


async def resolve_decision_id(
    ref: str, trace: CypherTrace, codes: dict[str, str]
) -> Optional[str]:
    """Accept a DEC code, a decision id, or an exact title."""
    if _CODE.match(ref):
        wanted = ref.upper()
        return next((d_id for d_id, code in codes.items() if code.upper() == wanted), None)
    rows = await trace.run(
        "resolve",
        "MATCH (d:Decision) WHERE d.id = $ref OR d.title = $ref RETURN d.id LIMIT 1",
        {"ref": ref},
    )
    return str(rows[0][0]) if rows and rows[0] and rows[0][0] else None


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


async def build_decision_detail(ref: str, dataset_name: Optional[str] = None) -> Optional[dict]:
    """Assemble the full decision page payload, or None if the decision does not exist."""
    trace = CypherTrace(dataset_name)
    codes = await get_decision_codes_cached(dataset_name)
    health = await get_health_map(dataset_name)
    today = _today()

    d_id = await resolve_decision_id(ref, trace, codes)
    if not d_id:
        return None

    sub = _Subgraph()

    # 1. The decision, its deciders and its systems
    core = await trace.run(
        "decision",
        "MATCH (d:Decision {id: $id}) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "RETURN properties(d), collect(DISTINCT p {.name, .role, .is_active, .leave_date}), "
        "collect(DISTINCT s.name)",
        {"id": d_id},
    )
    if not core or not core[0] or not core[0][0]:
        return None
    d_props: dict[str, Any] = dict(core[0][0])
    deciders = [
        {
            "name": str(p["name"]),
            "role": p.get("role") or None,
            "departed": is_departed(p.get("is_active"), p.get("leave_date"), today),
            "leave_date": p.get("leave_date") or None,
        }
        for p in (core[0][1] or [])
        if p and p.get("name")
    ]
    deciders.sort(key=lambda p: p["name"])
    system_names = sorted({str(s) for s in (core[0][2] or []) if s})

    focus_key = sub.node("Decision", d_props)
    for p in deciders:
        sub.edge(focus_key, "decided_by", sub.node("Person", {"name": p["name"]}))
    for s in system_names:
        sub.edge(focus_key, "about_system", sub.node("System", {"name": s}))

    # 2. Supersedes chains, followed fully in both directions
    down = await trace.run(
        "supersedes_chain",
        "MATCH path = (d:Decision {id: $id})-[:supersedes*1..%d]->(x:Decision) "
        "RETURN x.id, min(length(path))" % MAX_CHAIN_DEPTH,
        {"id": d_id},
    )
    up = await trace.run(
        "superseded_by_chain",
        "MATCH path = (d:Decision {id: $id})<-[:supersedes*1..%d]-(x:Decision) "
        "RETURN x.id, min(length(path))" % MAX_CHAIN_DEPTH,
        {"id": d_id},
    )
    supersedes_depth = {str(r[0]): int(r[1]) for r in down if r and r[0]}
    superseded_by_depth = {str(r[0]): int(r[1]) for r in up if r and r[0]}

    # 3. Contradictions, keeping edge direction
    conflict_rows = await trace.run(
        "contradictions",
        "MATCH (d:Decision {id: $id})-[r:contradicts]-(x:Decision) "
        "RETURN x.id, startNode(r).id = d.id",
        {"id": d_id},
    )
    contradicts_ids = [str(r[0]) for r in conflict_rows if r and r[0] and r[1]]
    contradicted_by_ids = [str(r[0]) for r in conflict_rows if r and r[0] and not r[1]]

    # 4. Other decisions on the same system(s)
    timeline_rows = await trace.run(
        "system_timeline",
        "MATCH (d:Decision {id: $id})-[:about_system]->(s:System)<-[:about_system]-(o:Decision) "
        "RETURN DISTINCT o.id",
        {"id": d_id},
    )
    timeline_ids = {str(r[0]) for r in timeline_rows if r and r[0]} | {d_id}

    lineage_ids = (
        {d_id}
        | set(supersedes_depth)
        | set(superseded_by_depth)
        | set(contradicts_ids)
        | set(contradicted_by_ids)
    )
    all_ids = sorted(lineage_ids | timeline_ids)

    # 5. Attributes of every referenced decision, in one query
    info_rows = await trace.run(
        "decision_attributes",
        "MATCH (x:Decision) WHERE x.id IN $ids "
        "OPTIONAL MATCH (x)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (x)-[:about_system]->(s:System) "
        "RETURN x.id, x.title, x.decided_on, collect(DISTINCT p.name), collect(DISTINCT s.name)",
        {"ids": all_ids},
    )
    info: dict[str, dict[str, Any]] = {}
    for r in info_rows:
        if not r or not r[0]:
            continue
        info[str(r[0])] = {
            "title": r[1],
            "decided_on": r[2],
            "deciders": sorted({str(x) for x in (r[3] or []) if x}),
            "systems": sorted({str(x) for x in (r[4] or []) if x}),
        }
        key = sub.node("Decision", {"id": str(r[0]), "title": r[1], "decided_on": r[2]})
        if str(r[0]) in timeline_ids:
            for s in info[str(r[0])]["systems"]:
                if s in system_names:
                    sub.edge(key, "about_system", sub.node("System", {"name": s}))

    # 6. Supersedes / contradicts edges among the lineage decisions
    chain_edges = await trace.run(
        "lineage_edges",
        "MATCH (a:Decision)-[r:supersedes|contradicts]->(b:Decision) "
        "WHERE a.id IN $ids AND b.id IN $ids RETURN a.id, type(r), b.id",
        {"ids": sorted(lineage_ids)},
    )
    for a, rel, b in (r for r in chain_edges if r and len(r) >= 3):
        sub.edge(f"Decision:{a}", str(rel), f"Decision:{b}")

    # 7. Sources of every lineage decision
    source_rows = await trace.run(
        "sources",
        "MATCH (x:Decision)-[:based_on]->(src) WHERE x.id IN $ids "
        "RETURN x.id, labels(src)[0], properties(src)",
        {"ids": sorted(lineage_ids)},
    )
    focus_sources: list[dict[str, Any]] = []
    for x_id, label, props in (r for r in source_rows if r and len(r) >= 3):
        props = dict(props or {})
        label = str(label)
        sub.edge(f"Decision:{x_id}", "based_on", sub.node(label, props))
        if str(x_id) == d_id and label in ("Ticket", "Meeting"):
            focus_sources.append(
                {
                    "type": "ticket" if label == "Ticket" else "meeting",
                    "id": str(props.get("ticket_id") if label == "Ticket" else props.get("title")),
                    "title": props.get("title"),
                    "date": props.get("closed") or props.get("opened") or props.get("date"),
                }
            )
    evidence_quote = d_props.get("evidence_quote") or None
    focus_sources.sort(key=lambda s: (s["type"] != "ticket", s["id"]))
    for src in focus_sources:
        # Quotes are stored per decision; only attribute one when there is a single source
        src["quote"] = evidence_quote if len(focus_sources) == 1 else None

    # 8. Impact: teams, projects and people within 2 hops of its systems
    impact_rows: list[Any] = []
    if system_names:
        impact_rows = await trace.run(
            "impact",
            "MATCH path = (s:System)-[:owns|member_of|leads|about_system|decided_by*1..2]-(x) "
            "WHERE s.name IN $systems AND (x:Person OR x:Team OR x:Project) "
            "UNWIND relationships(path) AS r "
            "RETURN DISTINCT labels(startNode(r))[0], properties(startNode(r)), type(r), "
            "labels(endNode(r))[0], properties(endNode(r))",
            {"systems": system_names},
        )
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
