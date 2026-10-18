"""Live ingest (Server-Sent Events), demo reset, and the change feed."""

from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.brain.memory import query_graph
from app.api.rate_limiter import DEMO_LIMIT_MESSAGE, budget_exceeded, check_ingest_rate_limit
from app.brain import orgctx
from app.config import get_settings
from app.orgs import registry
from app.ingest.batch import BatchRequest, run_batch
from app.ingest.live import (
    INGEST_LOCK,
    IngestRequest,
    demo_status,
    list_changes,
    reset_demo,
    run_ingest,
    sse,
)

router = APIRouter(tags=["Live ingest"])
_settings = get_settings()

_BUSY = "Another ingest or reset is running. Try again in a moment."


async def _count_sources() -> None:
    """Keep a user organization's source count current (shown in the organization list)."""
    slug = orgctx.current_slug()
    if not slug:
        return
    try:
        rows = await query_graph("MATCH (s) WHERE s:Ticket OR s:Meeting OR s:Document RETURN count(s)")
        await registry.set_source_count(slug, int(rows[0][0]) if rows else 0)
    except Exception:  # noqa: BLE001 - bookkeeping only
        pass


@router.post("/ingest")
async def ingest(body: IngestRequest, request: Request) -> StreamingResponse:
    """Ingest one source and stream each pipeline step, ending with a `diff` (or `error`) event.

    Everything written is tagged with a demo_ingest_id so POST /ingest/reset can remove it.
    """
    check_ingest_rate_limit(request)
    if budget_exceeded():
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=DEMO_LIMIT_MESSAGE)
    if INGEST_LOCK.locked():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_BUSY)
    dataset = _settings.DATASET_NAME

    async def stream() -> AsyncIterator[str]:
        # Check and acquire with nothing awaited in between, so two requests that both passed the
        # check above cannot both run: the second is told the pipeline is busy instead of queueing.
        if INGEST_LOCK.locked():
            yield sse({"event": "error", "data": {"message": _BUSY}})
            return
        async with INGEST_LOCK:
            async for event in run_ingest(body, dataset):
                yield sse(event)
                if event["event"] == "diff":
                    await _count_sources()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest/batch")
async def ingest_batch(body: BatchRequest, request: Request) -> StreamingResponse:
    """Ingest up to 10 uploaded files (.md, .txt, .pdf) and stream progress per file, ending with
    one combined `diff`. In the sample organization everything is tagged demo data and resets
    automatically; in your own organization it is kept."""
    check_ingest_rate_limit(request)
    if budget_exceeded():
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=DEMO_LIMIT_MESSAGE)
    if INGEST_LOCK.locked():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_BUSY)
    dataset = _settings.DATASET_NAME

    async def stream() -> AsyncIterator[str]:
        if INGEST_LOCK.locked():
            yield sse({"event": "error", "data": {"message": _BUSY}})
            return
        async with INGEST_LOCK:
            async for event in run_batch(body.files, dataset):
                yield sse(event)
                if event["event"] == "diff":
                    await _count_sources()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest/reset")
async def reset(request: Request) -> dict[str, Any]:
    """Remove all demo-ingested nodes/edges and restore changed values (e.g. a person leaving)."""
    if orgctx.current_graph():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organizations you create keep their data. Delete the organization to start over.",
        )
    check_ingest_rate_limit(request)
    if INGEST_LOCK.locked():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_BUSY)
    async with INGEST_LOCK:
        return await reset_demo(_settings.DATASET_NAME)


@router.get("/changes")
async def changes(
    limit: int = Query(default=20, ge=1, le=100),
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
    include_tests: bool = Query(False, description="Also list CI smoke-test calls"),
) -> list[dict[str, Any]]:
    """Recent ingests, resets and agent calls, newest first, with their diffs."""
    return await list_changes(dataset_name or _settings.DATASET_NAME, limit, include_tests)


@router.get("/ingest/status")
async def ingest_status() -> dict[str, Any]:
    """Whether demo data is present and when the automatic reset (10 minutes after the latest
    ingest) will remove it."""
    return await demo_status(_settings.DATASET_NAME)
