"""FastAPI Application Entrypoint for Decision-Trace Company Brain.

Features:
- Async lifespan managing database startup/shutdown checks
- Request ID tracking and structured access logging middleware
- Strict CORS configuration from environment settings
- Global error handling
- GET /health endpoint verifying FalkorDB connectivity
"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.ask import router as ask_router
from app.api.decisions import router as decisions_router
from app.api.graph import router as graph_router
from app.api.ingest import router as ingest_router
from app.api.people import router as people_router
from app.api.systems import router as systems_router
from app.brain.memory import ping_falkordb
from app.config import get_settings

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
)
logger = logging.getLogger("decision_trace.api")


async def _keep_caches_warm(interval_seconds: float = 240.0) -> None:
    """Recompute the health map and decision codes every few minutes (cache TTL is 5 min)."""
    from app.brain import cache
    from app.brain.codes import get_decision_codes
    from app.brain.health import evaluate_graph_health

    dataset = settings.DATASET_NAME
    while True:
        try:
            health, codes = await asyncio.gather(
                evaluate_graph_health(dataset_name=dataset), get_decision_codes(dataset)
            )
            cache.put("health", dataset, health)
            cache.put("codes", dataset or "", codes)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache warm-up failed: %s", exc)
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    logger.info("Initializing Decision-Trace backend...")
    is_falkor_alive = await ping_falkordb()
    if is_falkor_alive:
        logger.info("FalkorDB Cloud connection verified successfully.")
    else:
        logger.warning("FalkorDB Cloud connection ping failed during startup.")
    # Keep the health map and decision codes warm so no request pays for computing them.
    # Started in the background so it never delays startup (or the deploy healthcheck).
    warmer = asyncio.create_task(_keep_caches_warm())
    yield
    warmer.cancel()
    logger.info("Shutting down Decision-Trace backend...")


app = FastAPI(
    title="Decision-Trace Company Brain API",
    description="Knowledge graph backend connecting decisions, people, systems, and evidence via FalkorDB.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware
origins = [settings.FRONTEND_ORIGIN, "https://decision-trace.pages.dev"]
if "localhost" in settings.FRONTEND_ORIGIN:
    origins.append("http://127.0.0.1:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.pages\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(decisions_router)
app.include_router(ask_router)
app.include_router(graph_router)
app.include_router(systems_router)
app.include_router(people_router)
app.include_router(ingest_router)
app.include_router(admin_router)


@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next) -> Response:
    """Assigns unique request-id and logs execution time."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start_time = time.perf_counter()

    try:
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f"app;dur={duration_ms:.1f}"
        logger.info(
            "%s %s -> %d (%.2f ms) [req_id=%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "Unhandled error during %s %s (%.2f ms) [req_id=%s]: %s",
            request.method,
            request.url.path,
            duration_ms,
            request_id,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint validating service and FalkorDB connectivity."""
    falkordb_ok = await ping_falkordb()
    status_str = "healthy" if falkordb_ok else "degraded"
    response_code = status.HTTP_200_OK if falkordb_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
        "status": status_str,
        "service": "decision-trace-backend",
        "falkordb": "connected" if falkordb_ok else "disconnected",
        "dataset": settings.DATASET_NAME,
        "timestamp": time.time(),
    }
    return JSONResponse(status_code=response_code, content=payload)


@app.get("/")
async def root():
    """Root info endpoint."""
    return {
        "name": "Decision-Trace Company Brain",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
