"""Background jobs for long imports, and keep-alives for every long stream.

A GitHub import or a file upload can take longer than a browser, a proxy or a phone is willing to
hold one connection open. So the work runs as a job, in a task of its own, and the HTTP stream is
only a window onto the job's event log: if the stream drops, the job carries on, and a client can
re-attach (`GET /jobs/<id>/stream?from=N` replays from event N) or poll `GET /jobs/<id>`. A page
refresh in the middle of an import finds it through `GET /jobs/latest`.

Jobs live in memory (one backend process) for an hour after they finish. Each belongs to one
organization and can only be seen from it.
"""

import asyncio
import logging
import secrets
import time
from typing import Any, AsyncIterator, Callable, Optional

from app.brain import orgctx

logger = logging.getLogger("decision_trace.jobs")

HEARTBEAT_SECONDS = 10.0
KEEP_FINISHED_SECONDS = 3600.0
MAX_EVENTS = 5000
HEARTBEAT = ": keepalive\n\n"


class Job:
    def __init__(self, kind: str) -> None:
        self.id = f"job_{secrets.token_hex(6)}"
        self.kind = kind
        self.scope = orgctx.scope()
        self.status = "running"  # running | done | error | cancelled
        self.events: list[dict[str, Any]] = []
        self.created = time.time()
        self.finished: Optional[float] = None
        self.task: Optional[asyncio.Task] = None

    def add(self, event: dict[str, Any]) -> None:
        if len(self.events) < MAX_EVENTS:
            self.events.append(event)

    def summary(self) -> dict[str, Any]:
        """Status plus what a client needs to show real progress without replaying the stream."""
        latest: dict[str, Any] = {}
        result: Optional[dict[str, Any]] = None
        error: Optional[str] = None
        for e in self.events:
            if e["event"] == "progress":
                latest[e["data"]["phase"]] = e["data"]
            elif e["event"] == "diff":
                result = e["data"]
            elif e["event"] == "error":
                error = e["data"].get("message")
        return {
            "id": self.id, "kind": self.kind, "status": self.status, "events": len(self.events),
            "created_at": self.created, "finished_at": self.finished,
            "progress": list(latest.values()), "result": result, "error": error,
        }


_jobs: dict[str, Job] = {}


def _sweep() -> None:
    now = time.time()
    for jid in [j for j, job in _jobs.items() if job.finished and now - job.finished > KEEP_FINISHED_SECONDS]:
        _jobs.pop(jid, None)


def get(job_id: str) -> Optional[Job]:
    """A job, only from inside the organization it belongs to."""
    job = _jobs.get(job_id)
    return job if job and job.scope == orgctx.scope() else None


def latest(kind: Optional[str] = None) -> Optional[Job]:
    mine = [j for j in _jobs.values() if j.scope == orgctx.scope() and (kind is None or j.kind == kind)]
    return max(mine, key=lambda j: j.created, default=None)


def start(kind: str, factory: Callable[[], AsyncIterator[dict[str, Any]]], lock: Any) -> Job:
    """Run `factory()` (an async generator of {event, data}) as a job. The first event is
    `job` {id, kind}. The organization's ingest lock is held for the job's whole run; if it is
    taken, the job ends at once with an error event."""
    _sweep()
    job = Job(kind)
    job.add({"event": "job", "data": {"id": job.id, "kind": kind}})
    _jobs[job.id] = job

    async def run() -> None:
        try:
            if lock.locked():
                job.add({"event": "error", "data": {"message": "Another ingest or reset is running. Try again in a moment."}})
                job.status = "error"
                return
            async with lock:
                async for event in factory():
                    job.add(event)
                    if event["event"] == "error":
                        job.status = "error"
            if job.status == "running":
                job.status = "done"
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.add({"event": "error", "data": {"message": "The import was cancelled and what it had written was removed."}})
            raise
        except Exception as exc:  # noqa: BLE001 - reported to whoever is watching
            logger.exception("Job %s failed", job.id)
            job.status = "error"
            job.add({"event": "error", "data": {"message": f"{type(exc).__name__}: {exc}"[:300]}})
        finally:
            job.finished = time.time()

    # The task copies the request's context, so it keeps working on the same organization
    job.task = asyncio.create_task(run())
    return job


async def follow(job: Job, start_at: int = 0) -> AsyncIterator[dict[str, Any] | None]:
    """The job's events from `start_at`, as they happen. Yields None every HEARTBEAT_SECONDS of
    silence (the caller turns that into an SSE comment). Ends once the job has finished and every
    event has been delivered."""
    i = start_at
    quiet_since = time.monotonic()
    while True:
        if i < len(job.events):
            yield job.events[i]
            i += 1
            quiet_since = time.monotonic()
            continue
        if job.status != "running":
            return
        if time.monotonic() - quiet_since >= HEARTBEAT_SECONDS:
            yield None
            quiet_since = time.monotonic()
        await asyncio.sleep(0.25)


async def with_heartbeats(source: AsyncIterator[str], interval: float = HEARTBEAT_SECONDS) -> AsyncIterator[str]:
    """Pass a stream through, adding an SSE comment whenever it has been silent for `interval`
    seconds, so no proxy or browser sees an idle connection during a slow step."""
    it = source.__aiter__()
    pending: Optional[asyncio.Future] = asyncio.ensure_future(it.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield HEARTBEAT
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                pending = None
                return
            pending = asyncio.ensure_future(it.__anext__())
            yield item
    finally:
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        aclose = getattr(it, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except RuntimeError:  # the generator was still winding down; it ends on its own
                pass
