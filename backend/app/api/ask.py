"""Grounded question answering: POST /ask (one JSON result) and POST /ask/stream (SSE steps).

Both run the same pipeline (app/askflow/pipeline.py): intent by rules, entity matching, Cypher
traversal per intent, health, then one LLM call that only phrases the answer. Citations are
limited to real based_on sources that the answer text references.
"""

from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.rate_limiter import check_rate_limits
from app.api.schemas import AskRequest, AskResponse
from app.askflow.pipeline import collect_ask, run_ask
from app.config import get_settings
from app.ingest.live import sse

router = APIRouter(tags=["Question Answering"])
_settings = get_settings()


@router.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest, http_request: Request) -> AskResponse:
    """Answer a question grounded strictly in a retrieved FalkorDB subgraph."""
    check_rate_limits(http_request)
    result = await collect_ask(request.question, request.dataset_name or _settings.DATASET_NAME)
    return AskResponse(**result)


@router.post("/ask/stream")
async def ask_stream(request: AskRequest, http_request: Request) -> StreamingResponse:
    """The same answer as POST /ask, streamed as server-sent events: `step` (running / done, with
    ms), `query` (each Cypher statement with its row count), `path` (evidence before the answer),
    `token` (answer text), then `done` (the full AskResponse) or `error`."""
    check_rate_limits(http_request)
    dataset = request.dataset_name or _settings.DATASET_NAME

    async def stream() -> AsyncIterator[str]:
        async for event in run_ask(request.question, dataset):
            yield sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
