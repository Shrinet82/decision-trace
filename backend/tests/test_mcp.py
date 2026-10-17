"""MCP server: tool list, schemas, read tools on stubbed services, rate limit and change logging.

The official MCP client talks to the real ASGI route (Streamable HTTP), so the transport, the
tool schemas and the `ctx` injection are exercised exactly as an agent would use them.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.api.rate_limiter import _ip_day_requests, _ip_min_requests
from app.mcp_server import mcp

EXPECTED = {"ask", "get_decision", "list_decisions", "impact_of", "who_knows", "find_conflicts", "add_source"}
ASK_RESULT = {
    "answer": "Sessions moved to Keycloak (DEC-11), per TICK-102.",
    "intent": "why", "primary_decision_id": "d11",
    "citations": [{"type": "ticket", "id": "TICK-102", "title": "Keycloak"}],
    "graph_path": {
        "nodes": [{"id": "d11", "label": "Decision", "properties": {"title": "Use Keycloak"}},
                  {"id": "TICK-102", "label": "Ticket", "properties": {"ticket_id": "TICK-102"}}],
        "edges": [{"source": "d11", "target": "TICK-102", "type": "based_on", "properties": {}}],
        "omitted_count": 0},
    "sections": [{"key": "decisions", "title": "Decisions", "total": 1,
                  "items": [{"kind": "decision", "name": "Use Keycloak", "code": "DEC-11", "health": "active"}]}],
    "experts": [{"name": "Alice Vance", "role": "Eng", "departed": False, "score": 9,
                 "evidence": {"decided": 1, "owns": 1, "meetings": 1, "tickets": 1},
                 "decisions": ["DEC-04"], "meetings": [], "tickets": ["TICK-1"]}],
}


_test_app = None


@asynccontextmanager
async def _client():
    def factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=_test_app), headers=headers, timeout=timeout,
                                 auth=auth, follow_redirects=True)

    async with streamablehttp_client("http://test/mcp", httpx_client_factory=factory) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            yield session


@pytest.fixture(scope="module", autouse=True)
async def session_manager():
    # The session manager can only run once per instance; the app lifespan is not started here
    # A fresh session manager and ASGI app for these tests: a manager can only run once per
    # instance, and other tests may already have started the application's own lifespan.
    global _test_app
    mcp._session_manager = None
    _test_app = mcp.streamable_http_app()
    # Entered and exited in one task (anyio cancel scopes require it)
    ready, stop = asyncio.Event(), asyncio.Event()

    async def run() -> None:
        async with mcp.session_manager.run():
            ready.set()
            await stop.wait()

    task = asyncio.create_task(run())
    await ready.wait()
    yield
    stop.set()
    await task


@pytest.fixture(autouse=True)
def stubs():
    _ip_min_requests.clear()
    _ip_day_requests.clear()
    with patch("app.mcp_server.collect_ask", AsyncMock(return_value=ASK_RESULT)), \
         patch("app.mcp_server.get_decision_codes_cached", AsyncMock(return_value={"d11": "DEC-11"})), \
         patch("app.mcp_server.record_change", AsyncMock()) as record:
        yield record


async def _call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


async def test_lists_all_tools_with_descriptions_and_no_ctx_argument():
    async with _client() as s:
        tools = (await s.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED
    for t in tools:
        assert len(t.description or "") > 80, t.name
        assert "ctx" not in t.inputSchema.get("properties", {})
    read_only = {t.name for t in tools if t.annotations and t.annotations.readOnlyHint}
    assert read_only == EXPECTED - {"add_source"}


async def test_ask_returns_primary_decision_code_citations_and_named_path(stubs):
    async with _client() as s:
        out = await _call(s, "ask", {"question": "Why did we move sessions to Keycloak?"})
    assert out["primary_decision"] == "DEC-11"
    assert out["citations"][0]["id"] == "TICK-102"
    assert "DEC-11 -based_on-> TICK-102" in out["graph_path"]["edges"]
    entry = stubs.await_args.args[1]
    assert entry["kind"] == "agent" and entry["title"] == "ask" and "Keycloak" in entry["summary"]


async def test_impact_of_returns_structured_sections():
    async with _client() as s:
        out = await _call(s, "impact_of", {"system": "Snowflake"})
    assert out["affected"][0]["items"][0]["code"] == "DEC-11"


async def test_who_knows_ranks_people_with_evidence_counts():
    async with _client() as s:
        out = await _call(s, "who_knows", {"topic": "Kafka"})
    assert out["experts"][0]["name"] == "Alice Vance" and out["experts"][0]["evidence"]["decided"] == 1


async def test_unknown_decision_is_a_tool_error():
    with patch("app.mcp_server.build_decision_detail", AsyncMock(return_value=None)):
        async with _client() as s:
            result = await s.call_tool("get_decision", {"code": "DEC-99"})
    assert result.isError and "not found" in result.content[0].text


async def test_add_source_is_refused_when_read_only():
    with patch("app.mcp_server._settings.MCP_READ_ONLY", True):
        async with _client() as s:
            result = await s.call_tool("add_source", {
                "type": "ticket", "title": "T", "date": "2026-01-01", "text": "x"})
    assert result.isError and "read-only" in result.content[0].text


async def test_per_ip_rate_limit_applies_to_tool_calls():
    async with _client() as s:
        for _ in range(20):
            await _call(s, "ask", {"question": "q"})
        result = await s.call_tool("ask", {"question": "q"})
    assert result.isError and "Rate limit" in result.content[0].text
