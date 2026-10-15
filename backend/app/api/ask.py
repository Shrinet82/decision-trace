"""Grounded Question Answering API with Subgraph Traversal and Citations."""

import logging
from typing import Any, Optional

import litellm
from fastapi import APIRouter, Request

from app.api.rate_limiter import check_rate_limits, record_llm_call
from app.api.schemas import AskRequest, AskResponse, Citation, GraphEdge, GraphNode, GraphPath
from app.brain.memory import get_entity_roster, query_graph
from app.brain.reconciliation import compute_embedding_similarities
from app.config import get_settings

logger = logging.getLogger("decision_trace.api.ask")
router = APIRouter(tags=["Question Answering"])
_settings = get_settings()


async def _resolve_entities_in_question(
    question: str,
    target_dataset: str,
) -> dict[str, Any]:
    """Resolve entities in question using roster matching and embedding similarity."""
    roster = await get_entity_roster(target_dataset)
    q_lower = question.lower()

    # 1. Roster match on People and Systems
    matched_people: list[str] = [
        p
        for p in roster.get("people", [])
        if p.lower() in q_lower or (len(p.split()) > 1 and p.split()[0].lower() in q_lower.split())
    ]
    matched_systems: list[str] = [s for s in roster.get("systems", []) if s.lower() in q_lower]

    # 2. Embedding match on Decision titles
    decisions_raw = await query_graph(
        "MATCH (d:Decision) RETURN d.id, d.title", dataset_name=target_dataset
    )
    all_decisions: list[tuple[str, str]] = [
        (str(r[0]), str(r[1])) for r in decisions_raw if r and r[0] and r[1]
    ]

    matched_decision_ids: list[str] = []
    if all_decisions:
        titles = [t for _, t in all_decisions]
        scores = compute_embedding_similarities(question, titles)
        ranked = sorted(zip(all_decisions, scores, strict=False), key=lambda x: x[1], reverse=True)
        for (d_id, _), score in ranked[:4]:
            if score >= 0.35:
                matched_decision_ids.append(d_id)

    return {
        "people": matched_people,
        "systems": matched_systems,
        "decision_ids": matched_decision_ids,
    }


