"""Connect to a Decision Trace MCP endpoint with the official client and call every read tool.

Usage: python scripts/mcp_smoke.py [URL]    (default: the production endpoint)
Asserts the benchmark answers (Keycloak -> DEC-11, Snowflake impact -> DEC-03/13/17, Alice Vance
for Kafka, the DEC-04 / DEC-07 conflict) and prints each tool's output. Exits 1 on any failure.
Read-only: add_source is not called.
"""

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_URL = "https://decision-trace-api-production.up.railway.app/mcp"
EXPECTED_TOOLS = {"ask", "get_decision", "list_decisions", "impact_of", "who_knows", "find_conflicts", "add_source"}


async def call(session: ClientSession, name: str, args: dict) -> dict:
    result = await session.call_tool(name, args)
    text = result.content[0].text if result.content else ""
    if result.isError:
        raise AssertionError(f"{name} returned an error: {text}")
    data = json.loads(text)
    print(f"\n=== {name}({json.dumps(args)}) ===\n{json.dumps(data, indent=2)[:1800]}")
    return data


async def main(url: str) -> None:
    # The header marks these calls as tests so they stay out of the Home change feed
    async with streamablehttp_client(url, headers={"X-DT-Smoke": "1"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            print("tools:", sorted(tools))
            assert tools == EXPECTED_TOOLS, tools

            ask = await call(session, "ask", {"question": "Why did we move sessions to Keycloak?"})
            assert ask["primary_decision"] == "DEC-11", ask["primary_decision"]

            impact = await call(session, "impact_of", {"system": "Snowflake"})
            decisions = next(s for s in impact["affected"] if s["title"].lower().startswith("decision"))
            assert {"DEC-03", "DEC-13", "DEC-17"} <= {i["code"] for i in decisions["items"]}

            experts = await call(session, "who_knows", {"topic": "Kafka"})
            assert "Alice Vance" in [e["name"] for e in experts["experts"][:3]]

            decision = await call(session, "get_decision", {"code": "DEC-11"})
            assert decision["code"] == "DEC-11" and decision["sources"]

            listing = await call(session, "list_decisions", {"status": "contradicted"})
            assert listing["count"] >= 1

            conflicts = await call(session, "find_conflicts", {})
            codes = {d["code"] for c in conflicts["conflicts"] for d in c["decisions"]}
            assert {"DEC-04", "DEC-07"} <= codes, codes
    print("\nMCP smoke test passed")


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL))
    except AssertionError as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
