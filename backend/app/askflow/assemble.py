"""Pure assembly of Cypher rows into answers: evidence graph, sections, ranked experts, context.

Nothing here touches the database or the LLM, so every intent's shaping logic is unit-testable
with fixture rows. The Cypher that produces the rows lives in ``queries.py``.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.brain.health import is_departed

# Weights for "who knows about X" (decided and owns are the strongest signals)
EXPERTISE_WEIGHTS = {"decided": 3, "owns": 3, "meetings": 2, "tickets": 1}
MAX_PATH_NODES = 15


def _s(value: Any) -> Optional[str]:
    return str(value) if value not in (None, "") else None


_LOOSE_DATE = re.compile(r"^(\d{4})-0*(\d{1,2})-0*(\d{1,2})")


def norm_date(value: Any) -> Optional[str]:
    """YYYY-MM-DD from loosely padded dates in the source data (e.g. '2026-004-24')."""
    text = _s(value)
    if not text:
        return None
    m = _LOOSE_DATE.match(text)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else text


@dataclass
class EvidenceGraph:
    """Nodes and edges of the subgraph an answer is based on, with relevance weights."""

    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)
    _edge_keys: set[tuple[str, str, str]] = field(default_factory=set)
    # Sources reachable over based_on edges: the only things an answer may cite
    citations: dict[str, dict[str, str]] = field(default_factory=dict)

    def node(self, node_id: str, label: str, props: dict[str, Any], weight: float = 1.0) -> str:
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, "label": label, "properties": dict(props)}
        else:
            for k, v in props.items():
                self.nodes[node_id]["properties"].setdefault(k, v)
        self.weights[node_id] = max(self.weights.get(node_id, 0.0), weight)
        return node_id

    def edge(self, source: str, target: str, rel: str, props: Optional[dict[str, Any]] = None) -> None:
        key = (source, target, rel)
        if key not in self._edge_keys:
            self._edge_keys.add(key)
            self.edges.append({"source": source, "target": target, "type": rel, "properties": props or {}})

    def source(self, decision_id: str, label: str, key: str, title: Optional[str], date: Optional[str],
               weight: float = 6.0) -> None:
        """A decision's source document (Ticket, Meeting or ingested Document) and its citation."""
        if label == "Ticket":
            self.node(key, "Ticket", {"ticket_id": key, "title": title or key}, weight)
            self.citations[key] = {"type": "ticket", "id": key, "title": title or key}
        else:
            self.node(key, label, {"title": key, "date": date}, weight)
            self.citations[key] = {"type": label.lower(), "id": key, "title": key}
        self.edge(decision_id, key, "based_on")

    def capped(self, limit: int = MAX_PATH_NODES) -> dict[str, Any]:
        ranked = sorted(self.nodes.values(), key=lambda n: self.weights.get(n["id"], 0.0), reverse=True)
        kept = ranked[:limit]
        ids = {n["id"] for n in kept}
        return {
            "nodes": kept,
            "edges": [e for e in self.edges if e["source"] in ids and e["target"] in ids],
            "omitted_count": max(0, len(ranked) - len(kept)),
        }


def _person(p: dict[str, Any], today: str) -> dict[str, Any]:
    return {
        "name": str(p.get("name")),
        "role": _s(p.get("role")),
        "departed": is_departed(p.get("is_active"), p.get("leave_date"), today),
        "leave_date": _s(p.get("leave_date")),
    }


def _health(health: dict[str, Any], d_id: str) -> tuple[str, str]:
    h = health.get(d_id)
    return (h.status, h.reason) if h else ("active", "")


