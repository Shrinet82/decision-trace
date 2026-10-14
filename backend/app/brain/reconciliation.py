"""Post-ingest reconciliation for Decision-Trace knowledge graph.

Resolves entity identity discrepancies, deduplicates near-identical Decision nodes,
re-points incoming and outgoing edges, and preserves provenance.
"""

import logging
import re
from typing import Any, Optional

import numpy as np
from fastembed import TextEmbedding

from app.brain.memory import query_graph

logger = logging.getLogger("decision_trace.reconciliation")

_embedding_model: Optional[TextEmbedding] = None


def get_embedding_model() -> TextEmbedding:
    """Get or lazily initialize the shared local TextEmbedding model."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedding_model


def normalize_title(title: str) -> str:
    """Normalize a title by stripping whitespace, punctuation, and slug formatting."""
    cleaned = re.sub(r"[-_]+", " ", title.strip().lower())
    return re.sub(r"\s+", " ", cleaned)


def compute_embedding_similarity(text1: str, text2: str) -> float:
    """Compute cosine similarity between two texts using fastembed."""
    norm1 = normalize_title(text1)
    norm2 = normalize_title(text2)
    if norm1 == norm2:
        return 1.0

    model = get_embedding_model()
    embeddings = list(model.embed([norm1, norm2]))
    v1 = np.array(embeddings[0], dtype=np.float32)
    v2 = np.array(embeddings[1], dtype=np.float32)

    denom = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denom == 0:
        return 0.0
    return float(np.dot(v1, v2) / denom)


def is_stub_node(decision: dict[str, Any]) -> bool:
    """Determine whether a Decision node is an unresolved stub or reference placeholder."""
    summary = (decision.get("summary") or "").strip()
    rationale = (decision.get("rationale") or "").strip()
    title = decision.get("title") or ""

    # Stub if summary and rationale are empty
    if not summary and not rationale:
        return True
    # Stub if title is formatted as a kebab-case slug
    if "-" in title and " " not in title:
        return True
    return False


def pick_canonical_decision(
    d1: dict[str, Any], d2: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Determine which decision node is canonical and which is the duplicate to merge.

    Returns:
        (canonical, duplicate)
    """
    d1_is_stub = is_stub_node(d1)
    d2_is_stub = is_stub_node(d2)

    if d1_is_stub and not d2_is_stub:
        return d2, d1
    if d2_is_stub and not d1_is_stub:
        return d1, d2

    # If both or neither are stubs, prefer the one with richer summary/rationale
    d1_len = len(d1.get("summary") or "") + len(d1.get("rationale") or "")
    d2_len = len(d2.get("summary") or "") + len(d2.get("rationale") or "")
    if d1_len > d2_len:
        return d1, d2
    if d2_len > d1_len:
        return d2, d1

    # Tiebreak on title length or lower ID
    if len(d1.get("title", "")) >= len(d2.get("title", "")):
        return d1, d2
    return d2, d1


def extract_action_keywords(title: str, system: Optional[str] = None) -> set[str]:
    """Extract substantive purpose and action tokens from a decision title."""
    stopwords = {
        "adopt",
        "use",
        "migrate",
        "switch",
        "deploy",
        "implement",
        "to",
        "from",
        "for",
        "in",
        "of",
        "the",
        "a",
        "an",
        "and",
        "or",
        "on",
        "with",
        "by",
        "all",
        "our",
        "new",
        "cluster",
        "service",
        "services",
        "system",
        "database",
    }
    cleaned = re.sub(r"[-_]+", " ", title.strip().lower())
    if system:
        stopwords.update(normalize_title(system).split())
    tokens = set(cleaned.split())
    return {t for t in tokens if t not in stopwords and len(t) > 2}


