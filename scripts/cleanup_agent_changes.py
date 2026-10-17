"""List (and with --delete, remove) MCP agent entries from the production /changes feed.

The change log lives in its own graph (<graph>__changes), so this never touches decision data.
Usage: PYTHONPATH=backend python scripts/cleanup_agent_changes.py [--delete]
"""

import asyncio
import sys

from app.brain.memory import query_graph
from app.config import get_settings
from app.ingest.live import _changes_graph


async def main(delete: bool) -> None:
    graph = await _changes_graph(get_settings().DATASET_NAME)
    rows = await query_graph(
        "MATCH (c:Change {kind: 'agent'}) RETURN c.id, c.title, c.summary, c.created_at, c.type ORDER BY c.created_at",
        dataset_name=graph,
    )
    for r in rows:
        print(f"{r[3]}  {r[0]}  {r[1]}  {r[2]}  type={r[4]}")
    print(f"{len(rows)} agent entries")
    if delete and rows:
        await query_graph("MATCH (c:Change {kind: 'agent'}) DELETE c", dataset_name=graph)
        left = await query_graph("MATCH (c:Change {kind: 'agent'}) RETURN count(c)", dataset_name=graph)
        print("deleted; remaining agent entries:", left[0][0])


if __name__ == "__main__":
    asyncio.run(main("--delete" in sys.argv))
