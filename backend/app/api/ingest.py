"""Live ingest (Server-Sent Events), demo reset, and the change feed."""

from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.rate_limiter import check_ingest_rate_limit
from app.config import get_settings
from app.ingest.live import INGEST_LOCK, IngestRequest, list_changes, reset_demo, run_ingest, sse

router = APIRouter(tags=["Live ingest"])
_settings = get_settings()

_BUSY = "Another ingest or reset is running. Try again in a moment."


@router.post("/ingest")
async def ingest(body: IngestRequest, request: Request) -> StreamingResponse:
    """Ingest one source and stream each pipeline step, ending with a `diff` (or `error`) event.

    Everything written is tagged with a demo_ingest_id so POST /ingest/reset can remove it.
    """
    check_ingest_rate_limit(request)
    if INGEST_LOCK.locked():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_BUSY)
    dataset = _settings.DATASET_NAME

    async def stream() -> AsyncIterator[str]:
        async with INGEST_LOCK:
            async for event in run_ingest(body, dataset):
                yield sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest/reset")
async def reset(request: Request) -> dict[str, Any]:
    """Remove all demo-ingested nodes/edges and restore changed values (e.g. a person leaving)."""
    check_ingest_rate_limit(request)
    if INGEST_LOCK.locked():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_BUSY)
    async with INGEST_LOCK:
        return await reset_demo(_settings.DATASET_NAME)


@router.get("/changes")
async def changes(
    limit: int = Query(default=20, ge=1, le=100),
    dataset_name: Optional[str] = Query(None, description="Target dataset name"),
) -> list[dict[str, Any]]:
    """Recent ingests and resets, newest first, with their diffs."""
    return await list_changes(dataset_name or _settings.DATASET_NAME, limit)