def can_merge_decisions(
    d1: dict[str, Any], d2: dict[str, Any], similarity: float, threshold: float = 0.88
) -> bool:
    """Evaluate whether two decision nodes represent the same underlying decision."""
    if similarity < threshold:
        return False

    # Tiebreak rule 1: Systems must not conflict if both are explicitly present
    sys1 = (d1.get("system") or "").strip().lower()
    sys2 = (d2.get("system") or "").strip().lower()
    if sys1 and sys2 and sys1 != sys2:
        # Check if one is a substring of the other (e.g. 'redis' vs 'redis cluster')
        if sys1 not in sys2 and sys2 not in sys1:
            return False

    # Tiebreak rule 2: Decider must not conflict if both are explicitly present
    p1 = (d1.get("person") or "").strip().lower()
    p2 = (d2.get("person") or "").strip().lower()
    if p1 and p2 and p1 != p2:
        return False

    # Tiebreak rule 3: Distinct actions/purposes on the same system must not merge
    # (e.g. 'Adopt Redis for sessions' vs 'Adopt Redis for rate limiting')
    if not (is_stub_node(d1) or is_stub_node(d2)):
        k1 = extract_action_keywords(d1.get("title", ""), sys1)
        k2 = extract_action_keywords(d2.get("title", ""), sys2)
        if k1 and k2 and not (k1 & k2):
            return False

    return True


async def cleanup_empty_stubs(dataset_name: Optional[str] = None) -> int:
    """Remove empty/placeholder nodes created when LLMs output empty strings."""
    cleaned = 0
    queries = [
        "MATCH (t:Ticket) WHERE t.ticket_id = '' OR t.ticket_id IS NULL DETACH DELETE t",
        "MATCH (m:Meeting) WHERE m.title = '' OR m.title IS NULL DETACH DELETE m",
        "MATCH (s:System) WHERE s.name = '' OR s.name IS NULL DETACH DELETE s",
        "MATCH (p:Person) WHERE p.name = '' OR p.name IS NULL DETACH DELETE p",
        "MATCH (d:Decision) WHERE d.title = '' OR d.title IS NULL DETACH DELETE d",
    ]
    for q in queries:
        try:
            await query_graph(q, dataset_name=dataset_name)
            cleaned += 1
        except Exception as exc:
            logger.debug("Cleanup query failed: %s", exc)

    # Normalize system names with 'System: ' prefix
    try:
        sys_res = await query_graph(
            "MATCH (s:System) WHERE s.name STARTS WITH 'System:' RETURN id(s), s.name",
            dataset_name=dataset_name,
        )
        for row in sys_res:
            sid, name = row[0], row[1]
            clean_name = re.sub(r"^System:\s*", "", name, flags=re.IGNORECASE).strip()
            existing = await query_graph(
                f"MATCH (clean:System) WHERE clean.name = '{clean_name}' RETURN id(clean)",
                dataset_name=dataset_name,
            )
            if existing:
                clean_id = existing[0][0]
                await query_graph(
                    f"MATCH (src)-[r]->(old:System) WHERE id(old) = {sid} "
                    f"MATCH (clean:System) WHERE id(clean) = {clean_id} "
                    f"MERGE (src)-[new_r:about_system]->(clean)",
                    dataset_name=dataset_name,
                )
                await query_graph(
                    f"MATCH (s:System) WHERE id(s) = {sid} DETACH DELETE s",
                    dataset_name=dataset_name,
                )
            else:
                await query_graph(
                    f"MATCH (s:System) WHERE id(s) = {sid} SET s.name = '{clean_name}'",
                    dataset_name=dataset_name,
                )
    except Exception as exc:
        logger.debug("System normalization error: %s", exc)

    return cleaned


