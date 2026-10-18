"""Background jobs (GitHub import, file upload): status, re-attachable event stream, cancel.

See app/jobs.py. All routes work inside an organization (`/orgs/<id>/jobs/...`) and only see that
organization's jobs. Cancelling needs the organization's owner key, like starting one."""

from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app import jobs
from app.api.orgs import require_owner
from app.ingest.live import sse

router = APIRouter(tags=["Jobs"])


def _job(job_id: str) -> jobs.Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That job does not exist (it may have expired).")
    return job


@router.get("/jobs/latest")
async def latest_job(kind: Optional[str] = Query(default=None)) -> dict[str, Any]:
    """The newest job in this organization (running or finished), so a reloaded page can pick it up."""
    job = jobs.latest(kind)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No jobs yet.")
    return job.summary()


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    return _job(job_id).summary()


@router.get("/jobs/{job_id}/stream")
async def job_stream(job_id: str, from_: int = Query(default=0, alias="from", ge=0)) -> StreamingResponse:
    """The job's events from event number `from`, then live, with a keep-alive comment every 10 s.
    The stream ends when the job has finished and every event was delivered."""
    job = _job(job_id)

    async def stream() -> AsyncIterator[str]:
        async for event in jobs.follow(job, from_):
            yield jobs.HEARTBEAT if event is None else sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.delete("/jobs/{job_id}", dependencies=[Depends(require_owner)])
async def cancel_job(job_id: str) -> dict[str, Any]:
    job = _job(job_id)
    if job.status == "running" and job.task is not None:
        job.task.cancel()
    return {"id": job.id, "status": job.status}
