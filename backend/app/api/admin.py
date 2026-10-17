"""Administrative API endpoints protected by admin secret token."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.schemas import ResetResponse
from app.brain.memory import DestructiveResetRefused, reset
from app.config import get_settings

logger = logging.getLogger("decision_trace.api.admin")
router = APIRouter(prefix="/admin", tags=["Administration"])
_settings = get_settings()


def verify_admin_token(
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> None:
    """Validate that request includes the authorized admin token."""
    expected = _settings.ADMIN_TOKEN.get_secret_value()

    token = x_admin_token
    if not token and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]

    if not token or token != expected:
        logger.warning("Unauthorized access attempt to administrative endpoint.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/reset", response_model=ResetResponse, dependencies=[Depends(verify_admin_token)])
async def reset_database(
    dataset_name: Optional[str] = Query(None, description="Target dataset name to reset"),
) -> ResetResponse:
    """Reset the knowledge graph, deleting all nodes, edges, vectors, and Cognee metadata."""
    target_dataset = dataset_name or _settings.DATASET_NAME
    logger.warning("Admin triggered complete reset of dataset '%s'...", target_dataset)

    try:
        await reset(dataset_name=target_dataset)
        return ResetResponse(
            status="success",
            dataset=target_dataset,
            message=f"Dataset '{target_dataset}' successfully reset.",
        )
    except DestructiveResetRefused as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Admin reset failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reset operation failed: {exc}",
        ) from exc
