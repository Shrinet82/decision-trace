"""Organizations: create an empty one, look one up, delete it.

Everything else an organization has (decisions, ask, ingest, ...) is the ordinary API under the
`/orgs/<id>` prefix; see app.orgs.middleware.
"""

import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.rate_limiter import get_client_ip
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
        org = await registry.create(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return public(org)


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
async def delete_org(org_id: str) -> dict[str, Any]:
    """Delete an organization and everything in it. The sample organization cannot be deleted."""
    if org_id == registry.SAMPLE_ID:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The sample organization cannot be deleted.")
    if not await registry.delete(org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That organization does not exist.")
    return {"deleted": org_id}
