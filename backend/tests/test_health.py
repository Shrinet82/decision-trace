"""Unit tests for FastAPI endpoints and middleware."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    """Verify root endpoint status and metadata."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Decision-Trace Company Brain"
        assert "X-Request-ID" in resp.headers


@pytest.mark.asyncio
async def test_health_check_healthy():
    """Verify /health returns 200 when FalkorDB is reachable."""
    transport = httpx.ASGITransport(app=app)
    with patch("app.main.ping_falkordb", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["falkordb"] == "connected"
            assert "X-Request-ID" in resp.headers


@pytest.mark.asyncio
async def test_health_check_degraded():
    """Verify /health returns 503 when FalkorDB is unreachable."""
    transport = httpx.ASGITransport(app=app)
    with patch("app.main.ping_falkordb", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = False
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["falkordb"] == "disconnected"
