"""Which organization (which FalkorDB graph) the current request or task is working on.

The sample organization is the configured production graph and is the default: with nothing set,
every function behaves as it did before organizations existed. A request to `/orgs/<slug>/...`
sets the graph for the rest of that request (the middleware in app.orgs.middleware); background
jobs and MCP tools set it with `org_scope`. asyncio tasks and `asyncio.to_thread` copy the context,
so queries started from a request see the same graph.
"""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

_graph: ContextVar[Optional[str]] = ContextVar("org_graph", default=None)
_slug: ContextVar[Optional[str]] = ContextVar("org_slug", default=None)


def current_graph() -> Optional[str]:
    """The user organization's graph name, or None for the sample organization."""
    return _graph.get()


def current_slug() -> Optional[str]:
    return _slug.get()


def scope() -> str:
    """A string that tells organizations apart in caches and locks ('' = the sample organization)."""
    return _graph.get() or ""


@contextmanager
def org_scope(slug: Optional[str], graph: Optional[str]) -> Iterator[None]:
    """Work on one organization inside the block. `graph` None means the sample organization."""
    t1, t2 = _graph.set(graph), _slug.set(slug)
    try:
        yield
    finally:
        _graph.reset(t1)
        _slug.reset(t2)


class ScopedLock:
    """An asyncio.Lock per organization, with the same interface (acquire, release, locked,
    async with). One organization's slow ingest never blocks another's."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self) -> asyncio.Lock:
        return self._locks.setdefault(scope(), asyncio.Lock())

    def locked(self) -> bool:
        return self._lock().locked()

    async def acquire(self) -> bool:
        return await self._lock().acquire()

    def release(self) -> None:
        self._lock().release()

    async def __aenter__(self) -> "ScopedLock":
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.release()
