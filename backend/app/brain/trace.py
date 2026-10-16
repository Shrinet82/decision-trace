"""Run Cypher queries while recording what was run and how long it took.

The detail endpoints return this trace so the UI can show the exact Cypher behind a page.
"""

import time
from typing import Any, Optional

from app.brain.memory import query_graph


class CypherTrace:
    """Executes queries against one dataset and keeps (name, query, params, ms) for each."""

    def __init__(self, dataset_name: Optional[str] = None) -> None:
        self.dataset_name = dataset_name
        self.entries: list[dict[str, Any]] = []

    async def run(self, name: str, query: str, params: Optional[dict[str, Any]] = None) -> list[Any]:
        start = time.perf_counter()
        rows = await query_graph(query, dataset_name=self.dataset_name, params=params or {})
        self.entries.append(
            {
                "name": name,
                "query": query,
                "params": params or {},
                "ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )
        return rows

    def as_dict(self) -> dict[str, Any]:
        return {
            "queries": self.entries,
            "total_ms": round(sum(e["ms"] for e in self.entries), 1),
        }
