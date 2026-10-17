"""Daily LLM token budget: cached answers or a clear demo-limit message once it is used up, and
ingest refused (429), while the single-run ingest lock (409) and rate limits keep working."""

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import rate_limiter
from app.api.rate_limiter import DEMO_LIMIT_MESSAGE
from app.askflow import pipeline, queries
from app.ingest.live import INGEST_LOCK
from app.server import app
from tests.test_askflow import ROWS, _events, _patches

client = TestClient(app)
BY_QUERY = {queries.ROSTER: ROWS["ROSTER"], queries.IMPACT_DECISIONS: ROWS["IMPACT_DECISIONS"],
            queries.IMPACT_PEOPLE: ROWS["IMPACT_PEOPLE"], queries.IMPACT_TICKETS: ROWS["IMPACT_TICKETS"]}
QUESTION = "What's affected if we drop Snowflake?"


def _budget(tokens: int):
    return patch("app.config.get_settings", return_value=SimpleNamespace(LLM_DAILY_TOKEN_BUDGET=tokens))


def setup_function():
    pipeline._ANSWER_CACHE.clear()
    rate_limiter._token_usage.clear()


async def test_over_budget_serves_the_saved_answer_without_calling_the_model():
    answer = "Dropping Snowflake affects DEC-17 (Cloud Cost Optimization Taskforce)."
    first = await _events(QUESTION, _patches(BY_QUERY, answer))
    assert first[-1]["event"] == "done"

    patches = _patches(BY_QUERY, "must not be used")
    patches.append(patch("app.askflow.pipeline.budget_exceeded", return_value=True))
    events = await _events(QUESTION, patches)
    assert events[-1]["event"] == "done" and events[-1]["data"]["answer"] == answer
    steps = [e["data"] for e in events if e["event"] == "step" and e["data"]["step"] == "composing"]
    assert "saved answer" in steps[-1]["detail"]


async def test_over_budget_without_a_saved_answer_says_the_demo_limit_is_reached():
    patches = _patches(BY_QUERY, "must not be used")
    patches.append(patch("app.askflow.pipeline.budget_exceeded", return_value=True))
    events = await _events(QUESTION, patches)
    assert events[-1] == {"event": "error", "data": {"message": DEMO_LIMIT_MESSAGE, "code": "demo_limit"}}
    assert not any(e["event"] == "token" for e in events)


def test_token_usage_adds_up_and_trips_the_budget():
    with _budget(1000):
        rate_limiter.record_tokens(600, "test")
        assert not rate_limiter.budget_exceeded()
        rate_limiter.record_tokens(500, "test")
        assert rate_limiter.tokens_used_today() == 1100 and rate_limiter.budget_exceeded()


def test_a_budget_of_zero_means_unlimited():
    with _budget(0):
        rate_limiter.record_tokens(10**9, "test")
        assert not rate_limiter.budget_exceeded()


BODY = {"type": "meeting", "title": "t", "date": "2026-10-16", "text": "Alice decided to use Kafka."}


def test_ingest_is_refused_with_429_when_over_budget():
    rate_limiter._ip_ingest_requests.clear()
    with patch("app.api.ingest.budget_exceeded", return_value=True):
        r = client.post("/ingest", json=BODY)
    assert r.status_code == 429 and r.json()["detail"] == DEMO_LIMIT_MESSAGE


async def test_ingest_while_another_runs_is_409():
    rate_limiter._ip_ingest_requests.clear()
    await INGEST_LOCK.acquire()
    try:
        r = client.post("/ingest", json=BODY)
    finally:
        INGEST_LOCK.release()
    assert r.status_code == 409 and "Another ingest" in r.json()["detail"]


def test_ingest_rate_limit_is_429_after_three_per_minute():
    rate_limiter._ip_ingest_requests.clear()
    with patch("app.api.ingest.INGEST_LOCK") as lock:
        lock.locked.return_value = True
        codes = [client.post("/ingest", json=BODY).status_code for _ in range(4)]
    assert codes == [409, 409, 409, 429]
