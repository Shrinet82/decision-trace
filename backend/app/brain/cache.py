"""A tiny time-based cache for expensive whole-graph computations (health, decision codes)."""

import asyncio
import functools
import time
from typing import Any, Awaitable, Callable, Optional

_store: dict[tuple[str, str], tuple[float, Any]] = {}
_locks: dict[tuple[str, str], asyncio.Lock] = {}


async def cached(
    namespace: str, key: str, ttl_seconds: float, compute: Callable[[], Awaitable[Any]]
) -> Any:
    """Return the cached value for (namespace, key) if younger than ttl, else compute and store it."""
    hit = _store.get((namespace, key))
    if hit and time.monotonic() - hit[0] < ttl_seconds:
        return hit[1]
    # One computation per key: concurrent callers wait for it instead of repeating the queries
    lock = _locks.setdefault((namespace, key), asyncio.Lock())
    async with lock:
        hit = _store.get((namespace, key))
        if hit and time.monotonic() - hit[0] < ttl_seconds:
            return hit[1]
        value = await compute()
        _store[(namespace, key)] = (time.monotonic(), value)
        return value


def cached_endpoint(namespace: str, ttl_seconds: float = 120.0) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Cache an async read endpoint per argument set. Ingest and reset call invalidate(), which
    drops these too, so a page never shows data older than the last change to the graph."""

    def wrap(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def inner(*args: Any, **kwargs: Any) -> Any:
            key = repr((args, sorted(kwargs.items())))
            return await cached(namespace, key, ttl_seconds, lambda: fn(*args, **kwargs))

        return inner

    return wrap


def clear_cache() -> None:
    _store.clear()
    _locks.clear()


def put(namespace: str, key: str, value: Any) -> None:
    """Store a freshly computed value (used by the background refresher)."""
    _store[(namespace, key)] = (time.monotonic(), value)


def invalidate(namespace: Optional[str] = None) -> None:
    """Drop cached values (all, or one namespace), e.g. after the graph changes."""
    for k in [k for k in _store if namespace is None or k[0] == namespace]:
        _store.pop(k, None)
