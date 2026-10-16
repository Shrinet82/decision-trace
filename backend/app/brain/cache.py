"""A tiny time-based cache for expensive whole-graph computations (health, decision codes)."""

import time
from typing import Any, Awaitable, Callable, Optional

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


def put(namespace: str, key: str, value: Any) -> None:
    """Store a freshly computed value (used by the background refresher)."""
    _store[(namespace, key)] = (time.monotonic(), value)


def invalidate(namespace: Optional[str] = None) -> None:
    """Drop cached values (all, or one namespace), e.g. after the graph changes."""
    for k in [k for k in _store if namespace is None or k[0] == namespace]:
        _store.pop(k, None)
