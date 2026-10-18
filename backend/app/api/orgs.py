"""Organizations: create an empty one, look one up, delete it.

Everything else an organization has (decisions, ask, ingest, ...) is the ordinary API under the
`/orgs/<id>` prefix; see app.orgs.middleware.
"""

import time
from collections import defaultdict
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.rate_limiter import get_client_ip
from app.brain import orgctx
from app.brain.memory import run_on_graph
from app.orgs import registry

router = APIRouter(tags=["Organizations"])

MAX_CREATES_PER_HOUR = 3
_creates: dict[str, list[float]] = defaultdict(list)


class CreateOrg(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


def _check_create_limit(request: Request) -> None:
    ip = get_client_ip(request)
    now = time.time()
    _creates[ip] = [t for t in _creates[ip] if now - t < 3600.0]
    if len(_creates[ip]) >= MAX_CREATES_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You can create at most {MAX_CREATES_PER_HOUR} organizations per hour. Try again later.",
        )
    _creates[ip].append(now)


OWNER_KEY_HEADER = "X-Org-Key"
READ_ONLY_MESSAGE = (
    "This organization is read-only here: only the browser that created it holds its owner key. "
    "Create your own organization to add sources."
)


async def require_owner(x_org_key: Optional[str] = Header(default=None, alias=OWNER_KEY_HEADER)) -> None:
    """Dependency for every write: inside an organization somebody created, the request must carry
    that organization's owner key (header X-Org-Key). Viewing never needs it. The sample and
    showcase organizations have no owner; their writes are the tagged demo ingests that reset."""
    slug = orgctx.current_slug()
    if not orgctx.is_user_org() or slug is None:
        return
    org = await registry.get(slug)
    if org is None or not registry.key_matches(org, x_org_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=READ_ONLY_MESSAGE)


def public(org: dict[str, Any]) -> dict[str, Any]:
    """What clients see of an organization (never the graph name)."""
    return {
        "id": org["id"], "name": org["name"], "sample": bool(org["sample"]),
        "created_at": org["created_at"], "last_active": org["last_active"],
        "source_count": org["source_count"],
    }


@router.post("/orgs", status_code=status.HTTP_201_CREATED)
async def create_org(body: CreateOrg, request: Request) -> dict[str, Any]:
    """Create an empty organization (its own graph). Limits: 3 per hour per IP, 25 in total."""
    try:
        registry.clean_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    _check_create_limit(request)
    try:
        org, key = await registry.create(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    # The owner key is shown once and stored only as a hash: whoever holds it can change the organization
    return {**public(org), "owner_key": key}


@router.get("/orgs")
async def list_showcase() -> list[dict[str, Any]]:
    """The showcase organizations everyone can open (read-only, real data), for the organization menu."""
    await registry.refresh_if_stale()
    return [public(o) for o in sorted(registry.sample_orgs(), key=lambda o: o["name"])]


@router.get("/orgs/{org_id}")
async def get_org(org_id: str) -> dict[str, Any]:
    """One organization with its size. Unknown (or deleted, or idle-expired) ids are a 404."""
    org = await registry.get(org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That organization does not exist.")
    nodes = await run_on_graph(org["graph_name"], "MATCH (n) RETURN count(n)")
    edges = await run_on_graph(org["graph_name"], "MATCH ()-[r]->() RETURN count(r)")
    return {
        **public(org),
        "nodes": nodes[0][0] if nodes else 0,
        "edges": edges[0][0] if edges else 0,
        "idle_hours_before_deletion": None if org["sample"] else registry.IDLE_HOURS,
    }


@router.delete("/orgs/{org_id}")
async def delete_org(org_id: str, x_org_key: Optional[str] = Header(default=None, alias=OWNER_KEY_HEADER)) -> dict[str, Any]:
    """Delete an organization and everything in it (needs its owner key). Sample organizations cannot be deleted."""
    org = await registry.get(org_id)
    if org_id == registry.SAMPLE_ID or (org is not None and org["sample"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The sample organizations cannot be deleted.")
    if org is not None and not registry.key_matches(org, x_org_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Deleting an organization needs its owner key.")
    if not await registry.delete(org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That organization does not exist.")
    return {"deleted": org_id}
