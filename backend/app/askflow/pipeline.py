"""The Ask pipeline as a stream of events, shared by POST /ask/stream (SSE) and POST /ask.

Steps: understanding (intent, by rules) -> matching (people, systems, decisions) -> traversal
(Cypher per intent) -> health (health map, assembly) -> composing (LLM phrases the answer from
the assembled context, streamed token by token). Events:

  step   {step, status: running|done|skipped, label, ms?, detail?, intent?, entities?}
  query  {step, name, query, params, rows, ms}          one per Cypher statement
  path   {intent, graph_path, primary_decision_id, sections, experts}   before the answer
  token  {text}
  done   the full AskResponse (with trace)
  error  {message}
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from app.api.primary import pick_primary_decision
from app.api.rate_limiter import record_llm_call
from app.askflow import assemble, queries
from app.askflow.intent import classify_intent
from app.brain.codes import get_decision_codes_cached
from app.brain.health import get_health_map
from app.brain.memory import query_graph_threaded
from app.config import get_settings

logger = logging.getLogger("decision_trace.askflow")
_settings = get_settings()

STEPS = {
    "understanding": "Understanding the question",
    "matching": "Matching people, systems and decisions",
    "traversal": "Traversing the graph",
    "health": "Checking decision health",
    "composing": "Composing the answer",
}
NOT_FOUND = "The answer is not found in the Company Brain."
LLM_TIMEOUT_SECONDS = 45.0
_MAX_TOKENS = {"why": 400, "other": 400, "impact": 450, "expertise": 300, "status": 350}

_RULES = (
    "Answer ONLY using the facts in the context. Refer to decisions by their DEC code and title. "
    "Cite the ticket IDs (e.g. TICK-101) or meeting titles a decision is based on when you mention it. "
    "If a person has left the company, say so. Do not speculate or add facts that are not in the context."
)
WHY_PROMPT = (
    "You are the Company Brain assistant for engineering decisions and system ownership.\n"
    "Answer the user's question accurately, concisely, and STRICTLY using only the provided graph context below.\n\n"
    "CRITICAL INTEGRITY RULES:\n"
    "1. CONTRADICTION RULE: If asked why a technology or system was chosen over another (e.g. Kafka vs RabbitMQ) and the context contains contradicting decisions (e.g. 'contradicts' relationships), you MUST explicitly surface the contradiction, describe both decisions with their deciders and statuses, cite the respective tickets (e.g. TICK-105, TICK-106), and explain that the records show conflicting accepted decisions rather than a one-sided choice.\n"
    "2. Answer ONLY using the facts present in the Context. If the context does not contain any relevant facts or decisions, say 'The answer is not found in the Company Brain.'\n"
    "3. You MUST cite relevant Ticket IDs (e.g. TICK-101) or Meeting titles (e.g. 2026-02-10_iam_modernization.md) when referencing facts or decisions.\n"
    "4. If a person has departed (leave_date in past or inactive), explicitly mention their departure status when asked about ownership.\n"
    "5. STATUS INTEGRITY RULE: For decisions with status 'proposed', you MUST describe them as 'proposed' or 'a proposal' and NEVER use words like 'decided', 'adopted', or 'chosen'. For decisions with status 'rejected', you MUST explicitly state that they were 'rejected' or 'decided against'. ONLY decisions with status 'accepted' may be described as decided or adopted.\n"
    "6. Do NOT hallucinate or extrapolate beyond the provided context.\n\n"
    "CONTEXT SUBGRAPH:\n{context}"
)
IMPACT_PROMPT = (
    "You are the Company Brain assistant. The user asks what would be affected if a system were dropped "
    "or changed. The impact below was computed from the knowledge graph. Write a short impact summary: "
    "one opening sentence with the scale (how many decisions, people, teams or projects, open tickets), "
    "then brief bullet points for the decisions affected (DEC code, title, current health; note which are "
    "already superseded), the people to involve (owner first), teams and projects, and open or recent "
    f"tickets. At most 170 words. {_RULES}\n\nIMPACT CONTEXT:\n{{context}}"
)
EXPERTISE_PROMPT = (
    "You are the Company Brain assistant. The user asks who knows about a system. The ranking below was "
    "computed from graph evidence. Recommend at most three people in the given order and state each "
    "person's evidence as counts (for example: decided 1 decision (DEC-04), owns Kafka, attended 1 meeting, "
    "on 1 ticket). Never recommend someone who has left the company as the first contact; mention them as "
    f"departed instead. At most 120 words. {_RULES}\n\nEXPERTISE CONTEXT:\n{{context}}"
)
STATUS_PROMPT = (
    "You are the Company Brain assistant. Answer the user's question about decision health or system "
    "ownership directly, using the computed context below. For each relevant decision give its DEC code, "
    "title, deciders, its current health as given in the context (for example 'contradicted'), the relation "
    "(for example 'conflicts with DEC-04') and its sources in parentheses (for example '(TICK-105)'). "
    "A system whose owner has left the company has no active owner: name it when asked which systems have "
    "no owner. If a category is empty, say so plainly. At most 150 words. "
    f"{_RULES}\n\nHEALTH CONTEXT:\n{{context}}"
)
_PROMPTS = {"why": WHY_PROMPT, "other": WHY_PROMPT, "impact": IMPACT_PROMPT,
            "expertise": EXPERTISE_PROMPT, "status": STATUS_PROMPT}

_DEC_CODE = re.compile(r"\bDEC-\d{1,3}\b", re.IGNORECASE)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _event(name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": name, "data": data}


class _Run:
    """Collects step timings and the Cypher trace while events are produced."""

    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        self.started = time.perf_counter()
        self.steps: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []
        self._step_started = 0.0

    def start(self, step: str) -> dict[str, Any]:
        self._step_started = time.perf_counter()
        return _event("step", {"step": step, "status": "running", "label": STEPS[step]})

    def done(self, step: str, detail: Optional[str] = None, status: str = "done", **extra: Any) -> dict[str, Any]:
        ms = _ms(self._step_started) if status != "skipped" else 0.0
        entry = {"step": step, "label": STEPS[step], "status": status, "ms": ms, "detail": detail}
        self.steps.append(entry)
        return _event("step", {**entry, **extra})

    def skip(self, step: str, detail: str) -> dict[str, Any]:
        return self.done(step, detail, status="skipped")

    async def query(self, step: str, name: str, cypher: str, params: Optional[dict[str, Any]] = None) -> list[Any]:
        start = time.perf_counter()
        rows = await query_graph_threaded(cypher, dataset_name=self.dataset, params=params or {})
        self.queries.append({"step": step, "name": name, "query": cypher, "params": params or {},
                             "rows": len(rows), "ms": _ms(start)})
        return rows

    def query_events(self, since: int) -> list[dict[str, Any]]:
        return [_event("query", q) for q in self.queries[since:]]

    def trace(self) -> dict[str, Any]:
        return {"steps": self.steps, "queries": self.queries, "total_ms": _ms(self.started)}


# ---------------------------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------------------------

def match_names(question: str, people: list[str], systems: list[str]) -> tuple[list[str], list[str]]:
    """People by full name or first name; systems by whole word. Both in order of appearance."""
    q = question.lower()
    words = set(re.findall(r"[a-z0-9']+", q))

    def pos(name: str) -> int:
        i = q.find(name.lower())
        return i if i >= 0 else q.find(name.split()[0].lower())

    matched_people = [
        p for p in people
        if p.lower() in q or (len(p.split()) > 1 and p.split()[0].lower() in words)
    ]
    matched_systems = [s for s in systems if re.search(rf"\b{re.escape(s.lower())}\b", q)]
    return sorted(matched_people, key=pos), sorted(matched_systems, key=pos)


# Embedding similarity a decision title needs to count as matched. Unrelated titles score about
# 0.6, so when the question already names a system (whose decisions are retrieved by name) only
# strong matches are added; otherwise they would bury the facts the question is about.
DECISION_MATCH_MIN = 0.35
DECISION_MATCH_MIN_WITH_SYSTEM = 0.7


def _match_decisions(question: str, decisions: list[tuple[str, str]], limit: int = 4) -> list[tuple[str, float]]:
    """Top decisions by title similarity, as (id, score)."""
    from app.brain.reconciliation import compute_embedding_similarities

    if not decisions:
        return []
    scores = compute_embedding_similarities(question, [t for _, t in decisions])
    ranked = sorted(zip(decisions, scores, strict=False), key=lambda x: x[1], reverse=True)
    return [(d_id, float(score)) for (d_id, _), score in ranked[:limit]]


# ---------------------------------------------------------------------------------------------
# Composing
# ---------------------------------------------------------------------------------------------

async def _stream_llm(intent: str, context: str, question: str) -> AsyncIterator[str]:
    import litellm

    record_llm_call()
    response = await asyncio.wait_for(
        litellm.acompletion(
            model=_settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": _PROMPTS[intent].format(context=context)},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=_MAX_TOKENS[intent],
            stream=True,
        ),
        timeout=LLM_TIMEOUT_SECONDS,
    )
    deadline = time.monotonic() + LLM_TIMEOUT_SECONDS
    async for chunk in response:
        if time.monotonic() > deadline:
            raise TimeoutError("LLM stream exceeded its time limit")
        text = chunk.choices[0].delta.content if chunk.choices else None
        if text:
            yield text


def _fallback(intent: str, sections: list[dict[str, Any]], experts: list[dict[str, Any]], subject: str) -> str:
    """Deterministic answer when the LLM is unavailable: structured results are still exact."""
    if intent == "impact":
        totals = {s["key"]: s["total"] for s in sections}
        return (f"Changing {subject} affects {totals.get('decisions', 0)} decisions, {totals.get('people', 0)} people, "
                f"{totals.get('teams', 0)} teams or projects and {totals.get('tickets', 0)} tickets.")
    if intent == "expertise" and experts:
        top = experts[0]
        return f"{top['name']} has the most recorded evidence on {subject} (weight {top['score']})."
    if intent == "status":
        return "; ".join(f"{s['title']}: {s['total']}" for s in sections) + "."
    return NOT_FOUND


def _fix_status_wording(answer: str, statuses: dict[str, tuple[str, str]]) -> str:
    """Never let the answer say 'decided' for a proposed or rejected decision."""
    for title, status in statuses.values():
        if status in ("proposed", "rejected"):
            answer = re.sub(rf"\bdecided(?:\s+to)?\s+({re.escape(title)})", rf"{status} \1", answer, flags=re.IGNORECASE)
    return answer


# ---------------------------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------------------------

def _empty_done(run: _Run, intent: str, entities: list[dict[str, Any]], answer: str = NOT_FOUND) -> dict[str, Any]:
    return {"answer": answer, "citations": [], "people": [], "primary_decision_id": None,
            "graph_path": {"nodes": [], "edges": [], "omitted_count": 0}, "intent": intent,
            "entities": entities, "sections": [], "experts": [], "trace": run.trace()}


async def run_ask(question: str, dataset: Optional[str] = None) -> AsyncIterator[dict[str, Any]]:
    dataset = dataset or _settings.DATASET_NAME
    run = _Run(dataset)
    question = question.strip()
    try:
        async for event in _pipeline(run, question, dataset):
            yield event
    except Exception as exc:  # noqa: BLE001 - reported to the client as an error event
        logger.exception("Ask pipeline failed: %s", exc)
        yield _event("error", {"message": "The Company Brain could not answer right now. Try again in a moment."})


async def _pipeline(run: _Run, question: str, dataset: str) -> AsyncIterator[dict[str, Any]]:
    # 1. Understanding
    yield run.start("understanding")
    parsed = classify_intent(question)
    detail = parsed.intent + (f" ({parsed.focus})" if parsed.focus else "")
    yield run.done("understanding", detail, intent=parsed.intent, focus=parsed.focus)

    # 2. Matching
    yield run.start("matching")
    roster, codes = await asyncio.gather(
        run.query("matching", "roster", queries.ROSTER), get_decision_codes_cached(dataset)
    )
    for e in run.query_events(0):
        yield e
    people = sorted({str(r[1]) for r in roster if r and r[0] == "Person" and r[1]})
    systems = sorted({str(r[1]) for r in roster if r and r[0] == "System" and r[1]})
    decisions = [(str(r[2]), str(r[1])) for r in roster if r and r[0] == "Decision" and r[1] and r[2]]
    matched_people, matched_systems = match_names(question, people, systems)

    intent = parsed.intent
    route = intent
    if intent in ("impact", "expertise") and not matched_systems:
        route = "why"  # no system to analyse: fall back to retrieval around what did match
    elif intent == "status" and (matched_systems or matched_people):
        route = "why"  # a status question about specific things: answer from their subgraph
    elif intent == "other":
        route = "why"

    decision_ids: list[str] = []
    if route == "why":
        by_code = {v.upper(): k for k, v in codes.items()}
        decision_ids = [by_code[c.upper()] for c in _DEC_CODE.findall(question) if c.upper() in by_code]
        threshold = DECISION_MATCH_MIN_WITH_SYSTEM if matched_systems else DECISION_MATCH_MIN
        for d_id, score in await asyncio.to_thread(_match_decisions, question, decisions):
            if score >= threshold and d_id not in decision_ids:
                decision_ids.append(d_id)
    titles = dict(decisions)
    entities = (
        [{"label": "System", "name": s} for s in matched_systems]
        + [{"label": "Person", "name": p} for p in matched_people]
        + [{"label": "Decision", "name": titles[d], "id": d, "decision_code": codes.get(d)} for d in decision_ids]
    )
    found = len(entities)
    yield run.done("matching", f"{found} matched" if found else "Nothing in the graph matches the question",
                   entities=entities)

    if route == "why" and not entities:
        for step, why in (("traversal", "Nothing to traverse"), ("health", "No decisions to check")):
            yield run.skip(step, why)
        yield run.start("composing")
        yield _event("token", {"text": NOT_FOUND})
        yield run.done("composing", "No matching evidence, so no model call")
        yield _event("done", _empty_done(run, intent, entities))
        return

    # 3. Traversal
    yield run.start("traversal")
    before = len(run.queries)
    subject = matched_systems[0] if matched_systems else ""
    if route == "impact":
        p = {"name": subject}
        decision_rows, people_rows, ticket_rows = await asyncio.gather(
            run.query("traversal", "impact_decisions", queries.IMPACT_DECISIONS, p),
            run.query("traversal", "impact_people", queries.IMPACT_PEOPLE, p),
            run.query("traversal", "impact_tickets", queries.IMPACT_TICKETS, p),
        )
    elif route == "expertise":
        expertise_rows = await run.query("traversal", "expertise", queries.EXPERTISE, {"name": subject})
    elif route == "status":
        if parsed.focus == "ownership":
            status_rows = await run.query("traversal", "systems_ownership", queries.STATUS_SYSTEMS)
            decision_rows = []
        else:
            decision_rows = await run.query("traversal", "decision_health", queries.STATUS_DECISIONS)
            status_rows = []
    else:
        calls = []
        if decision_ids:
            calls.append(run.query("traversal", "decisions_by_id", queries.WHY_BY_IDS, {"decision_ids": decision_ids}))
        if matched_people:
            calls.append(run.query("traversal", "decisions_by_person", queries.WHY_BY_PEOPLE,
                                   {"people_names": matched_people}))
        if matched_systems:
            sp = {"system_names": matched_systems}
            calls.append(run.query("traversal", "decisions_by_system", queries.WHY_BY_SYSTEMS, sp))
            calls.append(run.query("traversal", "system_owners", queries.WHY_OWNERS, sp))
        results = await asyncio.gather(*calls)
        owner_rows = results[-1] if matched_systems else []
        why_rows = [row for res in (results[:-1] if matched_systems else results) for row in res]
    for e in run.query_events(before):
        yield e
    rows_total = sum(q["rows"] for q in run.queries[before:])
    n_queries = len(run.queries) - before
    yield run.done("traversal", f"{n_queries} {'query' if n_queries == 1 else 'queries'} · {rows_total} rows")

    # 4. Health
    yield run.start("health")
    health = await get_health_map(dataset)
    today = _today()
    sections: list[dict[str, Any]] = []
    experts: list[dict[str, Any]] = []
    primary: Optional[str] = None
    why: Optional[assemble.WhyResult] = None
    if route == "impact":
        res = assemble.build_impact(subject, decision_rows, people_rows, ticket_rows, codes, health, today)
        graph, sections, context, primary = res.graph, res.sections, res.context, res.primary_decision_id
    elif route == "expertise":
        experts = assemble.rank_experts(expertise_rows, codes, today)
        graph, context = assemble.expertise_graph(subject, experts), assemble.expertise_context(subject, experts)
    elif route == "status":
        res = assemble.build_status(parsed.focus or "overview", decision_rows, status_rows, codes, health, today)
        graph, sections, context, primary = res.graph, res.sections, res.context, res.primary_decision_id
    else:
        why = assemble.build_why(why_rows, owner_rows, codes, health)
        graph, context = why.graph, why.context
    on_path = [n for n in graph.nodes.values() if n["label"] == "Decision"]
    counts: dict[str, int] = {}
    for n in on_path:
        h = n["properties"].get("health") or "active"
        counts[h] = counts.get(h, 0) + 1
    if route == "status" and parsed.focus == "ownership":
        orphaned = sum(s["total"] for s in sections)
        health_detail = f"{len(status_rows)} systems · {orphaned} without an active owner"
    elif on_path:
        health_detail = f"{len(on_path)} decisions · " + ", ".join(
            f"{n} {h.replace('_', ' ')}" for h, n in sorted(counts.items()))
    else:
        health_detail = "No decisions on the path"
    if why and not primary:
        # Provisional primary for the evidence path while the answer streams: the best match still in force
        live = [d for d in why.main_decisions if d not in why.superseded_ids] or list(why.main_decisions)
        primary_provisional = live[0] if live else None
    else:
        primary_provisional = primary
    yield run.done("health", health_detail)
    yield _event("path", {
        "intent": intent, "graph_path": graph.capped(), "primary_decision_id": primary_provisional,
        "sections": sections, "experts": experts,
    })

    # 5. Composing
    yield run.start("composing")
    if why and not graph.nodes:
        yield _event("token", {"text": NOT_FOUND})
        yield run.done("composing", "No evidence on the path, so no model call")
        yield _event("done", _empty_done(run, intent, entities))
        return
    llm_intent = route if route in _PROMPTS else "why"
    parts: list[str] = []
    try:
        async for text in _stream_llm(llm_intent, "\n".join(context) if route != "why" else "\n\n".join(context), question):
            parts.append(text)
            yield _event("token", {"text": text})
        answer = "".join(parts).strip()
        composed = "Streamed from the model"
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM generation failed in /ask: %s", exc)
        answer = _fallback(route, sections, experts, subject)
        composed = "Model unavailable; answered from the graph results"
        if not parts:
            yield _event("token", {"text": answer})
    if not answer:
        answer = _fallback(route, sections, experts, subject)
    if why:
        answer = _fix_status_wording(answer, why.statuses)
    yield run.done("composing", composed)

    if why and NOT_FOUND.lower().rstrip(".") in answer.lower():
        # The model found nothing relevant in the retrieved subgraph: no path, no sources
        yield _event("done", {**_empty_done(run, intent, entities, answer)})
        return

    citations = assemble.verified_citations(graph, answer)
    if why:
        first_idx = assemble.first_citation_index(graph, citations, why.main_decisions)
        primary = (
            pick_primary_decision(answer, list(why.main_decisions.items()), first_idx, why.superseded_ids)
            if citations else None
        )
    path = graph.capped()
    people_on_path = sorted(
        n["properties"].get("name", n["id"]) for n in path["nodes"] if n["label"] == "Person"
    )
    yield _event("done", {
        "answer": answer, "citations": citations, "people": people_on_path, "primary_decision_id": primary,
        "graph_path": path, "intent": intent, "entities": entities, "sections": sections,
        "experts": experts, "trace": run.trace(),
    })


async def collect_ask(question: str, dataset: Optional[str] = None) -> dict[str, Any]:
    """Run the pipeline to completion and return the final result (for POST /ask)."""
    async for event in run_ask(question, dataset):
        if event["event"] == "done":
            return event["data"]
        if event["event"] == "error":
            raise RuntimeError(event["data"]["message"])
    raise RuntimeError("The ask pipeline ended without a result")
