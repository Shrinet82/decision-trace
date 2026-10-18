"""The organization registry: one record per organization, stored in its own small graph.

The sample organization is not stored: it is the configured production graph, read-only except for
the tagged demo ingest. User organizations each get a graph named `org_<id>_<random>`. The registry
is also held in memory (the app runs as one process) and written through on every change.
"""

import asyncio
import logging
import re
import secrets
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.brain import cache
from app.brain.memory import delete_graph, graph_memory_bytes, run_on_graph
from app.config import get_settings

logger = logging.getLogger("decision_trace.orgs")

REGISTRY_GRAPH = "dt_registry"
SAMPLE_ID = "sample"
SAMPLE_NAME = "Acme Corp (sample)"
MAX_USER_ORGS = 25
MAX_NAME_LENGTH = 40
IDLE_HOURS = 72
# Writing last_active on every request would hammer the registry; once per interval is enough
_TOUCH_EVERY_SECONDS = 600

_orgs: dict[str, dict[str, Any]] = {}
_loaded = False
_load_lock = asyncio.Lock()
_touched: dict[str, float] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def sample_org() -> dict[str, Any]:
    return {
        "id": SAMPLE_ID,
        "name": SAMPLE_NAME,
        "graph_name": get_settings().FALKORDB_GRAPH_NAME,
        "created_at": None,
        "last_active": None,
        "source_count": 0,
        "sample": True,
    }


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug[:24].strip("-") or "org"


def clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValueError("Give the organization a name.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValueError(f"The name can be at most {MAX_NAME_LENGTH} characters.")
    if any(unicodedata.category(c).startswith("C") for c in cleaned):
        raise ValueError("The name contains characters that are not allowed.")
    return cleaned


async def load(force: bool = False) -> None:
    """Read the registry graph into memory (once; a missing graph means no organizations yet)."""
    global _loaded
    async with _load_lock:
        if _loaded and not force:
            return
        try:
            rows = await run_on_graph(
                REGISTRY_GRAPH,
                "MATCH (o:Org) RETURN o.id, o.name, o.graph_name, o.created_at, o.last_active, o.source_count",
            )
        except Exception as exc:  # noqa: BLE001 - the graph does not exist until the first organization
            logger.info("Registry graph not readable yet: %s", exc)
            rows = []
        _orgs.clear()
        for r in rows:
            _orgs[r[0]] = {
                "id": r[0], "name": r[1], "graph_name": r[2], "created_at": r[3],
                "last_active": r[4] or r[3], "source_count": int(r[5] or 0), "sample": False,
            }
        _loaded = True


async def get(slug: str) -> Optional[dict[str, Any]]:
    """An organization by id; 'sample' is always present."""
    if slug == SAMPLE_ID:
        return sample_org()
    await load()
    return _orgs.get(slug)


def user_orgs() -> list[dict[str, Any]]:
    return list(_orgs.values())


async def create(name: str) -> dict[str, Any]:
    """Create an empty organization and its graph. Raises ValueError (bad name) or LookupError (full)."""
    name = clean_name(name)
    await load()
    if len(_orgs) >= MAX_USER_ORGS:
        raise LookupError(f"The demo is full: at most {MAX_USER_ORGS} organizations exist at once. Try again later.")
    slug = f"{slugify(name)}-{secrets.token_hex(3)}"
    graph_name = f"org_{slug.replace('-', '_')}_{secrets.token_hex(3)}"
    # A graph only exists once something is written; write and remove a marker to bring it into being
    await run_on_graph(graph_name, "CREATE (:_init {id: 'init'})")
    await run_on_graph(graph_name, "MATCH (n:_init) DELETE n")
    org = {
        "id": slug, "name": name, "graph_name": graph_name, "created_at": _now(),
        "last_active": _now(), "source_count": 0, "sample": False,
    }
    await run_on_graph(
        REGISTRY_GRAPH,
        "CREATE (o:Org) SET o += $props",
        {"props": {k: v for k, v in org.items() if k != "sample"}},
    )
    _orgs[slug] = org
    logger.info("Created organization %s (graph %s)", slug, graph_name)
    return org


async def delete(slug: str) -> bool:
    """Delete an organization: its graph, its activity log and its registry record."""
    org = _orgs.get(slug)
    if not org or org["sample"]:
        return False
    await delete_graph(org["graph_name"])
    await delete_graph(f"{org['graph_name']}__changes")
    await run_on_graph(REGISTRY_GRAPH, "MATCH (o:Org {id: $id}) DELETE o", {"id": slug})
    _orgs.pop(slug, None)
    _touched.pop(slug, None)
    cache.invalidate()
    logger.info("Deleted organization %s", slug)
    return True


async def touch(slug: str) -> None:
    """Record activity so the organization is not deleted as idle."""
    org = _orgs.get(slug)
    if not org:
        return
    now = time.monotonic()
    if now - _touched.get(slug, -1e9) < _TOUCH_EVERY_SECONDS:
        return
    _touched[slug] = now
    org["last_active"] = _now()
    try:
        await run_on_graph(
            REGISTRY_GRAPH, "MATCH (o:Org {id: $id}) SET o.last_active = $at", {"id": slug, "at": org["last_active"]}
        )
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never fail a request
        logger.warning("Could not record activity for %s: %s", slug, exc)


async def set_source_count(slug: str, count: int) -> None:
    org = _orgs.get(slug)
    if not org:
        return
    org["source_count"] = count
    try:
        await run_on_graph(
            REGISTRY_GRAPH, "MATCH (o:Org {id: $id}) SET o.source_count = $n", {"id": slug, "n": count}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not store source count for %s: %s", slug, exc)


async def delete_idle(now: Optional[datetime] = None) -> list[str]:
    """Delete user organizations untouched for IDLE_HOURS. Never touches the sample."""
    await load()
    now = now or datetime.now(timezone.utc)
    removed = []
    for org in list(_orgs.values()):
        last = _parse(org.get("last_active")) or _parse(org.get("created_at"))
        if last and now - last > timedelta(hours=IDLE_HOURS):
            if await delete(org["id"]):
                removed.append(org["id"])
    return removed


async def idle_loop(interval_seconds: float = 3600.0) -> None:
    """Background task: delete idle organizations once an hour."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            removed = await delete_idle()
            if removed:
                logger.info("Deleted idle organizations: %s", removed)
        except Exception as exc:  # noqa: BLE001 - never let the loop die
            logger.warning("Idle organization sweep failed: %s", exc)


async def sizes() -> list[dict[str, Any]]:
    """Node, edge and memory figures for every organization graph (for the report and ops)."""
    out = []
    for org in [sample_org(), *user_orgs()]:
        g = org["graph_name"]
        try:
            n = await run_on_graph(g, "MATCH (n) RETURN count(n)")
            e = await run_on_graph(g, "MATCH ()-[r]->() RETURN count(r)")
            nodes, edges = (n[0][0] if n else 0), (e[0][0] if e else 0)
        except Exception:  # noqa: BLE001
            nodes = edges = None
        out.append({"id": org["id"], "graph": g, "nodes": nodes, "edges": edges, "memory_bytes": await graph_memory_bytes(g)})
    return out
