"""Split list-valued Person/System nodes ("A, B and C") into one node per entity.

Idempotent: with no composite nodes it changes nothing. Takes the dataset name (default
``company_brain``, which resolves to the configured production graph) and prints node/edge counts
before and after. Never deletes a graph; only rewires and removes the composite nodes themselves.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.brain.memory import query_graph
from app.brain.reconciliation import split_composite_nodes


async def _counts(dataset: str) -> tuple[int, int]:
    nodes = (await query_graph("MATCH (n) RETURN count(n)", dataset_name=dataset))[0][0]
    edges = (await query_graph("MATCH ()-[r]->() RETURN count(r)", dataset_name=dataset))[0][0]
    return nodes, edges


async def main(dataset: str) -> None:
    before = await _counts(dataset)
    result = await split_composite_nodes(dataset_name=dataset)
    after = await _counts(dataset)
    print(f"Before: {before[0]} nodes, {before[1]} edges")
    for item in result["split"]:
        print(f"  split {item['label']} {item['name']!r} -> {item['parts']}")
    for item in result["created"]:
        print(f"  created {item['label']} {item['name']!r}")
    print(f"After:  {after[0]} nodes, {after[1]} edges")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "company_brain"))
