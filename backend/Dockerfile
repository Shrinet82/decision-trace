# Multi-stage Dockerfile for Decision-Trace Backend
# Stage 1: Build virtual environment
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv for fast, reliable dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /bin/uv

# Copy project metadata
COPY pyproject.toml ./

# Install dependencies into /build/.venv
RUN uv venv /build/.venv && \
    uv pip install --python /build/.venv/bin/python --no-cache -r pyproject.toml

# Stage 2: Minimal runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

# Create non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1000 appuser

# Set up data directories for persistent storage (SQLite and LanceDB)
RUN mkdir -p /app/data_storage/.cognee_system /app/data_storage/.lancedb && \
    chown -R appuser:appgroup /app

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appgroup /build/.venv /app/.venv

# Copy application source
COPY --chown=appuser:appgroup app/ /app/app/

# Environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    LANCEDB_PATH=/app/data_storage/.lancedb

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
