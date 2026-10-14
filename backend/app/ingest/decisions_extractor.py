"""LLM Decision Extraction Engine with Batching, Rate Limiting, and Telemetry.

Extracts Decision nodes from ticket comments and meeting note bodies,
linking them to existing Person, System, Ticket, and Meeting nodes, and
resolving supersedes/contradicts relationships using the roster and top-N titles.
"""

import asyncio
import csv
import logging
import time
from pathlib import Path
from typing import Any, Optional

import litellm
from litellm.integrations.custom_logger import CustomLogger

from app.brain.memory import get_or_create_dataset_graph_name, ingest_text, query_graph
from app.brain.reconciliation import reconcile_decisions
from app.config import get_settings
from app.ingest.notes_source import parse_meeting_note

logger = logging.getLogger("decision_trace.ingest.decisions")
_settings = get_settings()

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_TICKETS_PATH = DEFAULT_DATA_DIR / "tickets.csv"
DEFAULT_NOTES_DIR = DEFAULT_DATA_DIR / "meeting_notes"


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


async def extract_all_decisions(
    dataset_name: Optional[str] = None,
    tickets_path: Optional[str | Path] = None,
    notes_dir: Optional[str | Path] = None,
    concurrency_limit: int = 1,
    include_all_tickets: bool = True,
    pause_between_calls: float = 1.0,
) -> dict[str, Any]:
    """Run LLM extraction over ticket comments and meeting note bodies.

    Args:
        dataset_name: Target dataset name.
        tickets_path: Path to tickets.csv.
        notes_dir: Directory containing meeting notes markdown files.
        concurrency_limit: Maximum concurrent extraction tasks (default 1 to prevent rate limits).
        include_all_tickets: If True, processes all 80 tickets without keyword filtering.
        pause_between_calls: Seconds to sleep between calls to avoid Groq OTPM rate limits.

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

    # Tickets: load all tickets from CSV (no keyword pre-filtering)
    if t_path.exists():
        with open(t_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                comment = (row.get("comments") or "").strip()
                if not comment:
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
                }
            )

    total_items = len(items)
    logger.info(
        "Starting LLM decision extraction for %d items into dataset '%s' (concurrency: %d)...",
        total_items,
        target_dataset,
        concurrency_limit,
    )

    semaphore = asyncio.Semaphore(concurrency_limit)
    item_timings: list[dict[str, Any]] = []

    async def _process_item(index: int, item: dict[str, Any]) -> None:
        async with semaphore:
            token_tracker.reset_delta()
            item_start = time.perf_counter()
            logger.info(
                "[%d/%d] Ingesting %s '%s'...", index, total_items, item["type"], item["id"]
            )

            for attempt in range(1, 4):
                try:
                    await ingest_text(
                        item["text"],
                        dataset_name=target_dataset,
                        run_cognify=True,
                        reconcile=False,  # Reconcile once at end of full batch
                    )
                    break
                except Exception as exc:
                    err_msg = str(exc)
                    if "rate_limit" in err_msg.lower() or "429" in err_msg:
                        from app.brain.memory import rotate_groq_key

                        rotate_groq_key()
                        wait_sec = 2 * attempt
                        logger.warning(
                            "Rate limited on item %s (attempt %d/3). Rotated key and pausing for %ds: %s",
                            item["id"],
                            attempt,
                            wait_sec,
                            exc,
                        )
                        await asyncio.sleep(wait_sec)
                    else:
                        logger.error(
                            "Failed extraction for item %s (attempt %d/3): %s",
                            item["id"],
                            attempt,
                            exc,
                        )
                        break

            elapsed = time.perf_counter() - item_start
            delta_tokens = token_tracker.last_total_tokens
            item_timings.append(
                {
                    "id": item["id"],
                    "type": item["type"],
                    "duration_sec": elapsed,
                    "tokens": delta_tokens,
                }
            )
            logger.info(
                "[%d/%d] Completed '%s' in %.2fs (tokens: %d, cumulative: %d)",
                index,
                total_items,
                item["id"],
                elapsed,
                delta_tokens,
                token_tracker.total_tokens,
            )
            if pause_between_calls > 0:
                await asyncio.sleep(pause_between_calls)

    for i, item in enumerate(items, 1):
        await _process_item(i, item)

    # 2. Link meeting based_on edges in Cypher
    await query_graph(
        "MATCH (d:Decision)-[:based_on_meeting]->(m:Meeting) MERGE (d)-[r:based_on]->(m)",
        dataset_name=target_dataset,
    )

    # 3. Post-extraction reconciliation
    reconcile_res = await reconcile_decisions(dataset_name=target_dataset)
    logger.info("Post-extraction reconciliation: %s", reconcile_res)

    total_time = time.perf_counter() - overall_start

    # Estimate token costs: Groq pricing (~$0.20 per 1M prompt/completion tokens for qwen/qwen3.8-27b)
    prompt_cost = (token_tracker.prompt_tokens / 1_000_000) * 0.20
    comp_cost = (token_tracker.completion_tokens / 1_000_000) * 0.20
    total_cost_usd = prompt_cost + comp_cost

    summary = {
        "items_processed": total_items,
        "total_time_seconds": round(total_time, 2),
        "total_tokens": token_tracker.total_tokens,
        "prompt_tokens": token_tracker.prompt_tokens,
        "completion_tokens": token_tracker.completion_tokens,
        "llm_calls": token_tracker.call_count,
        "estimated_cost_usd": round(total_cost_usd, 6),
        "reconciliation": reconcile_res,
        "item_timings": item_timings,
    }
    logger.info(
        "Full decision extraction finished in %.2fs | Total tokens: %d | Est cost: $%.5f",
        total_time,
        token_tracker.total_tokens,
        total_cost_usd,
    )
    return summary
