"""Live ingest: one pasted source in, a streamed pipeline out, ending in a graph diff.

Steps (each streamed): reading -> extracting_decisions (existing two-pass extractor prompts) ->
extracting_people (leaves / joins / owns) -> matching (to existing Person/System, no duplicates)
-> linking (LLM judge per new decision vs existing decisions on the same systems) -> writing ->
health (recompute, diff before/after).

Every node and edge created here carries {demo_ingest_id, ingested_at}. Changes to existing nodes
(a person leaving) are recorded with their previous values in the change log, so reset can delete
exactly the tagged data and restore those values, leaving untagged data untouched.
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.api.rate_limiter import record_llm_call
from app.brain import cache
from app.brain.codes import get_decision_codes
from app.brain.health import evaluate_graph_health, evaluate_system_orphans
from app.brain.memory import (
    build_pass1_prompt,
    build_pass2_prompt,
    get_entity_roster,
    query_graph,
    resolve_active_graph_name,
)
from app.brain.names import split_names
from app.ingest.decisions_extractor import (
    Pass1Candidates,
    Pass2Verification,
    derive_status_from_evidence,
)
from app.ingest.source_text import excerpt, quote_in

logger = logging.getLogger("decision_trace.ingest.live")

TAG = "demo_ingest_id"
LLM_TIMEOUT_SECONDS = 45.0
MAX_TEXT = 5000
STEPS = [
    ("reading", "Reading source"),
    ("extracting_decisions", "Extracting decisions"),
    ("extracting_people", "Extracting people and status changes"),
    ("matching", "Matching people and systems"),
    ("linking", "Linking to existing decisions"),
    ("writing", "Writing to FalkorDB"),
    ("health", "Recomputing health"),
]
_LABEL_FOR_TYPE = {"meeting": "Meeting", "ticket": "Ticket", "announcement": "Document"}

# One ingest or reset at a time: both rewrite shared demo state
INGEST_LOCK = asyncio.Lock()


class IngestRequest(BaseModel):
    type: Literal["meeting", "ticket", "announcement"]
    title: str = Field(..., min_length=1, max_length=200)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    text: str = Field(..., min_length=1, max_length=MAX_TEXT)
    participants: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("participants")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return [p.strip() for p in v if p and p.strip()][:30]


class PersonChange(BaseModel):
    person: str = Field(..., description="Full name of the person")
    change: Literal["leaves", "joins", "owns"] = Field(
        ..., description="leaves = left the company; joins = joined; owns = now owns a system"
    )
    system: Optional[str] = Field(None, description="System name, only for 'owns'")
    quote: str = Field(..., description="Exact sentence from the text that states the change")


class PeopleChanges(BaseModel):
    changes: list[PersonChange] = Field(default_factory=list)


class LinkJudgement(BaseModel):
    new_choice: str = Field(..., description="What the NEW decision chooses, in a few words (e.g. 'Kafka')")
    existing_choice: str = Field(..., description="What the EXISTING decision chooses, in a few words")
    same_choice: bool = Field(
        ..., description="True if both decisions choose the same technology/option for the same purpose"
    )
    relation: Literal["supersedes", "contradicts", "reaffirms", "none"]
    reason: str = Field(..., description="One sentence grounded in the two decisions")


def effective_relation(j: LinkJudgement) -> str:
    """The edge to create. Making the same choice is never supersession or contradiction:
    restating or extending an existing choice (e.g. 'standardise on Kafka and retire RabbitMQ'
    vs 'adopt Kafka') reaffirms it, so no edge is created."""
    if j.same_choice and j.relation in ("supersedes", "contradicts"):
        return "none"
    return j.relation if j.relation in ("supersedes", "contradicts") else "none"


PEOPLE_PROMPT = (
    "You extract people status changes from an engineering source document.\n"
    "Return only explicit changes stated in the text:\n"
    "- leaves: the person has left / is leaving the company\n"
    "- joins: the person joined the company\n"
    "- owns: the person now owns a named system\n"
    "For each, copy the exact sentence that states it into `quote`. "
    "Attendance, opinions, or task assignments are NOT status changes. If none, return an empty list."
)

JUDGE_PROMPT = (
    "You judge how a NEW engineering decision relates to one EXISTING decision.\n"
    "Answer with one relation:\n"
    "- supersedes: the new decision replaces, retires, or reverses the existing one, or settles a "
    "choice between alternatives in favour of a different option than the existing decision chose.\n"
    "- contradicts: both remain in force and are incompatible, with no resolution.\n"
    "- reaffirms: the new decision makes the same choice as the existing one, even if it adds "
    "details such as retiring alternatives or setting deadlines (no edge is created).\n"
    "First state what each decision chooses and whether it is the same choice for the same purpose.\n"
    "- none: unrelated or only loosely related.\n"
    "Base the answer only on the two decisions and the source text. Give a one-sentence reason."
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event(name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": name, "data": data}


def sse(event: dict[str, Any]) -> str:
    """Serialize an event as a Server-Sent Events frame."""
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], default=str)}\n\n"


def _step(step: str, status: str, detail: Optional[str] = None) -> dict[str, Any]:
    label = dict(STEPS)[step]
    data: dict[str, Any] = {"step": step, "status": status, "label": label}
    if detail:
        data["detail"] = detail
    return _event("step", data)


async def _llm(system_prompt: str, text: str, model: type[BaseModel], max_tokens: int) -> Any:
    """Structured LLM call with a hard timeout, counted against the daily quota."""
    from cognee.infrastructure.llm.LLMGateway import LLMGateway

    record_llm_call()
    return await asyncio.wait_for(
        LLMGateway.acreate_structured_output(
            text_input=text, system_prompt=system_prompt, response_model=model, max_tokens=max_tokens
        ),
        timeout=LLM_TIMEOUT_SECONDS,
    )


def changes_graph_name(main_graph: str) -> str:
    """The activity log lives in its own graph so reset leaves the main graph exactly frozen."""
    return f"{main_graph}__changes"


async def _snapshot_state(dataset: str) -> dict[str, Any]:
    health, orphans, codes = await asyncio.gather(
        evaluate_graph_health(dataset_name=dataset),
        evaluate_system_orphans(dataset_name=dataset),
        get_decision_codes(dataset),
    )
    return {"health": health, "orphans": set(orphans), "codes": codes}


async def _match_person(name: str, people: list[str]) -> Optional[str]:
    """Existing person by exact (case-insensitive) name, then by unique last name."""
    lowered = {p.lower(): p for p in people}
    if name.lower() in lowered:
        return lowered[name.lower()]
    last = name.split()[-1].lower() if name.split() else ""
    hits = [p for p in people if p.split() and p.split()[-1].lower() == last]
    return hits[0] if len(hits) == 1 else None


def _match_system(name: str, systems: list[str]) -> Optional[str]:
    """Existing system by exact name, or the single known system named inside the phrase
    (the LLM sometimes returns "Kafka for all event messaging" instead of "Kafka")."""
    lowered = {s.lower(): s for s in systems}
    if name.lower() in lowered:
        return lowered[name.lower()]
    inside = [s for s in systems if re.search(rf"\b{re.escape(s)}\b", name, re.IGNORECASE)]
    return inside[0] if len(inside) == 1 else None


def _is_system_like(name: str) -> bool:
    """Only short, name-like strings may become new System nodes."""
    return 0 < len(name.split()) <= 3 and len(name) <= 40


_LEAVES = re.compile(
    r"([A-Z][a-z]+(?: [A-Z][a-z]+)+) (?:has left|left|is leaving|leaves) the company", re.UNICODE
)


async def run_ingest(req: IngestRequest, dataset: str) -> AsyncIterator[dict[str, Any]]:
    """Run the pipeline, yielding events. The caller holds INGEST_LOCK."""
    ingest_id = f"ing_{uuid.uuid4().hex[:10]}"
    ingested_at = _now()
    tags = {TAG: ingest_id, "ingested_at": ingested_at}
    created: list[dict[str, Any]] = []  # nodes/edges created, for the diff
    overrides: list[dict[str, Any]] = []  # previous values of changed existing nodes
    wrote_anything = False

    try:
        # 1. Reading
        yield _step("reading", "running")
        before = await _snapshot_state(dataset)
        roster = await get_entity_roster(dataset, max_people=200, max_systems=200)
        text = req.text.strip()
        yield _step(
            "reading",
            "done",
            f"{len(text.split())} words · {len(req.participants)} participants · {req.type}",
        )

        # 2. Decisions via the existing two-pass extractor prompts
        yield _step("extracting_decisions", "running")
        pass1 = await _llm(build_pass1_prompt(roster=roster), text, Pass1Candidates, 1500)
        candidates = getattr(pass1, "candidates", []) or []
        decisions: list[dict[str, Any]] = []
        for cand in candidates:
            if not quote_in(cand.verbatim_quote, text):
                continue  # the quote must be verbatim from this source
            verdict = await _llm(
                build_pass2_prompt(roster=roster),
                f"Candidate Title: {cand.title}\nCandidate Decider: {cand.decided_by or 'Unknown'}\n"
                f"Candidate System: {cand.system or 'None'}\nCandidate Rationale: {cand.rationale}\n"
                f"Evidence Quote: {cand.verbatim_quote}\nSource Context:\n{text}",
                Pass2Verification,
                800,
            )
            if not verdict.keep:
                continue
            decisions.append(
                {
                    "title": (verdict.refined_title or cand.title).strip(),
                    "quote": cand.verbatim_quote.strip(),
                    "rationale": cand.rationale.strip(),
                    "status": derive_status_from_evidence(cand.verbatim_quote, cand.status or "accepted"),
                    "deciders": split_names(verdict.decided_by_verified or cand.decided_by),
                    "systems": split_names(verdict.system_verified or cand.system),
                    "confidence": cand.confidence,
                }
            )
        yield _step(
            "extracting_decisions",
            "done",
            f"{len(decisions)} verified of {len(candidates)} candidates"
            + (": " + "; ".join(d["title"] for d in decisions) if decisions else ""),
        )

        # 3. People and status changes
        yield _step("extracting_people", "running")
        try:
            people_out = await _llm(PEOPLE_PROMPT, text, PeopleChanges, 600)
            person_changes = [c for c in people_out.changes if quote_in(c.quote, text)]
        except Exception as exc:  # noqa: BLE001 - fall back to a deterministic pattern
            logger.warning("People extraction failed, using pattern fallback: %s", exc)
            person_changes = [
                PersonChange(person=m.group(1), change="leaves", quote=m.group(0))
                for m in _LEAVES.finditer(text)
            ]
        yield _step(
            "extracting_people",
            "done",
            "; ".join(f"{c.person} {c.change}{' ' + c.system if c.system else ''}" for c in person_changes)
            or "No status changes",
        )

        # 4. Match entities to existing Person / System nodes
        yield _step("matching", "running")
        people_known = roster.get("people", [])
        systems_known = roster.get("systems", [])
        resolved_people: dict[str, Optional[str]] = {}
        for name in {*req.participants, *(n for d in decisions for n in d["deciders"]), *(c.person for c in person_changes)}:
            resolved_people[name] = await _match_person(name, people_known)
        resolved_systems: dict[str, Optional[str]] = {}
        for name in {*(s for d in decisions for s in d["systems"]), *(c.system for c in person_changes if c.system)}:
            resolved_systems[name] = _match_system(name, systems_known)
        # Systems mentioned anywhere in the source, used to find decisions to link against
        mentioned = [s for s in systems_known if re.search(rf"\b{re.escape(s)}\b", text, re.IGNORECASE)]
        matched = [
            f"{k} → {v}" if k != v else f"{k} → existing"
            for k, v in {**resolved_people, **resolved_systems}.items() if v
        ]
        new = [f"{k} → new" for k, v in resolved_people.items() if not v] + [
            f"{k} → new" for k, v in resolved_systems.items() if not v and _is_system_like(k)
        ] + [f"“{k}” ignored (not a system name)" for k, v in resolved_systems.items() if not v and not _is_system_like(k)]
        yield _step("matching", "done", ", ".join(matched + new) or "Nothing to match")
        context_nodes = [
            {"id": f"Person:{v}", "label": "Person", "name": v, "change": "context"}
            for v in resolved_people.values() if v
        ] + [
            {"id": f"System:{s}", "label": "System", "name": s, "change": "context"}
            for s in sorted({*mentioned, *(v for v in resolved_systems.values() if v)})
        ]
        if context_nodes:
            yield _event("graph", {"nodes": context_nodes, "edges": []})

        # 5. Link: judge each new decision against existing decisions on the same systems
        yield _step("linking", "running")
        link_systems = sorted(
            {*mentioned, *(v or k for d in decisions for k in d["systems"] for v in [resolved_systems.get(k)])}
        )
        existing = []
        if link_systems and decisions:
            existing = await query_graph(
                "MATCH (x:Decision)-[:about_system]->(s:System) WHERE s.name IN $systems "
                "OPTIONAL MATCH (x)-[:decided_by]->(p:Person) "
                "RETURN DISTINCT x.id, x.title, x.decided_on, x.evidence_quote, collect(DISTINCT p.name)",
                dataset_name=dataset,
                params={"systems": link_systems},
            )
        links: list[dict[str, Any]] = []
        judge_calls = []
        for i, d in enumerate(decisions):
            for row in existing:
                x_id, x_title, x_date, x_quote, x_deciders = row
                h = before["health"].get(str(x_id))
                prompt_input = (
                    f"NEW decision (dated {req.date}): {d['title']}\nQuote: {d['quote']}\n"
                    f"Source text: {text}\n\nEXISTING decision ({x_date}, decided by "
                    f"{', '.join(x_deciders or []) or 'unknown'}, health {h.status if h else 'active'}): "
                    f"{x_title}\nQuote: {x_quote or ''}"
                )
                judge_calls.append((i, str(x_id), x_title, _llm(JUDGE_PROMPT, prompt_input, LinkJudgement, 300)))
        results = await asyncio.gather(*(c[3] for c in judge_calls), return_exceptions=True)
        for (i, x_id, x_title, _), res in zip(judge_calls, results, strict=True):
            if isinstance(res, BaseException):
                links.append({"new": i, "existing": x_id, "title": x_title, "relation": "none", "reason": f"Judge failed: {res}"})
            else:
                rel = effective_relation(res)
                reason = res.reason
                if rel == "none" and res.relation in ("supersedes", "contradicts"):
                    reason = f"Same choice ({res.existing_choice}), so it reaffirms rather than {res.relation}. {res.reason}"
                links.append({"new": i, "existing": x_id, "title": x_title, "relation": rel, "reason": reason, "raw": res.relation})
        linked = [lk for lk in links if lk["relation"] != "none"]
        yield _step(
            "linking",
            "done",
            f"{len(links)} pairs judged · " + (
                "; ".join(f"{lk['relation']} “{lk['title']}”" for lk in linked) or "no links"
            ),
        )

        # 6. Write, all tagged
        yield _step("writing", "running")
        wrote_anything = True
        label = _LABEL_FOR_TYPE[req.type]
        src_props: dict[str, Any] = {
            "title": req.title,
            "date": req.date,
            "body": excerpt(text),
            "source_type": req.type,
            **tags,
        }
        if label == "Ticket":
            src_props["ticket_id"] = f"TICK-{ingest_id[4:10].upper()}"
            src_props["opened"] = req.date
            src_key = f"Ticket:{src_props['ticket_id']}"
        elif label == "Document":
            src_props["name"] = req.title
            src_key = f"Document:{req.title}"
        else:
            src_props["meeting_date"] = req.date
            src_key = f"Meeting:{req.title}"
        src_props["id"] = f"src_{ingest_id}"
        await query_graph(f"CREATE (n:{label}) SET n += $props", dataset_name=dataset, params={"props": src_props})
        created.append({"kind": "node", "id": src_key, "label": label, "name": req.title})

        async def ensure_person(name: str) -> str:
            match = resolved_people.get(name)
            if match:
                return match
            await query_graph(
                "CREATE (p:Person) SET p += $props",
                dataset_name=dataset,
                params={"props": {"name": name, "is_active": True, "leave_date": "", **tags}},
            )
            resolved_people[name] = name
            created.append({"kind": "node", "id": f"Person:{name}", "label": "Person", "name": name})
            return name

        async def ensure_system(name: str) -> Optional[str]:
            match = resolved_systems.get(name)
            if match:
                return match
            if not _is_system_like(name):
                return None
            await query_graph(
                "CREATE (s:System) SET s += $props",
                dataset_name=dataset,
                params={"props": {"name": name, **tags}},
            )
            resolved_systems[name] = name
            created.append({"kind": "node", "id": f"System:{name}", "label": "System", "name": name})
            return name

        async def edge(a_match: str, a_params: dict, rel: str, b_match: str, b_params: dict, props: dict) -> None:
            await query_graph(
                f"MATCH (a{a_match}) MATCH (b{b_match}) CREATE (a)-[r:{rel}]->(b) SET r += $props",
                dataset_name=dataset,
                params={**a_params, **b_params, "props": {**props, **tags}},
            )

        src_match = (" {id: $src}", {"src": src_props["id"]})
        if label == "Meeting":
            for name in req.participants:
                person = await ensure_person(name)
                await edge(*src_match, "attended_by", " :Person {name: $p}", {"p": person}, {})
                created.append({"kind": "edge", "source": src_key, "target": f"Person:{person}", "type": "attended_by"})

        new_ids: list[str] = []
        for d in decisions:
            d_id = f"dec_{uuid.uuid4().hex[:12]}"
            new_ids.append(d_id)
            await query_graph(
                "CREATE (d:Decision) SET d += $props",
                dataset_name=dataset,
                params={
                    "props": {
                        "id": d_id,
                        "title": d["title"],
                        "summary": d["rationale"] or d["title"],
                        "rationale": d["rationale"],
                        "status": d["status"],
                        "confidence": d["confidence"],
                        "evidence_quote": d["quote"],
                        "decided_on": req.date,
                        **tags,
                    }
                },
            )
            created.append({"kind": "node", "id": f"Decision:{d_id}", "label": "Decision", "name": d["title"], "decision_id": d_id})
            d_match = (" :Decision {id: $d}", {"d": d_id})
            for name in d["deciders"]:
                person = await ensure_person(name)
                await edge(*d_match, "decided_by", " :Person {name: $p}", {"p": person}, {})
                created.append({"kind": "edge", "source": f"Decision:{d_id}", "target": f"Person:{person}", "type": "decided_by"})
            for name in d["systems"]:
                system = await ensure_system(name)
                if not system:
                    continue
                await edge(*d_match, "about_system", " :System {name: $s}", {"s": system}, {})
                created.append({"kind": "edge", "source": f"Decision:{d_id}", "target": f"System:{system}", "type": "about_system"})
            await edge(*d_match, "based_on", *src_match, {"quote": d["quote"]})
            created.append({"kind": "edge", "source": f"Decision:{d_id}", "target": src_key, "type": "based_on"})

        for lk in linked:
            d_id = new_ids[lk["new"]]
            await edge(
                " :Decision {id: $d}", {"d": d_id}, lk["relation"], " :Decision {id: $x}", {"x": lk["existing"]},
                {"reason": lk["reason"], "judged_by": "llm"},
            )
            created.append({"kind": "edge", "source": f"Decision:{d_id}", "target": f"Decision:{lk['existing']}", "type": lk["relation"], "reason": lk["reason"]})

        for c in person_changes:
            if c.change == "owns" and c.system:
                system = resolved_systems.get(c.system)  # people changes only reference known systems
                if not system:
                    continue
                person = await ensure_person(c.person)
                already = await query_graph(
                    "MATCH (:Person {name: $p})-[r:owns]->(:System {name: $s}) RETURN count(r)",
                    dataset_name=dataset,
                    params={"p": person, "s": system},
                )
                if already and already[0][0]:
                    continue  # no duplicate ownership
                await edge(" :Person {name: $p}", {"p": person}, "owns", " :System {name: $s}", {"s": system}, {})
                created.append({"kind": "edge", "source": f"Person:{person}", "target": f"System:{system}", "type": "owns"})
                continue
            existing_name = resolved_people.get(c.person)
            if c.change == "joins" and not existing_name:
                await ensure_person(c.person)
                continue
            if not existing_name:
                continue
            prev = await query_graph(
                "MATCH (p:Person {name: $p}) RETURN p.is_active, p.leave_date",
                dataset_name=dataset,
                params={"p": existing_name},
            )
            prev_active, prev_leave = (prev[0] if prev else [True, ""])
            new_active, new_leave = (False, req.date) if c.change == "leaves" else (True, "")
            if (prev_active, prev_leave) == (new_active, new_leave):
                continue
            overrides.append(
                {"label": "Person", "name": existing_name, "before": {"is_active": prev_active, "leave_date": prev_leave},
                 "after": {"is_active": new_active, "leave_date": new_leave}}
            )
            await query_graph(
                "MATCH (p:Person {name: $p}) SET p.is_active = $a, p.leave_date = $l, p.demo_modified_by = $id",
                dataset_name=dataset,
                params={"p": existing_name, "a": new_active, "l": new_leave, "id": ingest_id},
            )

        added_nodes = [c for c in created if c["kind"] == "node"]
        added_edges = [c for c in created if c["kind"] == "edge"]
        yield _step("writing", "done", f"{len(added_nodes)} nodes, {len(added_edges)} edges, {len(overrides)} updated")
        yield _event(
            "graph",
            {
                "nodes": [{"id": n["id"], "label": n["label"], "name": n["name"], "change": "added"} for n in added_nodes]
                + [{"id": f"Person:{o['name']}", "label": "Person", "name": o["name"], "change": "changed"} for o in overrides],
                "edges": [{"source": e["source"], "target": e["target"], "type": e["type"], "change": "added"} for e in added_edges],
            },
        )

        # 7. Health
        yield _step("health", "running")
        cache.invalidate()
        after = await _snapshot_state(dataset)
        diff = build_diff(ingest_id, ingested_at, req, src_key, created, overrides, links, before, after)
        changed_nodes = [
            {"id": f"Decision:{s['id']}", "label": "Decision", "name": s["title"], "decision_code": s["decision_code"], "change": "changed"}
            for s in diff["status_changes"]
        ]
        if changed_nodes:
            yield _event("graph", {"nodes": changed_nodes, "edges": []})
        yield _step("health", "done", diff["summary"])

        await record_change(dataset, {
            "id": ingest_id, "kind": "ingest", "title": req.title, "type": req.type,
            "created_at": ingested_at, "summary": diff["summary"], "diff": diff, "overrides": overrides,
        })
        yield _event("diff", diff)
    except Exception as exc:  # noqa: BLE001 - surfaced to the client as an error event
        logger.exception("Ingest %s failed", ingest_id)
        if wrote_anything:
            await rollback(dataset, ingest_id, overrides)
        yield _event("error", {"message": f"{type(exc).__name__}: {exc}"[:300]})


def build_diff(
    ingest_id: str,
    ingested_at: str,
    req: IngestRequest,
    src_key: str,
    created: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
    links: list[dict[str, Any]],
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Compare health/orphans/codes before and after, and describe what was added."""
    codes = after["codes"]
    new_nodes = []
    new_ids = {}
    for c in created:
        if c["kind"] != "node":
            continue
        node = {"id": c["id"], "label": c["label"], "name": c["name"]}
        if c["label"] == "Decision":
            node["decision_code"] = codes.get(c["decision_id"])
            new_ids[c["decision_id"]] = node["decision_code"]
        new_nodes.append(node)

    status_changes = []
    for d_id, h_after in after["health"].items():
        h_before = before["health"].get(d_id)
        if h_before and h_before.status != h_after.status:
            status_changes.append(
                {"id": d_id, "decision_code": codes.get(d_id), "title": h_after.title,
                 "before": h_before.status, "after": h_after.status}
            )
    status_changes.sort(key=lambda s: s["decision_code"] or "")

    orphan_changes = [
        {"system": s, "before": s in before["orphans"], "after": s in after["orphans"]}
        for s in sorted(before["orphans"] ^ after["orphans"])
    ]
    person_changes = [
        {"name": o["name"], "field": "departed", "before": o["before"]["is_active"] is False,
         "after": o["after"]["is_active"] is False}
        for o in overrides
    ]
    new_codes = list(new_ids.values())
    link_list = [
        {"new_code": new_codes[lk["new"]] if lk["new"] < len(new_codes) else None,
         "existing_code": codes.get(lk["existing"]), "relation": lk["relation"], "reason": lk["reason"]}
        for lk in links
    ]
    edges_added = [
        {k: c[k] for k in ("source", "target", "type", "reason") if k in c}
        for c in created if c["kind"] == "edge"
    ]

    parts = []
    n_dec = len(new_codes)
    if n_dec:
        parts.append(f"{n_dec} new decision{'s' if n_dec != 1 else ''}")
    if status_changes:
        parts.append(f"{len(status_changes)} status change{'s' if len(status_changes) != 1 else ''}")
    if any(s["before"] == "contradicted" and s["after"] != "contradicted" for s in status_changes):
        parts.append("conflict resolved")
    if any(p["after"] and not p["before"] for p in person_changes):
        parts.append(f"{sum(1 for p in person_changes if p['after'])} person left")
    newly_orphaned = [o for o in orphan_changes if o["after"]]
    if newly_orphaned:
        parts.append(f"{len(newly_orphaned)} system{'s' if len(newly_orphaned) != 1 else ''} orphaned")

    return {
        "ingest_id": ingest_id,
        "ingested_at": ingested_at,
        "source": {"id": src_key, "label": src_key.split(":")[0], "title": req.title},
        "nodes_added": new_nodes,
        "edges_added": edges_added,
        "status_changes": status_changes,
        "person_changes": person_changes,
        "orphan_changes": orphan_changes,
        "links": link_list,
        "summary": " · ".join(parts) or "No changes",
    }