async def reconcile_decisions(
    dataset_name: Optional[str] = None, similarity_threshold: float = 0.88
) -> dict[str, Any]:
    """Find and merge near-duplicate Decision nodes, re-point edges, and preserve provenance.

    Args:
        dataset_name: Target dataset name.
        similarity_threshold: Minimum cosine similarity to consider two decisions duplicates.

    Returns:
        dict summarizing merged decisions and cleaned stubs.
    """
    await cleanup_empty_stubs(dataset_name=dataset_name)

    query = (
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
        "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
        "RETURN id(d) as id, d.title as title, d.summary as summary, "
        "d.rationale as rationale, d.status as status, p.name as person, s.name as system"
    )
    results = await query_graph(query, dataset_name=dataset_name)
    if not results or len(results) < 2:
        return {"merged_count": 0, "merges": []}

    decisions: list[dict[str, Any]] = [
        {
            "id": row[0],
            "title": row[1] or "",
            "summary": row[2] or "",
            "rationale": row[3] or "",
            "status": row[4] or "active",
            "person": row[5] or "",
            "system": row[6] or "",
        }
        for row in results
        if row and row[1]
    ]

    merges: list[dict[str, Any]] = []
    merged_ids: set[int] = set()

    for i in range(len(decisions)):
        d1 = decisions[i]
        if d1["id"] in merged_ids:
            continue

        for j in range(i + 1, len(decisions)):
            d2 = decisions[j]
            if d2["id"] in merged_ids:
                continue

            sim = compute_embedding_similarity(d1["title"], d2["title"])
            if can_merge_decisions(d1, d2, sim, similarity_threshold):
                canonical, duplicate = pick_canonical_decision(d1, d2)
                can_id, dup_id = canonical["id"], duplicate["id"]
                can_title, dup_title = canonical["title"], duplicate["title"]

                logger.info(
                    "Reconciling duplicate decision: '%s' -> canonical: '%s' (sim=%.3f)",
                    dup_title,
                    can_title,
                    sim,
                )

                # 1. Re-point incoming edges to duplicate node
                incoming_edges = await query_graph(
                    f"MATCH (src)-[r]->(dup:Decision) WHERE id(dup) = {dup_id} AND id(src) <> {can_id} "
                    f"RETURN id(src), type(r)",
                    dataset_name=dataset_name,
                )
                for edge in incoming_edges:
                    src_id, rel_type = edge[0], edge[1]
                    await query_graph(
                        f"MATCH (src), (can:Decision) WHERE id(src) = {src_id} AND id(can) = {can_id} "
                        f"MERGE (src)-[:{rel_type}]->(can)",
                        dataset_name=dataset_name,
                    )

                # 2. Re-point outgoing edges from duplicate node
                outgoing_edges = await query_graph(
                    f"MATCH (dup:Decision)-[r]->(tgt) WHERE id(dup) = {dup_id} AND id(tgt) <> {can_id} "
                    f"RETURN id(tgt), type(r)",
                    dataset_name=dataset_name,
                )
                for edge in outgoing_edges:
                    tgt_id, rel_type = edge[0], edge[1]
                    await query_graph(
                        f"MATCH (can:Decision), (tgt) WHERE id(can) = {can_id} AND id(tgt) = {tgt_id} "
                        f"MERGE (can)-[:{rel_type}]->(tgt)",
                        dataset_name=dataset_name,
                    )

                # 3. Preserve provenance on canonical node
                escaped_dup_title = dup_title.replace("'", "\\'")
                await query_graph(
                    f"MATCH (can:Decision) WHERE id(can) = {can_id} "
                    f"SET can.merged_titles = coalesce(can.merged_titles, []) + ['{escaped_dup_title}']",
                    dataset_name=dataset_name,
                )

                # 4. Detach and delete duplicate node
                await query_graph(
                    f"MATCH (dup:Decision) WHERE id(dup) = {dup_id} DETACH DELETE dup",
                    dataset_name=dataset_name,
                )

                merged_ids.add(dup_id)
                merges.append(
                    {
                        "canonical_title": can_title,
                        "merged_title": dup_title,
                        "similarity": sim,
                    }
                )

                # If d1 was the duplicate, break inner loop to avoid using it further
                if dup_id == d1["id"]:
                    break

    logger.info("Decision reconciliation completed: merged %d nodes.", len(merges))
    return {"merged_count": len(merges), "merges": merges}
