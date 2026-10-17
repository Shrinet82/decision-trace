"""GET /attention: the home page's needs-attention queue, from stubbed graph reads."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.schemas import PersonRef, SystemSummary
from app.brain.health import DecisionHealthInfo
from app.server import app

client = TestClient(app)
CODES = {"a": "DEC-04", "b": "DEC-07", "c": "DEC-09", "d": "DEC-01"}


def _health(i, status, reason):
    return DecisionHealthInfo(id=i, title=i, status=status, reason=reason)


def test_queue_lists_conflicts_orphans_stale_and_superseded_with_reasons():
    health = {
        "a": _health("a", "contradicted", "Contradicted by 'Adopt RabbitMQ'"),
        "c": _health("c", "possibly_stale", "Its decider Marcus left on 2025-11-30"),
    }
    orphan = SystemSummary(
        name="Elasticsearch", orphaned=True, decision_count=1, ticket_count=3,
        owner=PersonRef(name="Marcus Aurelius", departed=True, leave_date="2025-11-30"),
    )
    reads = [[["a", "b"], ["b", "a"]], [["d", "n", "2026-05-12", "Redis", ["TICK-9", "TICK-8"]]]]
    with patch("app.api.attention.get_health_map", AsyncMock(return_value=health)), \
         patch("app.api.attention.get_decision_codes_cached", AsyncMock(return_value={**CODES, "n": "DEC-11"})), \
         patch("app.api.attention.list_systems", AsyncMock(return_value=[orphan])), \
         patch("app.api.attention.query_graph", AsyncMock(side_effect=reads)):
        items = client.get("/attention").json()["items"]
    assert [i["kind"] for i in items] == ["conflict", "orphaned", "stale", "superseded"]
    assert items[0]["title"] == "DEC-04 and DEC-07 conflict" and items[0]["decision_code"] == "DEC-04"
    assert items[1]["system"] == "Elasticsearch" and "2025-11-30" in items[1]["reason"]
    assert items[2]["decision_code"] == "DEC-09"
    assert items[3]["decision_code"] == "DEC-01" and "DEC-11" in items[3]["reason"] and "2 tickets" in items[3]["reason"]


def test_empty_queue_when_everything_is_healthy():
    with patch("app.api.attention.get_health_map", AsyncMock(return_value={})), \
         patch("app.api.attention.get_decision_codes_cached", AsyncMock(return_value={})), \
         patch("app.api.attention.list_systems", AsyncMock(return_value=[])), \
         patch("app.api.attention.query_graph", AsyncMock(return_value=[])):
        assert client.get("/attention").json() == {"items": []}


async def test_endpoint_cache_computes_once_for_concurrent_callers_and_resets_on_invalidate():
    import asyncio

    from app.brain import cache

    calls = []

    @cache.cached_endpoint("test.endpoint", 60)
    async def read(*, name: str) -> str:
        calls.append(name)
        await asyncio.sleep(0.05)
        return name.upper()

    assert await asyncio.gather(*[read(name="a") for _ in range(8)]) == ["A"] * 8
    assert calls == ["a"]
    assert await read(name="b") == "B" and calls == ["a", "b"]
    cache.invalidate()
    await read(name="a")
    assert calls == ["a", "b", "a"]