async def _changes_graph(dataset: str) -> str:
    return changes_graph_name(await resolve_active_graph_name(dataset))


async def record_change(dataset: str, entry: dict[str, Any]) -> None:
    graph = await _changes_graph(dataset)
    await query_graph(
        "CREATE (c:Change) SET c += $props",
        dataset_name=graph,
        params={"props": {
            "id": entry["id"], "kind": entry["kind"], "title": entry.get("title", ""),
            "type": entry.get("type", ""), "created_at": entry["created_at"], "summary": entry["summary"],
            "diff_json": json.dumps(entry.get("diff")) if entry.get("diff") else "",
            "overrides_json": json.dumps(entry.get("overrides", [])),
            "reverted": False,
        }},
    )


async def list_changes(dataset: str, limit: int = 20) -> list[dict[str, Any]]:
    graph = await _changes_graph(dataset)
    try:
        rows = await query_graph(
            "MATCH (c:Change) RETURN c.id, c.kind, c.title, c.type, c.created_at, c.summary, c.diff_json, c.reverted "
            "ORDER BY c.created_at DESC LIMIT $limit",
            dataset_name=graph,
            params={"limit": limit},
        )
    except Exception:  # noqa: BLE001 - no change log yet
        return []
    return [
        {"id": r[0], "kind": r[1], "title": r[2], "type": r[3] or None, "created_at": r[4], "summary": r[5],
         "diff": json.loads(r[6]) if r[6] else None, "reverted": bool(r[7])}
        for r in rows
    ]


