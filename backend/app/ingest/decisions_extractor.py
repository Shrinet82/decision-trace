"""Two-Pass LLM Decision Extraction Engine with Concurrency, Rate Limiting, and Telemetry.

Pass 1 (Recall): Extracts candidate engineering decisions with verbatim evidence quotes.
Pass 2 (Precision): Verifies each candidate against its verbatim quote, drops weak/non-decisions,
and resolves deciders and systems to canonical entities.
Links supersedes and contradicts relationships, re-points edges, and reconciles identities.
"""

import asyncio
import csv
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from app.config import export_cognee_env, get_settings
_settings = get_settings()
export_cognee_env(_settings)

import litellm
from litellm.caching import Cache
from cognee.infrastructure.llm.LLMGateway import LLMGateway
from litellm.integrations.custom_logger import CustomLogger
from pydantic import BaseModel, Field

from app.brain.memory import (
    apply_groq_key,
    build_pass1_prompt,
    build_pass2_prompt,
    get_entity_roster,
    get_existing_decision_titles,
    get_or_create_dataset_graph_name,
    query_graph,
    rotate_groq_key,
)
from app.brain.reconciliation import compute_embedding_similarity, reconcile_decisions
from app.ingest.notes_source import parse_meeting_note

logger = logging.getLogger("decision_trace.ingest.decisions")
export_cognee_env(_settings)
apply_groq_key()

# Initialize fresh extraction cache keyed by model + prompt version
model_slug = _settings.LLM_MODEL.replace("/", "_").replace(":", "_").replace(".", "_")
prompt_version = os.getenv("PROMPT_VERSION", "v1")
cache_dir = Path(".cache") / "extractions" / f"{model_slug}_{prompt_version}"
cache_dir.mkdir(parents=True, exist_ok=True)
litellm.cache = Cache(type="disk", disk_cache_dir=str(cache_dir))
litellm.enable_cache()

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_TICKETS_PATH = DEFAULT_DATA_DIR / "tickets.csv"
DEFAULT_NOTES_DIR = DEFAULT_DATA_DIR / "meeting_notes"


class CandidateDecision(BaseModel):
    """Candidate decision extracted during high-recall Pass 1."""

    title: str = Field(..., description="Concise title of the decision")
    verbatim_quote: str = Field(
        ...,
        description="Exact verbatim text excerpt from the document that serves as proof of the choice",
    )
    system: Optional[str] = Field(None, description="System/database/tool/service involved, or null")
    decided_by: Optional[str] = Field(None, description="Person who made or authorized the decision, or null")
    status: Literal["accepted", "proposed", "rejected", "reverted"] = Field(
        default="accepted", description="Status of the decision"
    )
    confidence: float = Field(default=0.8, description="Extraction confidence score (0.0 to 1.0)")
    rationale: str = Field(default="", description="Why the choice was made, constraints, or trade-offs")
    supersedes: list[str] = Field(
        default_factory=list, description="Titles of prior decisions superseded by this decision"
    )
    contradicts: list[str] = Field(
        default_factory=list, description="Titles of decisions contradicted by this decision"
    )


class Pass1Candidates(BaseModel):
    """Container model for Pass 1 extraction output."""

    candidates: list[CandidateDecision] = Field(default_factory=list)


class Pass2Verification(BaseModel):
    """Verification assessment produced by precision Pass 2."""

    was_choice_made: bool = Field(
        ..., description="Was a definitive choice about technology, vendor, process, or policy made in the quote?"
    )
    is_decision_not_status_or_bug: bool = Field(
        ...,
        description="Is this an actual decision rather than a bug fix, pod restart, temporary incident triage, or routine task update?",
    )
    decided_by_verified: Optional[str] = Field(
        None, description="Verified full name of the decider resolved from the text/roster, or null"
    )
    system_verified: Optional[str] = Field(None, description="Verified canonical system name, or null")
    refined_title: str = Field(..., description="Clean, precise canonical decision title")
    keep: bool = Field(
        ...,
        description="True if this is a valid decision supported by the quote; False if weak, routine bug, or non-decision",
    )
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection if keep is False")


