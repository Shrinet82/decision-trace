"""A tiny time-based cache for expensive whole-graph computations (health, decision codes)."""

import time
from typing import Any, Awaitable, Callable

_store: dict[tuple[str, str], tuple[float, Any]] = {}


async def cached(
    namespace: str, key: str, ttl_seconds: float, compute: Callable[[], Awaitable[Any]]
) -> Any:
    """Return the cached value for (namespace, key) if younger than ttl, else compute and store it."""
    now = time.monotonic()
    hit = _store.get((namespace, key))
    if hit and now - hit[0] < ttl_seconds:
        return hit[1]
    value = await compute()
    _store[(namespace, key)] = (now, value)
    return value


def clear_cache() -> None:
    _store.clear()
