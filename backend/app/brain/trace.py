"""Run Cypher queries while recording what was run and how long it took.

Detail endpoints return this trace so the UI can show the exact Cypher behind a page. Queries
run in worker threads, so independent ones can be issued together with ``gather``.
"""

import asyncio
import time
from typing import Any, Optional

from app.brain.memory import query_graph_threaded


class CypherTrace:
    """Executes queries against one dataset and keeps (name, query, params, ms) for each."""

    def __init__(self, dataset_name: Optional[str] = None) -> None:
        self.dataset_name = dataset_name
        self.entries: list[dict[str, Any]] = []
        self._started = time.perf_counter()

    async def run(self, name: str, query: str, params: Optional[dict[str, Any]] = None) -> list[Any]:
        start = time.perf_counter()
        rows = await query_graph_threaded(query, dataset_name=self.dataset_name, params=params or {})
        self.entries.append(
            {
                "name": name,
                "query": query,
                "params": params or {},
                "ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )
        return rows

    async def gather(self, *calls: tuple[str, str, dict[str, Any]]) -> list[list[Any]]:
        """Run several (name, query, params) concurrently; results in the same order."""
        return list(await asyncio.gather(*(self.run(n, q, p) for n, q, p in calls)))

    def as_dict(self) -> dict[str, Any]:
        # Wall-clock time, so concurrent queries are not double counted
        return {
            "queries": self.entries,
            "total_ms": round((time.perf_counter() - self._started) * 1000, 1),
        }