async def _restore(dataset: str, overrides: list[dict[str, Any]]) -> int:
    restored = 0
    for o in reversed(overrides):
        await query_graph(
            "MATCH (p:Person {name: $p}) SET p.is_active = $a, p.leave_date = $l, p.demo_modified_by = NULL",
            dataset_name=dataset,
            params={"p": o["name"], "a": o["before"]["is_active"], "l": o["before"]["leave_date"]},
        )
        restored += 1
    return restored


async def rollback(dataset: str, ingest_id: str, overrides: list[dict[str, Any]]) -> None:
    """Undo a failed ingest: delete only its tagged items and restore what it changed."""
    try:
        await query_graph(
            "MATCH ()-[r]->() WHERE r.demo_ingest_id = $id DELETE r", dataset_name=dataset, params={"id": ingest_id}
        )
        await query_graph(
            "MATCH (n) WHERE n.demo_ingest_id = $id DETACH DELETE n", dataset_name=dataset, params={"id": ingest_id}
        )
        await _restore(dataset, overrides)
    finally:
        cache.invalidate()


async def reset_demo(dataset: str) -> dict[str, Any]:
    """Delete every tagged node/edge and restore every recorded override. Untagged data untouched."""
    graph = await _changes_graph(dataset)
    try:
        rows = await query_graph(
            "MATCH (c:Change {kind: 'ingest', reverted: false}) RETURN c.id, c.overrides_json ORDER BY c.created_at DESC",
            dataset_name=graph,
        )
    except Exception:  # noqa: BLE001
        rows = []
    restored = 0
    for change_id, overrides_json in rows:
        restored += await _restore(dataset, json.loads(overrides_json or "[]"))
    edges = await query_graph(
        "MATCH ()-[r]->() WHERE r.demo_ingest_id IS NOT NULL DELETE r RETURN count(r)", dataset_name=dataset
    )
    nodes = await query_graph(
        "MATCH (n) WHERE n.demo_ingest_id IS NOT NULL DETACH DELETE n RETURN count(n)", dataset_name=dataset
    )
    # Safety net: clear markers left without a change record (e.g. a crash mid-ingest)
    await query_graph(
        "MATCH (p:Person) WHERE p.demo_modified_by IS NOT NULL SET p.demo_modified_by = NULL", dataset_name=dataset
    )
    if rows:
        await query_graph(
            "MATCH (c:Change {kind: 'ingest', reverted: false}) SET c.reverted = true", dataset_name=graph
        )
    cache.invalidate()
    totals = await asyncio.gather(
        query_graph("MATCH (n) RETURN count(n)", dataset_name=dataset),
        query_graph("MATCH ()-[r]->() RETURN count(r)", dataset_name=dataset),
    )
    result = {
        "removed_nodes": nodes[0][0] if nodes else 0,
        "removed_edges": edges[0][0] if edges else 0,
        "restored_properties": restored,
        "nodes": totals[0][0][0],
        "edges": totals[1][0][0],
    }
    await record_change(dataset, {
        "id": f"reset_{uuid.uuid4().hex[:8]}", "kind": "reset", "title": "Reset demo data",
        "created_at": _now(),
        "summary": f"Removed {result['removed_nodes']} nodes and {result['removed_edges']} edges, restored {restored} values",
    })
    return result

