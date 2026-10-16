# Multi-stage Dockerfile for Decision-Trace Backend
# Stage 1: Build virtual environment
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv for fast, reliable dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /bin/uv

# Copy project metadata
COPY pyproject.toml ./

# Install dependencies into /app/.venv
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python --no-cache --compile-bytecode -r pyproject.toml

# Stage 2: Minimal runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

# Create non-root user with home directory
RUN groupadd -r appgroup && useradd -m -r -g appgroup -u 1000 appuser

# Set up data directories for persistent storage (SQLite and LanceDB) and caches
RUN mkdir -p /app/data_storage/.cognee_system /app/data_storage/.lancedb /tmp/fastembed_cache /home/appuser/.cache && \
    chown -R appuser:appgroup /app /tmp/fastembed_cache /home/appuser

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

# Copy application source
COPY --chown=appuser:appgroup app/ /app/app/
# Precompile app bytecode too, so the first boot does not compile anything (fast healthcheck)
RUN /app/.venv/bin/python -m compileall -q /app/app

# Environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/home/appuser \
    HF_HOME=/home/appuser/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/tmp/fastembed_cache \
    LANCEDB_PATH=/app/data_storage/.lancedb

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=10s --start-period=90s --retries=5 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
