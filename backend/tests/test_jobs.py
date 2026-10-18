"""Background jobs: they outlive their stream, can be re-attached, stay inside their organization,
and every long stream carries keep-alives."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.api import orgs as orgs_api
from app.brain import orgctx
from app.brain.orgctx import ScopedLock
from app.orgs import registry
from app.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    jobs._jobs.clear()
    yield
    jobs._jobs.clear()


async def _events(**kw):
    for i in range(3):
        await asyncio.sleep(kw.get("delay", 0))
        yield {"event": "progress", "data": {"phase": "extracting", "status": "running", "label": "x", "detail": f"{i + 1}/3"}}
    yield {"event": "diff", "data": {"summary": "ok"}}


async def test_a_job_runs_on_after_nobody_is_watching_and_can_be_replayed():
    lock = ScopedLock()
    job = jobs.start("github", lambda: _events(delay=0.01), lock)
    assert job.status == "running" and job.events[0]["data"]["id"] == job.id
    await job.task
    assert job.status == "done" and not lock.locked()
    names = [e["event"] for e in job.events]
    assert names == ["job", "progress", "progress", "progress", "diff"]
    # Re-attaching from event 3 replays only what was missed
    replay = [e async for e in jobs.follow(job, 3) if e is not None]
    assert [e["event"] for e in replay] == ["progress", "diff"]
    summary = job.summary()
    assert summary["status"] == "done" and summary["result"] == {"summary": "ok"}
    assert summary["progress"][0]["detail"] == "3/3"


async def test_a_failing_job_ends_with_an_error_event():
    async def boom():
        yield {"event": "progress", "data": {"phase": "fetching", "status": "running", "label": "x"}}
        raise ValueError("kaput")

    job = jobs.start("upload", boom, ScopedLock())
    await job.task
    assert job.status == "error" and "kaput" in job.summary()["error"]


async def test_a_busy_lock_ends_the_job_at_once():
    lock = ScopedLock()
    await lock.acquire()
    job = jobs.start("github", lambda: _events(), lock)
    await job.task
    assert job.status == "error" and "Another ingest" in job.summary()["error"]
    lock.release()


async def test_cancelling_stops_the_job_and_releases_the_lock():
    lock = ScopedLock()

    async def slow():
        yield {"event": "progress", "data": {"phase": "extracting", "status": "running", "label": "x"}}
        await asyncio.sleep(30)
        yield {"event": "diff", "data": {}}

    job = jobs.start("github", slow, lock)
    await asyncio.sleep(0.05)
    job.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job.task
    assert job.status == "cancelled" and not lock.locked()
    assert "cancelled" in job.summary()["error"]


async def test_jobs_are_only_visible_inside_their_own_organization():
    with orgctx.org_scope("a", "graph_a"):
        job = jobs.start("github", lambda: _events(), ScopedLock())
        assert jobs.get(job.id) is job and jobs.latest("github") is job
    with orgctx.org_scope("b", "graph_b"):
        assert jobs.get(job.id) is None and jobs.latest() is None
    assert jobs.get(job.id) is None  # nor from Acme
    await job.task


async def test_silence_becomes_keepalive_comments_and_nothing_is_lost():
    async def slow_source():
        yield "a"
        await asyncio.sleep(0.35)
        yield "b"

    out = [x async for x in jobs.with_heartbeats(slow_source(), interval=0.1)]
    assert [x for x in out if x != jobs.HEARTBEAT] == ["a", "b"]
    assert out.count(jobs.HEARTBEAT) >= 2


async def test_a_follower_gets_a_heartbeat_while_the_job_is_quiet(monkeypatch):
    monkeypatch.setattr(jobs, "HEARTBEAT_SECONDS", 0.1)

    async def quiet():
        await asyncio.sleep(0.9)
        yield {"event": "diff", "data": {}}

    job = jobs.start("github", quiet, ScopedLock())
    seen = [e async for e in jobs.follow(job)]
    assert seen.count(None) >= 2 and seen[-1]["event"] == "diff"


def test_the_endpoints_report_progress_and_replay(monkeypatch):
    async def fake_batch(files, dataset):
        yield {"event": "file", "data": {"index": 0, "name": "a.md", "status": "done"}}
        yield {"event": "diff", "data": {"summary": "ok"}}

    monkeypatch.setattr("app.api.ingest.run_batch", fake_batch)
    from app.api import rate_limiter

    rate_limiter._ip_ingest_requests.clear()
    res = client.post("/ingest/batch", json={"files": [{"name": "a.md", "text": "We decided X."}]})
    assert res.status_code == 200
    blocks = [b for b in res.text.strip().split("\n\n") if b]
    first = json.loads(blocks[0].split("\n")[1].removeprefix("data: "))
    job_id = first["id"]
    assert [b.split("\n")[0] for b in blocks] == ["event: job", "event: file", "event: diff"]

    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == "done" and status["result"] == {"summary": "ok"}
    assert client.get("/jobs/latest", params={"kind": "upload"}).json()["id"] == job_id
    replay = client.get(f"/jobs/{job_id}/stream", params={"from": 2})
    assert replay.text.count("event:") == 1 and "event: diff" in replay.text
    assert client.get("/jobs/job_nope").status_code == 404
    rate_limiter._ip_ingest_requests.clear()


def test_cancelling_a_job_in_a_user_organization_needs_the_owner_key(monkeypatch):
    registry._orgs.clear()
    registry._loaded = True
    import time

    registry._loaded_at = time.monotonic()
    orgs_api._creates.clear()

    async def fake_run(graph, query, params=None):
        return []

    monkeypatch.setattr(registry, "run_on_graph", fake_run)
    monkeypatch.setattr(orgs_api, "run_on_graph", fake_run)
    org = client.post("/orgs", json={"name": "Jobs"}).json()
    assert client.delete(f"/orgs/{org['id']}/jobs/job_x").status_code == 403
    assert client.delete(f"/orgs/{org['id']}/jobs/job_x", headers={"X-Org-Key": org["owner_key"]}).status_code == 404
    registry._orgs.clear()
