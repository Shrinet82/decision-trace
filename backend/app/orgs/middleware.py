"""Routes `/orgs/<slug>/<path>` to `/<path>` working on that organization's graph.

Every endpoint, the streams and the caches therefore need no organization parameter: the
middleware sets the graph for the request (app.brain.orgctx) and rewrites the path. The unprefixed
routes keep serving the sample organization, so MCP clients and old links still work.
"""

import json
from typing import Any

from app.brain import orgctx
from app.orgs import registry


async def _json(send: Any, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body).encode()
    await send({
        "type": "http.response.start", "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
    })
    await send({"type": "http.response.body", "body": payload})


class OrgScopeMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        parts = scope["path"].split("/")  # ['', 'orgs', slug, 'rest', ...]
        if len(parts) < 4 or parts[1] != "orgs" or not parts[3]:
            await self.app(scope, receive, send)
            return
        slug = parts[2]
        org = await registry.get(slug)
        if org is None:
            await _json(send, 404, {"detail": "That organization does not exist (it may have been deleted)."})
            return
        rest = "/" + "/".join(parts[3:])
        scope = dict(scope)
        scope["path"] = rest
        if scope.get("raw_path"):
            raw = scope["raw_path"].decode("latin-1")
            scope["raw_path"] = ("/" + "/".join(raw.split("/")[3:])).encode("latin-1")
        graph = None if org["sample"] else org["graph_name"]
        with orgctx.org_scope(None if org["sample"] else slug, graph):
            if graph:
                await registry.touch(slug)
            await self.app(scope, receive, send)
