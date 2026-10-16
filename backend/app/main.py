"""ASGI entrypoint that binds the port immediately and loads the real app in the background.

Importing the application (cognee, litellm) takes ~8 s on a fast machine and longer on a small
container, which repeatedly missed the deploy healthcheck window before the port was even bound.
This wrapper starts instantly: while app.server loads in a thread, GET /health answers
{"status": "starting"} and every other request waits for the app instead of failing. Once loaded,
all traffic (including /health with its FalkorDB ping) goes to the real application, whose
lifespan (cache warm-up) is run as usual. If loading fails, requests return 500.
"""

import asyncio
import importlib
import json
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("decision_trace.boot")

_loaded = threading.Event()
_start_lock = threading.Lock()
_state: dict[str, Any] = {"app": None, "error": None, "started": False}


def _load() -> None:
    try:
        _state["app"] = importlib.import_module("app.server").app
    except BaseException as exc:  # noqa: BLE001 - reported on every request
        _state["error"] = exc
        logger.exception("Application failed to load")
    finally:
        _loaded.set()


def _ensure_loading() -> None:
    with _start_lock:
        if not _state["started"]:
            _state["started"] = True
            threading.Thread(target=_load, name="app-loader", daemon=True).start()


async def _loaded_app() -> Any:
    while not _loaded.is_set():
        await asyncio.sleep(0.05)
    if _state["error"] is not None:
        raise RuntimeError("Application failed to load") from _state["error"]
    return _state["app"]


async def _send_json(send: Any, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": payload})


async def _lifespan(receive: Any, send: Any) -> None:
    context: Optional[Any] = None
    starter: Optional[asyncio.Task] = None

    async def start_real_lifespan() -> None:
        nonlocal context
        real = await _loaded_app()
        context = real.router.lifespan_context(real)
        await context.__aenter__()

    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            _ensure_loading()
            starter = asyncio.create_task(start_real_lifespan())
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            if starter is not None and not starter.done():
                starter.cancel()
            if context is not None:
                await context.__aexit__(None, None, None)
            await send({"type": "lifespan.shutdown.complete"})
            return


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] == "lifespan":
        await _lifespan(receive, send)
        return
    _ensure_loading()
    if not _loaded.is_set() and scope["type"] == "http" and scope.get("path") == "/health":
        await _send_json(send, 200, {"status": "starting", "service": "decision-trace-backend"})
        return
    try:
        real = await _loaded_app()
    except RuntimeError:
        if scope["type"] == "http":
            await _send_json(send, 500, {"detail": "Application failed to load"})
        return
    await real(scope, receive, send)
