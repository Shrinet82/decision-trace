"""Live ingest (Server-Sent Events), demo reset, and the change feed."""

from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app import jobs
from app.api.orgs import require_owner
from app.api.rate_limiter import DEMO_LIMIT_MESSAGE, budget_exceeded, check_ingest_rate_limit
from app.brain import orgctx
from app.brain.memory import query_graph
from app.config import get_settings
from app.ingest.batch import BatchRequest, run_batch
from app.ingest.github import GithubRequest, run_github_import
from app.ingest.live import (
    INGEST_LOCK,
    IngestRequest,
    demo_status,
    list_changes,
    reset_demo,
    run_ingest,
    sse,
)
from app.orgs import registry

router = APIRouter(tags=["Live ingest"])
_settings = get_settings()

_BUSY = "Another ingest or reset is running. Try again in a moment."


def _job_response(job: jobs.Job) -> StreamingResponse:
    """Stream a job's events from the start. The job runs on its own: if this connection drops,
    it carries on and the client re-attaches with GET /jobs/<id>/stream?from=<n>."""

    async def stream() -> AsyncIterator[str]:
        async for event in jobs.follow(job):
            yield jobs.HEARTBEAT if event is None else sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


async def _count_sources() -> None:
    """Keep a user organization's source count current (shown in the organization list)."""
    slug = orgctx.current_slug()
    if not slug or not orgctx.is_user_org():
        return
    try:
        rows = await query_graph("MATCH (s) WHERE s:Ticket OR s:Meeting OR s:Document RETURN count(s)")
        await registry.set_source_count(slug, int(rows[0][0]) if rows else 0)
    except Exception:  # noqa: BLE001 - bookkeeping only
        pass


@router.post("/ingest", dependencies=[Depends(require_owner)])
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
        jobs.with_heartbeats(stream()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest/batch", dependencies=[Depends(require_owner)])
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

    async def work() -> AsyncIterator[dict[str, Any]]:
        async for event in run_batch(body.files, dataset):
            yield event
            if event["event"] == "diff":
                await _count_sources()

    return _job_response(jobs.start("upload", work, INGEST_LOCK))



@router.post("/ingest/github", dependencies=[Depends(require_owner)])
async def ingest_github(body: GithubRequest, request: Request) -> StreamingResponse:
    """Import ADRs (and optionally decision-like PRs and issues) from a public GitHub repository,
    streaming progress, ending with a `diff`. Only available in organizations you create: the sample
    organization is read-only apart from its tagged demo data."""
    if not orgctx.is_user_org():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="GitHub import is available in organizations you create, not in the sample organization.",
        )
    check_ingest_rate_limit(request)
    if budget_exceeded():
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=DEMO_LIMIT_MESSAGE)
    if INGEST_LOCK.locked():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_BUSY)
    dataset = _settings.DATASET_NAME

    async def work() -> AsyncIterator[dict[str, Any]]:
        async for event in run_github_import(body, dataset):
            yield event
            if event["event"] == "diff":
                await _count_sources()

    return _job_response(jobs.start("github", work, INGEST_LOCK))



@router.post("/ingest/reset")
async def reset(request: Request) -> dict[str, Any]:
    """Remove all demo-ingested nodes/edges and restore changed values (e.g. a person leaving)."""
    if orgctx.is_user_org():
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