class TokenUsageTracker(CustomLogger):
    """Tracks token usage across all LLM calls executed via LiteLLM."""

    def __init__(self) -> None:
        super().__init__()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.call_count = 0
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self._registered = False

    def reset_delta(self) -> None:
        """Reset the per-document token delta counters."""
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0

    def reset_all(self) -> None:
        """Reset all cumulative and delta token counters."""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.call_count = 0
        self.reset_delta()

    def _record_usage(self, response_obj: Any) -> None:
        usage = getattr(response_obj, "usage", None)
        if usage:
            p = getattr(usage, "prompt_tokens", 0) or 0
            c = getattr(usage, "completion_tokens", 0) or 0
            t = getattr(usage, "total_tokens", 0) or (p + c)
            self.prompt_tokens += p
            self.completion_tokens += c
            self.total_tokens += t
            self.last_prompt_tokens += p
            self.last_completion_tokens += c
            self.last_total_tokens += t
            self.call_count += 1

    def callback(
        self, kwargs: Any, completion_response: Any, start_time: Any, end_time: Any
    ) -> None:
        """LiteLLM success callback hook to capture exact token usage."""
        self._record_usage(completion_response)

    async def async_log_success_event(
        self, kwargs: Any, response_obj: Any, start_time: Any, end_time: Any
    ) -> None:
        """LiteLLM async success logger hook for native async completion."""
        self._record_usage(response_obj)

    def register(self) -> None:
        """Register callback with litellm if not already registered."""
        if not self._registered:
            if litellm.success_callback is None:
                litellm.success_callback = []
            litellm.success_callback.append(self.callback)
            if litellm.callbacks is None:
                litellm.callbacks = []
            litellm.callbacks.append(self)
            self._registered = True


# Global singleton tracker instance
token_tracker = TokenUsageTracker()
token_tracker.register()


async def _save_verified_decision(
    candidate: CandidateDecision,
    verification: Pass2Verification,
    item: dict[str, Any],
    dataset_name: str,
) -> str:
    """Save a verified decision node and its relationships directly into FalkorDB."""
    decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    title = verification.refined_title.strip() or candidate.title.strip()
    rationale = candidate.rationale.strip()
    summary = rationale or title
    status = candidate.status or "accepted"
    confidence = candidate.confidence if candidate.confidence is not None else 1.0
    evidence_quote = candidate.verbatim_quote.strip()
    date_val = item.get("date")

    # 1. Merge Decision node
    create_q = (
        "MERGE (d:Decision {title: $title}) "
        "ON CREATE SET d.id = $id, d.summary = $summary, d.rationale = $rationale, "
        "              d.status = $status, d.confidence = $confidence, "
        "              d.evidence_quote = $evidence_quote, d.decided_on = $decided_on "
        "ON MATCH SET d.summary = $summary, d.rationale = $rationale, "
        "             d.status = $status, d.confidence = $confidence, "
        "             d.evidence_quote = $evidence_quote"
    )
    await query_graph(
        create_q,
        dataset_name=dataset_name,
        params={
            "title": title,
            "id": decision_id,
            "summary": summary,
            "rationale": rationale,
            "status": status,
            "confidence": confidence,
            "evidence_quote": evidence_quote,
            "decided_on": date_val,
        },
    )

    # 2. Link decided_by Person
    decider = (verification.decided_by_verified or candidate.decided_by or "").strip()
    if decider:
        # Match Person or create if not present
        await query_graph(
            "MATCH (d:Decision {title: $title}) "
            "MERGE (p:Person {name: $person}) "
            "MERGE (d)-[:decided_by]->(p)",
            dataset_name=dataset_name,
            params={"title": title, "person": decider},
        )

    # 3. Link about_system System
    sys_name = (verification.system_verified or candidate.system or "").strip()
    if sys_name.lower().startswith("system:"):
        sys_name = sys_name[7:].strip()
    if sys_name:
        await query_graph(
            "MATCH (d:Decision {title: $title}) "
            "MERGE (s:System {name: $system}) "
            "MERGE (d)-[:about_system]->(s)",
            dataset_name=dataset_name,
            params={"title": title, "system": sys_name},
        )

    # 4. Link based_on Ticket or Meeting
    if item["type"] == "ticket":
        await query_graph(
            "MATCH (d:Decision {title: $title}) "
            "MERGE (t:Ticket {ticket_id: $ticket_id}) "
            "MERGE (d)-[:based_on]->(t)",
            dataset_name=dataset_name,
            params={"title": title, "ticket_id": item["id"]},
        )
    elif item["type"] == "meeting":
        await query_graph(
            "MATCH (d:Decision {title: $title}) "
            "MERGE (m:Meeting {title: $meeting_title}) "
            "MERGE (d)-[:based_on]->(m)",
            dataset_name=dataset_name,
            params={"title": title, "meeting_title": item["id"]},
        )

    return title


