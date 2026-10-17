"""Light load test against production: concurrent Ask streams, page loads and MCP calls.

Usage: python scripts/load_test.py [--asks 10] [--pages 20] [--mcp 10]
Each Ask stream gets its own X-Forwarded-For value so the per-IP limit (20/min) does not mask what
the server itself can do; the limit is checked separately (`--limit-check`). Prints p50/p95 and errors.
"""

import argparse
import asyncio
import json
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

API = "https://decision-trace-api-production.up.railway.app"
SITE = "https://decision-trace.pages.dev"
QUESTIONS = [
    "Why did we move sessions to Keycloak?", "Do any decisions conflict?", "What's affected if we drop Snowflake?",
    "Who knows the most about Kafka?", "Which systems have no owner?", "Why did we choose Kafka over RabbitMQ?",
    "What replaced Redis for session storage?", "Who decided to adopt Prometheus?",
    "What would we lose if Elasticsearch went away?", "Who is our go-to person for Postgres?",
]
PAGE_URLS = ["/", "/ask", "/decisions", "/systems", "/people", "/explore", "/sources", "/agents"]
API_PATHS = ["/api/decisions?limit=500", "/api/systems", "/api/people", "/api/attention", "/api/changes?limit=8", "/api/sources"]


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    return values[min(len(values) - 1, round(p / 100 * (len(values) - 1)))]


def summarize(name: str, results: list[dict]) -> None:
    ok = [r for r in results if r["ok"]]
    times = [r["total"] for r in ok]
    first = [r["first"] for r in ok if r.get("first") is not None]
    print(f"\n## {name}: {len(ok)}/{len(results)} ok")
    if times:
        print(f"   total  p50 {pct(times, 50):.2f}s  p95 {pct(times, 95):.2f}s  max {max(times):.2f}s")
    if first:
        print(f"   first byte/event  p50 {pct(first, 50):.2f}s  p95 {pct(first, 95):.2f}s")
    for r in results:
        if not r["ok"]:
            print("   ERROR:", r["error"])


async def ask_stream(client: httpx.AsyncClient, i: int) -> dict:
    start = time.perf_counter()
    first = None
    try:
        async with client.stream("POST", f"{API}/ask/stream", json={"question": QUESTIONS[i % len(QUESTIONS)]},
                                 headers={"X-Forwarded-For": f"10.99.{i}.{i + 1}"}, timeout=90) as r:
            if r.status_code != 200:
                return {"ok": False, "error": f"HTTP {r.status_code}", "total": 0}
            done = False
            async for line in r.aiter_lines():
                if first is None and line.startswith("event:"):
                    first = time.perf_counter() - start
                if line.startswith("event: done"):
                    done = True
                if line.startswith("event: error"):
                    return {"ok": False, "error": "stream error event", "total": 0}
            return {"ok": done, "error": "no done event", "total": time.perf_counter() - start, "first": first}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "total": 0}


async def page_load(client: httpx.AsyncClient, i: int) -> dict:
    start = time.perf_counter()
    try:
        page = await client.get(SITE + PAGE_URLS[i % len(PAGE_URLS)], timeout=30)
        api = await client.get(SITE + API_PATHS[i % len(API_PATHS)], timeout=30)
        ok = page.status_code == 200 and api.status_code == 200
        return {"ok": ok, "error": f"page {page.status_code} api {api.status_code}", "total": time.perf_counter() - start,
                "first": page.elapsed.total_seconds()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "total": 0}


async def mcp_call(i: int) -> dict:
    start = time.perf_counter()
    name, args = [("find_conflicts", {}), ("get_decision", {"code": "DEC-11"}), ("list_decisions", {}),
                  ("who_knows", {"topic": "Kafka"})][i % 4]
    try:
        async with streamablehttp_client(f"{API}/mcp", headers={"X-DT-Smoke": "1", "X-Forwarded-For": f"10.98.{i}.1"}) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await asyncio.wait_for(s.call_tool(name, args), timeout=60)
                json.loads(res.content[0].text) if not res.isError else None
                return {"ok": not res.isError, "error": f"{name}: {res.content[0].text[:120]}", "total": time.perf_counter() - start}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{name}: {type(exc).__name__}: {exc}", "total": 0}


async def limit_check() -> None:
    codes = []
    async with httpx.AsyncClient() as c:
        for _ in range(23):
            r = await c.post(f"{API}/ask", json={"question": "Which systems have no owner?"},
                             headers={"X-Forwarded-For": "10.77.0.1"}, timeout=60)
            codes.append(r.status_code)
    print(f"\n## rate limit (one IP, 23 asks): {codes.count(200)} x 200, {codes.count(429)} x 429  (limit is 20/min)")


async def main(asks: int, pages: int, mcp: int, check: bool) -> None:
    async with httpx.AsyncClient() as client:
        t = time.perf_counter()
        results = await asyncio.gather(
            *[ask_stream(client, i) for i in range(asks)],
            *[page_load(client, i) for i in range(pages)],
            *[mcp_call(i) for i in range(mcp)],
        )
        wall = time.perf_counter() - t
    summarize(f"{asks} concurrent Ask streams", results[:asks])
    summarize(f"{pages} concurrent page loads (HTML + API through the proxy)", results[asks:asks + pages])
    summarize(f"{mcp} concurrent MCP sessions (init + one tool call)", results[asks + pages:])
    print(f"\nwall time for everything at once: {wall:.1f}s")
    if check:
        await limit_check()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--asks", type=int, default=10)
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--mcp", type=int, default=10)
    ap.add_argument("--limit-check", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.asks, a.pages, a.mcp, a.limit_check))