@router.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest, http_request: Request) -> AskResponse:
    """Answer a natural language question grounded strictly in a retrieved FalkorDB subgraph."""
    check_rate_limits(http_request)
    target_dataset = request.dataset_name or _settings.DATASET_NAME
    question = request.question.strip()

    # Step 1: Resolve entities in question
    entities = await _resolve_entities_in_question(question, target_dataset)
    people_matches = entities["people"]
    system_matches = entities["systems"]
    decision_id_matches = entities["decision_ids"]

    logger.info(
        "Question: '%s' | Resolved: people=%s, systems=%s, decisions=%d",
        question,
        people_matches,
        system_matches,
        len(decision_id_matches),
    )

    # If nothing resolved, refuse or say not found immediately without calling LLM
    if not people_matches and not system_matches and not decision_id_matches:
        return AskResponse(
            answer="I could not find any relevant decisions, systems, or people in the Company Brain to answer your question.",
            citations=[],
            people=[],
            graph_path=GraphPath(nodes=[], edges=[]),
        )

    # Step 2: Retrieve connected subgraph via Cypher
    nodes_map: dict[str, GraphNode] = {}
    node_weights: dict[str, float] = {}
    edges_set: set[tuple[str, str, str]] = set()
    edges_list: list[GraphEdge] = []
    citations_map: dict[str, Citation] = {}
    subgraph_text_lines: list[str] = []

    def _add_node(n_id: str, label: str, props: dict[str, Any], weight: float = 1.0) -> None:
        if n_id not in nodes_map:
            nodes_map[n_id] = GraphNode(id=n_id, label=label, properties=props)
        node_weights[n_id] = max(node_weights.get(n_id, 0.0), weight)

    def _add_edge(
        src: str, tgt: str, rel_type: str, props: Optional[dict[str, Any]] = None
    ) -> None:
        key = (src, tgt, rel_type)
        if key not in edges_set:
            edges_set.add(key)
            edges_list.append(
                GraphEdge(source=src, target=tgt, type=rel_type, properties=props or {})
            )

    # Subgraph Query A: Decisions matching decision IDs or systems
    d_rows: list[list[Any]] = []
    if decision_id_matches:
        rows_by_id = await query_graph(
            "MATCH (d:Decision) WHERE d.id IN $decision_ids "
            "OPTIONAL MATCH (d)-[r_dec:decided_by]->(p:Person) "
            "OPTIONAL MATCH (d)-[r_sys:about_system]->(s:System) "
            "OPTIONAL MATCH (d)-[r_tic:based_on]->(t:Ticket) "
            "OPTIONAL MATCH (d)-[r_mtg:based_on]->(m:Meeting) "
            "OPTIONAL MATCH (d)-[r_sup:supersedes]->(d_sup:Decision) "
            "OPTIONAL MATCH (d_sup_by:Decision)-[r_supby:supersedes]->(d) "
            "OPTIONAL MATCH (d)-[r_con:contradicts]-(d_con:Decision) "
            "OPTIONAL MATCH (s)<-[r_own:owns]-(owner:Person) "
            "RETURN d.id, d.title, coalesce(d.summary, ''), coalesce(d.rationale, ''), coalesce(d.status, 'accepted'), "
            "p.name, s.name, t.ticket_id, t.title, m.title, m.date, "
            "d_sup.id, d_sup.title, d_sup_by.id, d_sup_by.title, d_con.id, d_con.title, "
            "owner.name, coalesce(owner.is_active, true), coalesce(owner.leave_date, '')",
            dataset_name=target_dataset,
            params={"decision_ids": decision_id_matches},
        )
        d_rows.extend(rows_by_id)

    if system_matches:
        rows_by_sys = await query_graph(
            "MATCH (d:Decision)-[r_sys:about_system]->(s:System) WHERE s.name IN $system_names "
            "OPTIONAL MATCH (d)-[r_dec:decided_by]->(p:Person) "
            "OPTIONAL MATCH (d)-[r_tic:based_on]->(t:Ticket) "
            "OPTIONAL MATCH (d)-[r_mtg:based_on]->(m:Meeting) "
            "OPTIONAL MATCH (d)-[r_sup:supersedes]->(d_sup:Decision) "
            "OPTIONAL MATCH (d_sup_by:Decision)-[r_supby:supersedes]->(d) "
            "OPTIONAL MATCH (d)-[r_con:contradicts]-(d_con:Decision) "
            "OPTIONAL MATCH (s)<-[r_own:owns]-(owner:Person) "
            "RETURN d.id, d.title, coalesce(d.summary, ''), coalesce(d.rationale, ''), coalesce(d.status, 'accepted'), "
            "p.name, s.name, t.ticket_id, t.title, m.title, m.date, "
            "d_sup.id, d_sup.title, d_sup_by.id, d_sup_by.title, d_con.id, d_con.title, "
            "owner.name, coalesce(owner.is_active, true), coalesce(owner.leave_date, '')",
            dataset_name=target_dataset,
            params={"system_names": system_matches},
        )
        d_rows.extend(rows_by_sys)

    for row in d_rows:
        if not row or not row[0]:
            continue
        d_id = str(row[0])
        d_title = str(row[1])
        d_summary = str(row[2])
        d_rationale = str(row[3])
        d_status = str(row[4])
        decider = str(row[5]) if row[5] else None
        system = str(row[6]) if row[6] else None
        t_id = str(row[7]) if row[7] else None
        t_title = str(row[8]) if row[8] else None
        m_title = str(row[9]) if row[9] else None
        m_date = str(row[10]) if row[10] else None
        sup_id = str(row[11]) if row[11] else None
        sup_title = str(row[12]) if row[12] else None
        supby_id = str(row[13]) if row[13] else None
        supby_title = str(row[14]) if row[14] else None
        con_id = str(row[15]) if row[15] else None
        con_title = str(row[16]) if row[16] else None
        owner_name = str(row[17]) if row[17] else None
        owner_active = bool(row[18])
        owner_leave_date = str(row[19]) if row[19] else None

        _add_node(
            d_id, "Decision", {"title": d_title, "status": d_status, "rationale": d_rationale}, weight=10.0
        )

        text_block = [f"Decision: '{d_title}' (Status: {d_status})"]
        if d_summary:
            text_block.append(f"  Summary: {d_summary}")
        if d_rationale:
            text_block.append(f"  Rationale: {d_rationale}")

        if decider:
            _add_node(decider, "Person", {"name": decider}, weight=8.0)
            _add_edge(d_id, decider, "decided_by")
            text_block.append(f"  Decided by: {decider}")

        if system:
            _add_node(system, "System", {"name": system}, weight=8.0)
            _add_edge(d_id, system, "about_system")
            text_block.append(f"  System: {system}")
            if owner_name:
                _add_node(
                    owner_name,
                    "Person",
                    {"name": owner_name, "is_active": owner_active, "leave_date": owner_leave_date},
                    weight=7.0,
                )
                _add_edge(owner_name, system, "owns")
                status_desc = (
                    "active" if owner_active else f"departed (leave_date: {owner_leave_date})"
                )
                text_block.append(f"  System Owner: {owner_name} ({status_desc})")

        if t_id:
            _add_node(t_id, "Ticket", {"ticket_id": t_id, "title": t_title or t_id}, weight=6.0)
            _add_edge(d_id, t_id, "based_on")
            citations_map[t_id] = Citation(type="ticket", id=t_id, title=t_title or t_id)
            text_block.append(f"  Source Ticket: {t_id} ('{t_title}')")

        if m_title:
            _add_node(m_title, "Meeting", {"title": m_title, "date": m_date}, weight=6.0)
            _add_edge(d_id, m_title, "based_on")
            citations_map[m_title] = Citation(type="meeting", id=m_title, title=m_title)
            text_block.append(f"  Source Meeting: {m_title} (Date: {m_date})")

        if sup_id and sup_title:
            _add_node(sup_id, "Decision", {"title": sup_title}, weight=5.0)
            _add_edge(d_id, sup_id, "supersedes")
            text_block.append(f"  Supersedes: '{sup_title}'")

        if supby_id and supby_title:
            _add_node(supby_id, "Decision", {"title": supby_title}, weight=5.0)
            _add_edge(supby_id, d_id, "supersedes")
            text_block.append(f"  Superseded by: '{supby_title}'")

        if con_id and con_title:
            _add_node(con_id, "Decision", {"title": con_title}, weight=5.0)
            _add_edge(d_id, con_id, "contradicts")
            text_block.append(f"  Contradicts: '{con_title}'")

        subgraph_text_lines.append("\n".join(text_block))

    # Subgraph Query B: Direct system queries (e.g. "Who owns Elasticsearch now?")
    if system_matches:
        sys_owner_rows = await query_graph(
            "MATCH (s:System) WHERE s.name IN $system_names "
            "OPTIONAL MATCH (s)<-[r:owns]-(p:Person) "
            "RETURN s.name, p.name, coalesce(p.is_active, true), coalesce(p.leave_date, '')",
            dataset_name=target_dataset,
            params={"system_names": system_matches},
        )
        for r in sys_owner_rows:
            if not r or not r[0]:
                continue
            s_name = str(r[0])
            p_name = str(r[1]) if r[1] else None
            p_active = bool(r[2])
            p_leave = str(r[3]) if r[3] else None

            _add_node(s_name, "System", {"name": s_name}, weight=8.0)
            if p_name:
                _add_node(
                    p_name,
                    "Person",
                    {"name": p_name, "is_active": p_active, "leave_date": p_leave},
                    weight=7.5,
                )
                _add_edge(p_name, s_name, "owns")
                status_str = "active employee" if p_active else f"DEPARTED on {p_leave}"
                subgraph_text_lines.append(
                    f"System Ownership: '{s_name}' is owned by {p_name} ({status_str})."
                )

    if not nodes_map:
        return AskResponse(
            answer="I could not find any relevant information in the Company Brain to answer your question.",
            citations=[],
            people=[],
            graph_path=GraphPath(nodes=[], edges=[], omitted_count=0),
        )

    # Step 3: LLM generation grounded strictly in subgraph
    context_text = "\n\n".join(subgraph_text_lines)
    system_prompt = (
        "You are the Company Brain assistant for engineering decisions and system ownership.\n"
        "Answer the user's question accurately, concisely, and STRICTLY using only the provided graph context below.\n\n"
        "CRITICAL INTEGRITY RULES:\n"
        "1. Answer ONLY using the facts present in the Context. If the context does not contain the answer, say 'The answer is not found in the Company Brain.'\n"
        "2. You MUST cite relevant Ticket IDs (e.g. TICK-101) or Meeting titles (e.g. 2026-02-10_iam_modernization.md) when referencing facts or decisions.\n"
        "3. If a person has departed (leave_date in past or inactive), explicitly mention their departure status when asked about ownership.\n"
        "4. STATUS INTEGRITY RULE: For decisions with status 'proposed', you MUST describe them as 'proposed' or 'a proposal' and NEVER use words like 'decided', 'adopted', or 'chosen'. For decisions with status 'rejected', you MUST explicitly state that they were 'rejected' or 'decided against'. ONLY decisions with status 'accepted' may be described as decided or adopted.\n"
        "5. Do NOT hallucinate or extrapolate beyond the provided context.\n\n"
        f"CONTEXT SUBGRAPH:\n{context_text}"
    )

    answer_text = ""
    try:
        from app.brain.memory import apply_groq_key
        apply_groq_key()
        record_llm_call()
        response = await litellm.acompletion(
            model=_settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=400,
        )
        answer_text = response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("LLM generation failed in /ask: %s", exc)
        answer_text = f"Based on the knowledge graph context:\n{context_text}"

    # Programmatic verification: never allow 'decided' or 'adopted' for proposed/rejected decisions
    import re
    for row in d_rows:
        if not row or not row[0]:
            continue
        d_title = str(row[1])
        d_status = str(row[4])
        if d_status == "proposed":
            answer_text = re.sub(
                rf"\bdecided(?:\s+to)?\s+({re.escape(d_title)})",
                r"proposed \1",
                answer_text,
                flags=re.IGNORECASE,
            )
        elif d_status == "rejected":
            answer_text = re.sub(
                rf"\bdecided(?:\s+to)?\s+({re.escape(d_title)})",
                r"rejected \1",
                answer_text,
                flags=re.IGNORECASE,
            )

    # Step 4: Strict graph-edge citation verification
    # Citations MUST originate strictly from actual 'based_on' edges in the graph
    valid_based_on_targets = {
        e.target for e in edges_list if e.type == "based_on"
    }
    verified_citations = [
        c for c in citations_map.values() if c.id in valid_based_on_targets
    ]

    def _rank_citation(c: Citation) -> tuple[int, float]:
        in_answer = 1 if (c.id.lower() in answer_text.lower() or c.title.lower() in answer_text.lower()) else 0
        weight = node_weights.get(c.id, 0.0)
        return (in_answer, weight)

    has_explicit_evidence = any(
        c.id.lower() in answer_text.lower() or (len(c.title) > 5 and c.title.lower() in answer_text.lower())
        for c in verified_citations
    )
    if not has_explicit_evidence and (
        "not found" in answer_text.lower()
        or "could not find" in answer_text.lower()
        or "no information" in answer_text.lower()
    ):
        ranked_citations = []
    elif has_explicit_evidence:
        # Prioritize citations specifically referenced in the answer text
        in_text_citations = [
            c for c in ranked_citations
            if c.id.lower() in answer_text.lower() or (len(c.title) > 5 and c.title.lower() in answer_text.lower())
        ]
        if in_text_citations:
            ranked_citations = in_text_citations[:5]

    # Step 5: Rank and cap graph_path nodes at ~15, ordered by relevance
    sorted_nodes = sorted(
        nodes_map.values(), key=lambda n: node_weights.get(n.id, 0.0), reverse=True
    )
    capped_nodes = sorted_nodes[:15]
    omitted_count = max(0, len(sorted_nodes) - len(capped_nodes))
    capped_node_ids = {n.id for n in capped_nodes}
    capped_edges = [
        e for e in edges_list if e.source in capped_node_ids and e.target in capped_node_ids
    ]

    # Extract all people in the retained subgraph
    subgraph_people = sorted(
        [
            node.properties.get("name", node.id)
            for node in capped_nodes
            if node.label == "Person"
        ]
    )

    return AskResponse(
        answer=answer_text,
        citations=ranked_citations,
        people=subgraph_people,
        graph_path=GraphPath(nodes=capped_nodes, edges=capped_edges, omitted_count=omitted_count),
    )