async def extract_all_decisions(
    dataset_name: Optional[str] = None,
    tickets_path: Optional[str | Path] = None,
    notes_dir: Optional[str | Path] = None,
    concurrency_limit: int = 3,
    include_all_tickets: bool = True,
    pause_between_calls: float = 0.5,
) -> dict[str, Any]:
    """Run Two-Pass LLM decision extraction over ticket comments and meeting note bodies.

    Args:
        dataset_name: Target dataset name.
        tickets_path: Path to tickets.csv.
        notes_dir: Directory containing meeting notes markdown files.
        concurrency_limit: Maximum concurrent extraction tasks (default 3 with backoff).
        include_all_tickets: If True, processes all tickets.
        pause_between_calls: Seconds to sleep between calls.

    Returns:
        dict: Summary of extracted decisions, token usage, timing, and costs.
    """
    target_dataset = dataset_name or _settings.DATASET_NAME
    await get_or_create_dataset_graph_name(target_dataset)
    t_path = Path(tickets_path or DEFAULT_TICKETS_PATH)
    n_dir = Path(notes_dir or DEFAULT_NOTES_DIR)

    token_tracker.reset_all()
    overall_start = time.perf_counter()

    # 1. Prepare items to extract
    items: list[dict[str, Any]] = []

    # Tickets: load all tickets from CSV
    if t_path.exists():
        with open(t_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                comment = (row.get("comments") or "").strip()
                if not comment:
                    continue
                # Skip routine operational incident triage comments with boilerplate closure
                comment_lower = comment.lower()
                if "applied configuration fix in staging" in comment_lower and "ticket resolved" in comment_lower:
                    continue
                text = (
                    f"Source Type: Ticket\n"
                    f"Ticket ID: {row['ticket_id']}\n"
                    f"Title: {row.get('title', '')}\n"
                    f"Reporter: {row.get('reporter', '')}\n"
                    f"Assignee: {row.get('assignee', '')}\n"
                    f"System: {row.get('system', '')}\n"
                    f"Comment: {comment}"
                )
                items.append(
                    {
                        "id": row["ticket_id"],
                        "type": "ticket",
                        "text": text,
                        "date": row.get("closed") or row.get("opened"),
                    }
                )

    # Meeting Notes: load from markdown files
    if n_dir.exists():
        for note_file in sorted(n_dir.glob("*.md")):
            content = note_file.read_text(encoding="utf-8")
            parsed = parse_meeting_note(content, note_file.name)
            notes_body = parsed.get("notes", "").strip()
            if not notes_body:
                continue
            text = (
                f"Source Type: Meeting\n"
                f"Meeting Title: {parsed['title']}\n"
                f"Date: {parsed['date']}\n"
                f"Attended by: {', '.join(parsed['attendees'])}\n"
                f"Note Content: {notes_body}"
            )
            items.append(
                {
                    "id": parsed["title"],
                    "type": "meeting",
                    "text": text,
                    "date": parsed["date"],
                }
            )

    total_items = len(items)
    print(f"Active Extraction Model: {_settings.LLM_MODEL} (temperature=0)")
    logger.info("Active Extraction Model: %s (temperature=0)", _settings.LLM_MODEL)
    logger.info(
        "Starting Two-Pass Decision Extraction for %d items into dataset '%s' (concurrency: %d)...",
        total_items,
        target_dataset,
        concurrency_limit,
    )

    roster = await get_entity_roster(target_dataset)
    existing_titles = await get_existing_decision_titles(target_dataset)
    pass1_prompt = build_pass1_prompt(existing_decision_titles=existing_titles, roster=roster)
    pass2_prompt = build_pass2_prompt(roster=roster)

    semaphore = asyncio.Semaphore(concurrency_limit)
    item_timings: list[dict[str, Any]] = []
    pending_cross_edges: list[tuple[str, list[str], list[str]]] = []
    total_verified_decisions = 0
    parse_failures = 0

    async def _execute_with_retry(fn, *args, **kwargs):
        """Execute LLM call with key rotation and exponential backoff on rate limits / throttling."""
        for attempt in range(1, 6):
            try:
                apply_groq_key()
                return await fn(*args, **kwargs)
            except Exception as exc:
                err_msg = str(exc)
                is_throttled = any(
                    x in err_msg.lower()
                    for x in [
                        "throttling",
                        "throttlingexception",
                        "too many requests",
                        "toomanyrequestsexception",
                        "rate_limit",
                        "ratelimit",
                        "429",
                        "tokens",
                    ]
                )
                if not _settings.LLM_MODEL.startswith("bedrock/") and (
                    "rate_limit" in err_msg.lower() or "429" in err_msg or "tokens" in err_msg.lower()
                ):
                    rotate_groq_key()
                    import re

                    m = re.search(r"try again in ([\d\.]+)s", err_msg)
                    wait_sec = float(m.group(1)) + 1.0 if m else min(2**attempt, 16)
                    logger.warning(
                        "Rate limit on attempt %d/5. Rotated key, sleeping %.1fs: %s",
                        attempt,
                        wait_sec,
                        exc,
                    )
                    await asyncio.sleep(wait_sec)
                elif is_throttled:
                    wait_sec = min(2**attempt, 32)
                    logger.warning(
                        "Throttling on attempt %d/5 (%s). Backing off for %.1fs...",
                        attempt,
                        exc,
                        wait_sec,
                    )
                    await asyncio.sleep(wait_sec)
                elif attempt < 5:
                    wait_sec = min(2**attempt, 8)
                    logger.warning("Call attempt %d failed: %s. Retrying in %.1fs...", attempt, exc, wait_sec)
                    await asyncio.sleep(wait_sec)
                else:
                    logger.error("LLM call failed after 5 attempts: %s", exc)
                    raise

    async def _process_item(index: int, item: dict[str, Any]) -> None:
        nonlocal total_verified_decisions, parse_failures
        async with semaphore:
            token_tracker.reset_delta()
            item_start = time.perf_counter()
            logger.info(
                "[%d/%d] Processing %s '%s'...", index, total_items, item["type"], item["id"]
            )

            # Pass 1: Recall-Oriented Candidate Extraction
            try:
                p1_output = await _execute_with_retry(
                    LLMGateway.acreate_structured_output,
                    text_input=item["text"],
                    system_prompt=pass1_prompt,
                    response_model=Pass1Candidates,
                    max_tokens=1500,
                )
                candidates = p1_output.candidates if hasattr(p1_output, "candidates") else []
            except Exception as exc:
                logger.error("Pass 1 extraction failed for %s: %s", item["id"], exc)
                parse_failures += 1
                candidates = []

            # Pass 2: Precision Verification of Candidates
            verified_count_for_item = 0
            for cand in candidates:
                p2_input = (
                    f"Candidate Title: {cand.title}\n"
                    f"Candidate Decider: {cand.decided_by or 'Unknown'}\n"
                    f"Candidate System: {cand.system or 'None'}\n"
                    f"Candidate Rationale: {cand.rationale}\n"
                    f"Evidence Quote: {cand.verbatim_quote}\n"
                    f"Source Context:\n{item['text']}"
                )
                try:
                    p2_output = await _execute_with_retry(
                        LLMGateway.acreate_structured_output,
                        text_input=p2_input,
                        system_prompt=pass2_prompt,
                        response_model=Pass2Verification,
                        max_tokens=800,
                    )
                    if p2_output.keep:
                        # Safeguard against routine incident closures and bug fixes
                        quote_check = f"{cand.verbatim_quote} {cand.title} {item['text']}".lower()
                        if (
                            "applied configuration fix in staging" in quote_check
                            and "ticket resolved" in quote_check
                        ):
                            logger.info(
                                "Rejecting candidate '%s': routine incident resolution pattern",
                                cand.title,
                            )
                            continue

                        # Save verified decision to FalkorDB
                        saved_title = await _save_verified_decision(
                            cand, p2_output, item, target_dataset
                        )
                        verified_count_for_item += 1
                        total_verified_decisions += 1
                        if cand.supersedes or cand.contradicts:
                            pending_cross_edges.append(
                                (
                                    saved_title,
                                    cand.supersedes,
                                    cand.contradicts,
                                    item["text"],
                                    cand.verbatim_quote,
                                )
                            )
                        logger.info(
                            "Verified decision: '%s' (Decider: %s, System: %s)",
                            saved_title,
                            p2_output.decided_by_verified,
                            p2_output.system_verified,
                        )
                    else:
                        logger.info(
                            "Rejected candidate '%s': %s",
                            cand.title,
                            p2_output.rejection_reason,
                        )
                except Exception as exc:
                    logger.error("Pass 2 verification error for candidate '%s': %s", cand.title, exc)
                    parse_failures += 1

            elapsed = time.perf_counter() - item_start
            delta_tokens = token_tracker.last_total_tokens
            item_timings.append(
                {
                    "id": item["id"],
                    "type": item["type"],
                    "duration_sec": elapsed,
                    "tokens": delta_tokens,
                    "verified_decisions": verified_count_for_item,
                }
            )
            logger.info(
                "[%d/%d] Completed '%s' in %.2fs (verified: %d, delta tokens: %d)",
                index,
                total_items,
                item["id"],
                elapsed,
                verified_count_for_item,
                delta_tokens,
            )
            if pause_between_calls > 0:
                await asyncio.sleep(pause_between_calls)

    # Process all items concurrently
    tasks = [_process_item(i, item) for i, item in enumerate(items, 1)]
    await asyncio.gather(*tasks)

    # 2. Link supersedes and contradicts cross-edges
    logger.info("Resolving supersedes and contradicts cross-edges (%d items)...", len(pending_cross_edges))
    all_dec_rows = await query_graph(
        "MATCH (d:Decision) RETURN id(d), d.title", dataset_name=target_dataset
    )
    title_to_id: dict[str, int] = {str(r[1]).lower(): int(r[0]) for r in all_dec_rows if r and r[0] and r[1]}

    REPLACEMENT_KEYWORDS = {
        "supersede", "supersedes", "superseded",
        "replace", "replaces", "replaced", "replacing",
        "migrate", "migrates", "migrated", "migration",
        "deprecate", "deprecates", "deprecated",
        "decommission", "decommissioned",
        "in favor of", "instead of", "phase out", "phasing out"
    }

    for src_title, sup_list, con_list, doc_text, quote_text in pending_cross_edges:
        src_norm = src_title.strip().lower()
        src_id = title_to_id.get(src_norm)

        # Supersedes
        combined_evidence = f"{doc_text} {quote_text}".lower()
        has_replacement_evidence = any(kw in combined_evidence for kw in REPLACEMENT_KEYWORDS)

        if has_replacement_evidence:
            for sup in sup_list:
                sup_norm = sup.strip().lower()
                # 1. Prevent self-loops
                if sup_norm == src_norm:
                    continue

                # 2. Check if this target is actually marked as contradiction
                is_contradiction = any(
                    c.strip().lower() == sup_norm or compute_embedding_similarity(c, sup) >= 0.75
                    for c in con_list
                )
                if is_contradiction:
                    logger.info("Skipping supersedes '%s' -> '%s' (relationship is contradictory)", src_title, sup)
                    continue

                target_id = title_to_id.get(sup_norm)
                if not target_id:
                    # Fuzzy/embedding similarity match
                    for t, tid in title_to_id.items():
                        if t == src_norm:
                            continue
                        if sup_norm in t or t in sup_norm or compute_embedding_similarity(sup_norm, t) >= 0.75:
                            target_id = tid
                            break

                # Ensure target exists and is NOT the same node as source
                if target_id and target_id != src_id:
                    await query_graph(
                        "MATCH (d1:Decision {title: $src}) "
                        "MATCH (d2:Decision) WHERE id(d2) = $tgt_id AND id(d1) <> id(d2) "
                        "MERGE (d1)-[:supersedes]->(d2)",
                        dataset_name=target_dataset,
                        params={"src": src_title, "tgt_id": target_id},
                    )
        else:
            if sup_list:
                logger.info(
                    "Skipping supersedes for '%s': text lacks explicit replacement keywords",
                    src_title,
                )

        # Contradicts
        for con in con_list:
            con_norm = con.strip().lower()
            if con_norm == src_norm:
                continue
            target_id = title_to_id.get(con_norm)
            if not target_id:
                for t, tid in title_to_id.items():
                    if t == src_norm:
                        continue
                    if con_norm in t or t in con_norm or compute_embedding_similarity(con_norm, t) >= 0.75:
                        target_id = tid
                        break
            if target_id and target_id != src_id:
                await query_graph(
                    "MATCH (d1:Decision {title: $src}) "
                    "MATCH (d2:Decision) WHERE id(d2) = $tgt_id AND id(d1) <> id(d2) "
                    "MERGE (d1)-[:contradicts]->(d2)",
                    dataset_name=target_dataset,
                    params={"src": src_title, "tgt_id": target_id},
                )

    # 3. Post-extraction reconciliation
    reconcile_res = await reconcile_decisions(dataset_name=target_dataset)
    logger.info("Post-extraction reconciliation: %s", reconcile_res)

    total_time = time.perf_counter() - overall_start

    # Dynamic token pricing based on active model
    active_model = _settings.LLM_MODEL.lower()
    if "deepseek" in active_model:
        prompt_rate = 0.62  # $0.62 per 1M input tokens
        comp_rate = 1.85    # $1.85 per 1M output tokens
    elif "nova-lite" in active_model:
        prompt_rate = 0.06  # $0.06 per 1M input tokens
        comp_rate = 0.24    # $0.24 per 1M output tokens
    else:
        prompt_rate = 0.20
        comp_rate = 0.20

    prompt_cost = (token_tracker.prompt_tokens / 1_000_000) * prompt_rate
    comp_cost = (token_tracker.completion_tokens / 1_000_000) * comp_rate
    total_cost_usd = prompt_cost + comp_cost

    summary = {
        "items_processed": total_items,
        "total_verified_decisions": total_verified_decisions,
        "total_time_seconds": round(total_time, 2),
        "total_tokens": token_tracker.total_tokens,
        "prompt_tokens": token_tracker.prompt_tokens,
        "completion_tokens": token_tracker.completion_tokens,
        "llm_calls": token_tracker.call_count,
        "estimated_cost_usd": round(total_cost_usd, 6),
        "parse_failures": parse_failures,
        "reconciliation": reconcile_res,
        "item_timings": item_timings,
    }
    logger.info(
        "Two-Pass Decision Extraction finished in %.2fs | Verified: %d | Total tokens: %d | Est cost: $%.5f",
        total_time,
        total_verified_decisions,
        token_tracker.total_tokens,
        total_cost_usd,
    )
    return summary