def _decision_props(d_id: str, title: str, codes: dict[str, str], health: dict[str, Any],
                    extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    status, _ = _health(health, d_id)
    return {"title": title, "decision_code": codes.get(d_id), "health": status, **(extra or {})}


def _code_list(ids: list[str], codes: dict[str, str]) -> str:
    return ", ".join(codes.get(i, i) for i in ids)


# ---------------------------------------------------------------------------------------------
# why / other: retrieval around the matched decisions and systems (the original /ask behaviour)
# ---------------------------------------------------------------------------------------------

@dataclass
class WhyResult:
    graph: EvidenceGraph
    context: list[str]
    main_decisions: dict[str, str]
    superseded_ids: set[str]
    statuses: dict[str, tuple[str, str]]  # id -> (title, extraction status)


def build_why(d_rows: list[list[Any]], owner_rows: list[list[Any]], codes: dict[str, str],
              health: dict[str, Any]) -> WhyResult:
    """Rows of WHY_BY_IDS / WHY_BY_SYSTEMS (one per decision x optional neighbour) and WHY_OWNERS."""
    g = EvidenceGraph()
    blocks: dict[str, list[str]] = {}
    main: dict[str, str] = {}
    superseded: set[str] = set()
    statuses: dict[str, tuple[str, str]] = {}

    for row in d_rows:
        if not row or not row[0]:
            continue
        (d_id, d_title, d_summary, d_rationale, d_status, decider, system, t_id, t_title, m_title,
         m_date, sup_id, sup_title, supby_id, supby_title, con_id, con_title, owner_name, owner_active,
         owner_leave) = (list(row) + [None] * 20)[:20]
        d_id, d_title, d_status = str(d_id), str(d_title), str(d_status or "accepted")
        statuses[d_id] = (d_title, d_status)
        health_status, health_reason = _health(health, d_id)
        g.node(d_id, "Decision", _decision_props(d_id, d_title, codes, health,
                                                  {"status": d_status, "rationale": str(d_rationale or "")}), 10.0)
        main.setdefault(d_id, d_title)
        block = blocks.get(d_id)
        if block is None:
            block = [f"Decision {codes.get(d_id, '')}: '{d_title}' (Status: {d_status}; "
                     f"current health: {health_status}{' - ' + health_reason if health_reason else ''})"]
            if d_summary:
                block.append(f"  Summary: {d_summary}")
            if d_rationale:
                block.append(f"  Rationale: {d_rationale}")
            blocks[d_id] = block

        def add(line: str) -> None:
            if line not in block:
                block.append(line)

        if decider:
            g.node(str(decider), "Person", {"name": str(decider)}, 8.0)
            g.edge(d_id, str(decider), "decided_by")
            add(f"  Decided by: {decider}")
        if system:
            g.node(str(system), "System", {"name": str(system)}, 8.0)
            g.edge(d_id, str(system), "about_system")
            add(f"  System: {system}")
            if owner_name:
                active = bool(owner_active) if owner_active is not None else True
                g.node(str(owner_name), "Person",
                       {"name": str(owner_name), "is_active": active, "leave_date": _s(owner_leave)}, 7.0)
                g.edge(str(owner_name), str(system), "owns")
                desc = "active" if active else f"departed (leave_date: {owner_leave})"
                add(f"  System Owner: {owner_name} ({desc})")
        if t_id:
            g.source(d_id, "Ticket", str(t_id), _s(t_title), None)
            add(f"  Source Ticket: {t_id} ('{t_title}')")
        if m_title:
            g.source(d_id, "Meeting", str(m_title), None, _s(m_date))
            add(f"  Source Meeting: {m_title} (Date: {m_date})")
        if sup_id and sup_title:
            g.node(str(sup_id), "Decision", _decision_props(str(sup_id), str(sup_title), codes, health), 5.0)
            g.edge(d_id, str(sup_id), "supersedes")
            add(f"  Supersedes: {codes.get(str(sup_id), '')} '{sup_title}'")
        if supby_id and supby_title:
            superseded.add(d_id)
            g.node(str(supby_id), "Decision", _decision_props(str(supby_id), str(supby_title), codes, health), 5.0)
            g.edge(str(supby_id), d_id, "supersedes")
            add(f"  Superseded by: {codes.get(str(supby_id), '')} '{supby_title}'")
        if con_id and con_title:
            g.node(str(con_id), "Decision", _decision_props(str(con_id), str(con_title), codes, health), 5.0)
            g.edge(d_id, str(con_id), "contradicts")
            add(f"  Contradicts: {codes.get(str(con_id), '')} '{con_title}'")

    ownership: list[str] = []
    for r in owner_rows:
        if not r or not r[0]:
            continue
        s_name, p_name = str(r[0]), _s(r[1])
        g.node(s_name, "System", {"name": s_name}, 8.0)
        if p_name:
            active = bool(r[2]) if r[2] is not None else True
            g.node(p_name, "Person", {"name": p_name, "is_active": active, "leave_date": _s(r[3])}, 7.5)
            g.edge(p_name, s_name, "owns")
            state = "active employee" if active else f"DEPARTED on {r[3]}"
            ownership.append(f"System Ownership: '{s_name}' is owned by {p_name} ({state}).")
    # Ownership facts first: they are short and easily buried under decision blocks
    context = ownership + ["\n".join(b) for b in blocks.values()]
    return WhyResult(g, context, main, superseded, statuses)


# ---------------------------------------------------------------------------------------------
# impact: what is affected if a system is dropped or changed
# ---------------------------------------------------------------------------------------------

@dataclass
class ImpactResult:
    graph: EvidenceGraph
    sections: list[dict[str, Any]]
    context: list[str]
    primary_decision_id: Optional[str]


def _sources(raw: Any) -> list[tuple[str, str, Optional[str], Optional[str]]]:
    """[label, key, title, date] rows from a collect(), skipping the null placeholder."""
    out = []
    for s in raw or []:
        if s and len(s) >= 2 and s[0] and s[1]:
            out.append((str(s[0]), str(s[1]), _s(s[2]) if len(s) > 2 else None, _s(s[3]) if len(s) > 3 else None))
    return out


def build_impact(system: str, decision_rows: list[list[Any]], people_rows: list[list[Any]],
                 ticket_rows: list[list[Any]], codes: dict[str, str], health: dict[str, Any],
                 today: str) -> ImpactResult:
    """Rows of IMPACT_DECISIONS, IMPACT_PEOPLE and IMPACT_TICKETS for one system."""
    g = EvidenceGraph()
    g.node(system, "System", {"name": system}, 8.0)

    # Decisions: those directly on the system, then the rest of their supersedes chains
    decisions: list[dict[str, Any]] = []
    for r in decision_rows:
        if not r or not r[0]:
            continue
        d_id, title, decided_on, deciders, systems, supersedes, contradicts, sources = (list(r) + [None] * 8)[:8]
        decisions.append({
            "id": str(d_id), "title": str(title or "Untitled"), "decided_on": _s(decided_on),
            "deciders": [d for d in (deciders or []) if d and d.get("name")],
            "systems": sorted({str(s) for s in (systems or []) if s}),
            "supersedes": sorted({str(s) for s in (supersedes or []) if s}),
            "contradicts": sorted({str(s) for s in (contradicts or []) if s}),
            "sources": _sources(sources),
        })
    direct = [d for d in decisions if system.lower() in (s.lower() for s in d["systems"])]
    chained = [d for d in decisions if d not in direct]
    direct.sort(key=lambda d: (d["decided_on"] or "", d["title"]))
    chained.sort(key=lambda d: (d["decided_on"] or "", d["title"]))
    ids = {d["id"] for d in decisions}
    superseded_by: dict[str, list[str]] = {}
    for d in decisions:
        for old in d["supersedes"]:
            superseded_by.setdefault(old, []).append(d["id"])

    # Primary: the most recent decision on the system that is still in force
    live = [d for d in direct if _health(health, d["id"])[0] != "superseded"] or direct
    primary = max(live, key=lambda d: (d["decided_on"] or "", d["title"]))["id"] if live else None

    people: dict[str, dict[str, Any]] = {}

    def person(p: dict[str, Any]) -> dict[str, Any]:
        info = _person(p, today)
        return people.setdefault(info["name"], {**info, "owner": False, "decided": [], "tickets": set()})

    decision_items, ctx_decisions = [], []
    for d in direct + chained:
        status, reason = _health(health, d["id"])
        is_direct = d in direct
        weight = 10.0 if d["id"] == primary else (9.0 if is_direct else 7.0)
        g.node(d["id"], "Decision", _decision_props(d["id"], d["title"], codes, health,
                                                    {"decided_on": d["decided_on"]}), weight)
        for s in d["systems"]:
            g.node(s, "System", {"name": s}, 8.0 if s.lower() == system.lower() else 4.0)
            g.edge(d["id"], s, "about_system")
        for old in d["supersedes"]:
            if old in ids:
                g.edge(d["id"], old, "supersedes")
        for other in d["contradicts"]:
            if other in ids:
                g.edge(d["id"], other, "contradicts")
        for label, key, title, date in d["sources"]:
            g.source(d["id"], label, key, title, date, weight=6.0 if is_direct else 4.0)
        for p in d["deciders"]:
            entry = person(p)
            entry["decided"].append(d["id"])
            g.node(entry["name"], "Person", {"name": entry["name"], "role": entry["role"]}, 5.0)
            g.edge(d["id"], entry["name"], "decided_by")

        relation = []
        if d["supersedes"]:
            relation.append(f"supersedes {_code_list(d['supersedes'], codes)}")
        if superseded_by.get(d["id"]):
            relation.append(f"superseded by {_code_list(superseded_by[d['id']], codes)}")
        if d["contradicts"]:
            relation.append(f"conflicts with {_code_list(d['contradicts'], codes)}")
        detail = ("on " + ", ".join(d["systems"])) if is_direct else "in a supersedes chain"
        if relation:
            detail += " · " + "; ".join(relation)
        decision_items.append({"kind": "decision", "name": d["title"], "id": d["id"], "code": codes.get(d["id"]),
                               "health": status, "detail": detail, "date": d["decided_on"]})
        deciders = ", ".join(p["name"] for p in d["deciders"]) or "unknown"
        srcs = ", ".join(k for _, k, _, _ in d["sources"]) or "none"
        ctx_decisions.append(
            f"- {codes.get(d['id'], d['id'])} '{d['title']}' ({d['decided_on'] or 'undated'}); "
            f"{'directly about ' + system if is_direct else 'related through a supersedes chain'}; "
            f"health: {status}{' - ' + reason if reason else ''}; decided by {deciders}; "
            f"{'; '.join(relation) + '; ' if relation else ''}sources: {srcs}"
        )

    # People and teams/projects within two hops (through the system's owner)
    team_items: dict[tuple[str, str], dict[str, Any]] = {}
    if people_rows and people_rows[0]:
        owners, ticket_people, team_rows = (list(people_rows[0]) + [None] * 3)[:3]
        for o in owners or []:
            if o and o.get("name"):
                entry = person(o)
                entry["owner"] = True
                g.node(entry["name"], "Person", {"name": entry["name"], "role": entry["role"],
                                                 "is_active": not entry["departed"],
                                                 "leave_date": entry["leave_date"]}, 6.0)
                g.edge(entry["name"], system, "owns")
        for row in ticket_people or []:
            if row and row[0]:
                entry = person({"name": row[0], "role": row[1], "is_active": row[2], "leave_date": row[3]})
                if row[4]:
                    entry["tickets"].add(str(row[4]))
        for row in team_rows or []:
            if row and row[0] and row[1]:
                label, name, via, rel = str(row[0]), str(row[1]), _s(row[2]), _s(row[3])
                item = team_items.setdefault((label, name), {
                    "kind": label.lower(), "name": name, "via": set(), "detail": None})
                if via:
                    item["via"].add(f"{via} ({'member' if rel == 'member_of' else 'lead'})")
                g.node(name, label, {"name": name}, 3.0)
                if via:
                    g.edge(via, name, rel or "member_of")

    def person_detail(p: dict[str, Any]) -> str:
        bits = []
        if p["owner"]:
            bits.append("owner")
        if p["decided"]:
            bits.append("decided " + _code_list(sorted(set(p["decided"]), key=lambda i: codes.get(i, i)), codes))
        if p["tickets"]:
            n = len(p["tickets"])
            bits.append(f"{n} ticket{'s' if n != 1 else ''}")
        return " · ".join(bits)

    ranked_people = sorted(
        people.values(),
        key=lambda p: (p["departed"], not p["owner"], -len(p["decided"]), -len(p["tickets"]), p["name"]),
    )
    people_items = [{"kind": "person", "name": p["name"], "detail": person_detail(p), "role": p["role"],
                     "departed": p["departed"], "leave_date": p["leave_date"]} for p in ranked_people]
    teams = [{"kind": t["kind"], "name": t["name"],
              "detail": ("via " + ", ".join(sorted(t["via"]))) if t["via"] else None}
             for t in sorted(team_items.values(), key=lambda t: (t["kind"], t["name"]))]

    # Tickets: open first, then the most recent closed ones
    tickets = []
    for r in ticket_rows:
        if r and r[0]:
            tickets.append({"kind": "ticket", "name": str(r[0]), "detail": _s(r[1]), "status": _s(r[2]),
                            "date": norm_date(r[3])})
    tickets.sort(key=lambda t: t["date"] or "", reverse=True)
    open_t = [t for t in tickets if (t["status"] or "").lower() != "closed"]
    closed_t = [t for t in tickets if (t["status"] or "").lower() == "closed"]
    shown_tickets = open_t + closed_t[: max(0, 6 - len(open_t))]
    for t in open_t:
        g.node(t["name"], "Ticket", {"ticket_id": t["name"], "title": t["detail"], "status": t["status"]}, 2.0)
        g.edge(t["name"], system, "mentions")

    sections = [
        {"key": "decisions", "title": "Decisions", "items": decision_items, "total": len(decision_items)},
        {"key": "people", "title": "People", "items": people_items, "total": len(people_items)},
        {"key": "teams", "title": "Teams & projects", "items": teams, "total": len(teams)},
        {"key": "tickets", "title": "Tickets", "items": shown_tickets, "total": len(tickets)},
    ]

    owner_names = [p for p in ranked_people if p["owner"]]
    context = [f"System under review: {system}"]
    if owner_names:
        context.append("Owner: " + ", ".join(
            f"{p['name']} ({'DEPARTED ' + (p['leave_date'] or '') if p['departed'] else 'active'})"
            for p in owner_names))
    else:
        context.append("Owner: none on record")
    context.append(f"Decisions affected ({len(decision_items)}):")
    context.extend(ctx_decisions or ["- none"])
    context.append(f"People to involve ({len(people_items)}):")
    context.extend(
        f"- {p['name']}{' (DEPARTED)' if p['departed'] else ''}: {person_detail(p)}" for p in ranked_people
    )
    context.append("Teams and projects within two hops: " + (
        "; ".join(f"{t['name']} ({t['kind']}{', ' + t['detail'] if t['detail'] else ''})" for t in teams) or "none"))
    context.append(f"Tickets mentioning {system}: {len(tickets)} ({len(open_t)} open)")
    context.extend(f"- {t['name']} [{t['status']}] opened {t['date']}: {t['detail']}" for t in shown_tickets)
    return ImpactResult(g, sections, context, primary)


# ---------------------------------------------------------------------------------------------
# expertise: who knows about a system
# ---------------------------------------------------------------------------------------------

def rank_experts(rows: list[list[Any]], codes: dict[str, str], today: str) -> list[dict[str, Any]]:
    """One EXPERTISE row: [decided, owns, meetings_by_source, meetings_by_mention, tickets], each a
    list of [person_map, evidence_key]. Returns people ranked by weighted evidence counts; people
    who have left are kept (flagged) but ranked after everyone still at the company."""
    if not rows or not rows[0]:
        return []
    decided, owns, meet_src, meet_text, tickets = (list(rows[0]) + [None] * 5)[:5]
    people: dict[str, dict[str, Any]] = {}

    def add(pairs: Any, kind: str) -> None:
        for pair in pairs or []:
            if not pair or not pair[0] or not pair[0].get("name"):
                continue
            info = _person(pair[0], today)
            entry = people.setdefault(info["name"], {**info, "_ev": {k: set() for k in EXPERTISE_WEIGHTS}})
            entry["_ev"][kind].add(str(pair[1]) if len(pair) > 1 and pair[1] is not None else info["name"])

    add(decided, "decided")
    add(owns, "owns")
    add(meet_src, "meetings")
    add(meet_text, "meetings")
    add(tickets, "tickets")

    experts = []
    for p in people.values():
        ev = p.pop("_ev")
        counts = {k: len(v) for k, v in ev.items()}
        experts.append({
            **p,
            "score": sum(EXPERTISE_WEIGHTS[k] * n for k, n in counts.items()),
            "evidence": counts,
            "decisions": sorted((codes.get(i, i) for i in ev["decided"])),
            "meetings": sorted(ev["meetings"]),
            "tickets": sorted(ev["tickets"]),
        })
    experts.sort(key=lambda e: (e["departed"], -e["score"], e["name"]))
    return experts


def expertise_graph(system: str, experts: list[dict[str, Any]], limit: int = 6) -> EvidenceGraph:
    g = EvidenceGraph()
    g.node(system, "System", {"name": system}, 8.0)
    for rank, e in enumerate(experts[:limit]):
        g.node(e["name"], "Person", {"name": e["name"], "role": e["role"], "is_active": not e["departed"],
                                     "leave_date": e["leave_date"]}, 7.0 - rank * 0.1)
        if e["evidence"]["owns"]:
            g.edge(e["name"], system, "owns")
    return g


def expertise_context(system: str, experts: list[dict[str, Any]], limit: int = 8) -> list[str]:
    w = EXPERTISE_WEIGHTS
    lines = [f"Topic: {system} (System)",
             f"People ranked by weighted evidence (decided={w['decided']}, owns={w['owns']}, "
             f"meeting attendee={w['meetings']}, ticket participant={w['tickets']}); "
             "people who left the company are listed last:"]
    for i, e in enumerate(experts[:limit], start=1):
        ev = e["evidence"]
        state = f"DEPARTED {e['leave_date'] or ''}".strip() if e["departed"] else "active"
        lines.append(
            f"{i}. {e['name']} ({e['role'] or 'role unknown'}, {state}): decided {ev['decided']}"
            f"{' (' + ', '.join(e['decisions']) + ')' if e['decisions'] else ''}, owns {ev['owns']}, "
            f"meetings {ev['meetings']}, tickets {ev['tickets']} -> weight {e['score']}"
        )
    if not experts:
        lines.append("No one has recorded evidence on this system.")
    return lines


# ---------------------------------------------------------------------------------------------
# status: health across all decisions, or ownership across all systems
# ---------------------------------------------------------------------------------------------

@dataclass
class StatusResult:
    graph: EvidenceGraph
    sections: list[dict[str, Any]]
    context: list[str]
    primary_decision_id: Optional[str]


_FOCUS_HEALTH = {"conflicts": ["contradicted"], "superseded": ["superseded"], "stale": ["possibly_stale"],
                 "overview": ["contradicted", "possibly_stale", "superseded"]}
_HEALTH_TITLE = {"contradicted": "Conflicts", "possibly_stale": "Possibly stale", "superseded": "Superseded"}


def build_status(focus: str, decision_rows: list[list[Any]], system_rows: list[list[Any]],
                 codes: dict[str, str], health: dict[str, Any], today: str) -> StatusResult:
    g = EvidenceGraph()
    sections: list[dict[str, Any]] = []
    context: list[str] = []
    primary: Optional[str] = None

    if focus == "ownership":
        orphaned, unowned = [], []
        for r in system_rows:
            if not r or not r[0]:
                continue
            name = str(r[0])
            owners = [_person(o, today) for o in (r[1] or []) if o and o.get("name")]
            if not owners:
                unowned.append({"kind": "system", "name": name, "detail": "no owner on record"})
                g.node(name, "System", {"name": name}, 7.0)
            elif all(o["departed"] for o in owners):
                o = owners[0]
                orphaned.append({"kind": "system", "name": name,
                                 "detail": f"owner {o['name']} left {o['leave_date'] or ''}".strip(),
                                 "departed": True})
                g.node(name, "System", {"name": name}, 8.0)
                g.node(o["name"], "Person", {"name": o["name"], "is_active": False, "leave_date": o["leave_date"]}, 7.0)
                g.edge(o["name"], name, "owns")
        total = sum(1 for r in system_rows if r and r[0])
        sections.append({"key": "orphaned", "title": "Owner has left", "items": orphaned, "total": len(orphaned)})
        sections.append({"key": "unowned", "title": "No owner on record", "items": unowned, "total": len(unowned)})
        context.append(f"Systems checked: {total}")
        context.append("Systems with NO ACTIVE OWNER because their owner has left the company: " + (
            "; ".join(f"{i['name']} ({i['detail']})" for i in orphaned) or "none"))
        context.append("Systems with no owner on record: " + (
            "; ".join(i["name"] for i in unowned) or "none"))
        context.append(f"Every other system ({total - len(orphaned) - len(unowned)}) has an active owner.")
        return StatusResult(g, sections, context, None)

    rows = {}
    for r in decision_rows:
        if r and r[0]:
            d_id, title, decided_on, deciders, systems, contradicts, supersedes, sources = (list(r) + [None] * 8)[:8]
            rows[str(d_id)] = {
                "id": str(d_id), "title": str(title or "Untitled"), "decided_on": _s(decided_on),
                "deciders": sorted({str(x) for x in (deciders or []) if x}),
                "systems": sorted({str(x) for x in (systems or []) if x}),
                "contradicts": sorted({str(x) for x in (contradicts or []) if x}),
                "supersedes": sorted({str(x) for x in (supersedes or []) if x}),
                "sources": _sources(sources),
            }
    superseded_by: dict[str, list[str]] = {}
    contradicted_by: dict[str, list[str]] = {}
    for d in rows.values():
        for o in d["supersedes"]:
            superseded_by.setdefault(o, []).append(d["id"])
        for o in d["contradicts"]:
            contradicted_by.setdefault(o, []).append(d["id"])

    counts: dict[str, int] = {}
    for d_id in rows:
        counts[_health(health, d_id)[0]] = counts.get(_health(health, d_id)[0], 0) + 1
    context.append(f"Decisions checked: {len(rows)} (" + ", ".join(
        f"{n} {s.replace('_', ' ')}" for s, n in sorted(counts.items())) + ")")

    def add_decision(d: dict[str, Any], weight: float) -> None:
        g.node(d["id"], "Decision", _decision_props(d["id"], d["title"], codes, health,
                                                    {"decided_on": d["decided_on"]}), weight)
        for p in d["deciders"]:
            g.node(p, "Person", {"name": p}, weight - 3)
            g.edge(d["id"], p, "decided_by")
        for s in d["systems"]:
            g.node(s, "System", {"name": s}, weight - 2)
            g.edge(d["id"], s, "about_system")
        for label, key, title, date in d["sources"]:
            g.source(d["id"], label, key, title, date, weight=weight - 1)

    for status in _FOCUS_HEALTH.get(focus, _FOCUS_HEALTH["overview"]):
        members = sorted((d for d in rows.values() if _health(health, d["id"])[0] == status),
                         key=lambda d: (d["decided_on"] or "", d["title"]))
        items = []
        for d in members:
            _, reason = _health(health, d["id"])
            rel = []
            if d["contradicts"] or contradicted_by.get(d["id"]):
                rel.append("conflicts with " + _code_list(d["contradicts"] + contradicted_by.get(d["id"], []), codes))
            if superseded_by.get(d["id"]):
                rel.append("superseded by " + _code_list(superseded_by[d["id"]], codes))
            if d["supersedes"]:
                rel.append("supersedes " + _code_list(d["supersedes"], codes))
            items.append({"kind": "decision", "name": d["title"], "id": d["id"], "code": codes.get(d["id"]),
                          "health": status, "detail": "; ".join(rel) or reason, "date": d["decided_on"]})
            add_decision(d, 9.0)
            for o in d["contradicts"]:
                if o in rows:
                    add_decision(rows[o], 9.0)
                    g.edge(d["id"], o, "contradicts")
            for newer in superseded_by.get(d["id"], []):
                add_decision(rows[newer], 7.0)
                g.edge(newer, d["id"], "supersedes")
            context.append(
                f"- [{_HEALTH_TITLE[status]}] {codes.get(d['id'], d['id'])} '{d['title']}' "
                f"({d['decided_on'] or 'undated'}), decided by {', '.join(d['deciders']) or 'unknown'}, "
                f"systems {', '.join(d['systems']) or 'none'}; {'; '.join(rel) or reason}; "
                f"sources: {', '.join(k for _, k, _, _ in d['sources']) or 'none'}"
            )
        sections.append({"key": status, "title": _HEALTH_TITLE[status], "items": items, "total": len(items)})
        if not items:
            context.append(f"- [{_HEALTH_TITLE[status]}] none")

    # Primary: the newer decision of the first conflict (it introduced the conflict)
    conflicts = [d for d in rows.values() if d["contradicts"]]
    if focus in ("conflicts", "overview") and conflicts:
        first = min(conflicts, key=lambda d: (d["decided_on"] or "", d["title"]))
        pair = [first] + [rows[o] for o in first["contradicts"] if o in rows]
        primary = max(pair, key=lambda d: (d["decided_on"] or "", d["title"]))["id"]
        g.weights[primary] = 10.0
    return StatusResult(g, sections, context, primary)


# ---------------------------------------------------------------------------------------------
# Citations: only real based_on sources that the answer text actually references
# ---------------------------------------------------------------------------------------------

def verified_citations(graph: EvidenceGraph, answer: str, limit: int = 5) -> list[dict[str, str]]:
    based_on = {e["target"] for e in graph.edges if e["type"] == "based_on"}
    text = answer.lower()
    cited = [
        c for c in graph.citations.values()
        if c["id"] in based_on and (c["id"].lower() in text or (len(c["title"]) > 5 and c["title"].lower() in text))
    ]
    cited.sort(key=lambda c: graph.weights.get(c["id"], 0.0), reverse=True)
    return cited[:limit]


def first_citation_index(graph: EvidenceGraph, citations: list[dict[str, str]],
                         decisions: dict[str, str]) -> dict[str, int]:
    order = {c["id"]: i for i, c in enumerate(citations)}
    out: dict[str, int] = {}
    for e in graph.edges:
        if e["type"] == "based_on" and e["target"] in order and e["source"] in decisions:
            i = order[e["target"]]
            out[e["source"]] = min(i, out.get(e["source"], i))
    return out
