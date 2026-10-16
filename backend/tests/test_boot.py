"""The fast-binding entrypoint answers /health immediately and then serves the real app."""

import time

from fastapi.testclient import TestClient

import app.main as boot


def test_entrypoint_starts_then_delegates_to_the_real_app():
    with TestClient(boot.app) as client:
        first = client.get("/health")
        assert first.status_code == 200
        assert first.json()["status"] in ("starting", "healthy", "degraded")

        deadline = time.monotonic() + 60
        while not boot._loaded.is_set() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert boot._loaded.is_set() and boot._state["error"] is None

        # Real routes are served once loaded
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/no-such-route").status_code == 404
