"""Backend Rate Limiter and Daily LLM Usage Guard.

Enforces:
1. Per-IP rate limiting: 20 requests/minute, 200 requests/day.
2. Global daily LLM call cap: 500 calls/day.
"""

import logging
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

# Per-IP tracking
_ip_min_requests: dict[str, list[float]] = defaultdict(list)
_ip_day_requests: dict[str, list[float]] = defaultdict(list)

# Global daily tracking
_global_llm_calls: list[float] = []

MAX_REQ_PER_MIN = 20
MAX_REQ_PER_DAY = 200
MAX_GLOBAL_LLM_PER_DAY = 500


def get_client_ip(request: Request) -> str:
    """Extract real client IP considering Cloudflare and proxy headers."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    x_forwarded = request.headers.get("x-forwarded-for")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


def check_rate_limits(request: Request) -> str:
    """Validate per-IP rate limits (20/min, 200/day) and global daily cap."""
    now = time.time()
    ip = get_client_ip(request)

    # 1. Clean up windows
    _ip_min_requests[ip] = [t for t in _ip_min_requests[ip] if now - t < 60.0]
    _ip_day_requests[ip] = [t for t in _ip_day_requests[ip] if now - t < 86400.0]

    # 2. Check minute limit
    if len(_ip_min_requests[ip]) >= MAX_REQ_PER_MIN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: maximum {MAX_REQ_PER_MIN} requests per minute per IP.",
        )

    # 3. Check day limit
    if len(_ip_day_requests[ip]) >= MAX_REQ_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily limit exceeded: maximum {MAX_REQ_PER_DAY} requests per day per IP.",
        )

    # 4. Check global daily LLM cap
    global _global_llm_calls
    _global_llm_calls = [t for t in _global_llm_calls if now - t < 86400.0]
    if len(_global_llm_calls) >= MAX_GLOBAL_LLM_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Global daily LLM request quota reached. Please try again tomorrow.",
        )

    # Record request
    _ip_min_requests[ip].append(now)
    _ip_day_requests[ip].append(now)
    return ip


logger = logging.getLogger("decision_trace.usage")

DEMO_LIMIT_MESSAGE = (
    "Demo limit reached: today's AI budget for this public demo is used up, so new answers are paused "
    "until tomorrow. Decisions, Systems, People, Sources and Explore still work."
)
# (timestamp, tokens) over the last 24 hours
_token_usage: list[tuple[float, int]] = []


def record_llm_call() -> None:
    """Record an LLM invocation against the global daily cap."""
    _global_llm_calls.append(time.time())


def estimate_tokens(*texts: str) -> int:
    """About 4 characters per token; good enough for a spending guard."""
    return sum(len(t) for t in texts) // 4 + 1


def tokens_used_today() -> int:
    global _token_usage
    cutoff = time.time() - 86400.0
    _token_usage = [(t, n) for t, n in _token_usage if t >= cutoff]
    return sum(n for _, n in _token_usage)


def record_tokens(tokens: int, label: str) -> None:
    """Add a call's estimated tokens to today's total and log usage."""
    from app.config import get_settings

    _token_usage.append((time.time(), tokens))
    budget = get_settings().LLM_DAILY_TOKEN_BUDGET
    logger.info("LLM usage: +%d tokens (%s); %d of %s in the last 24 h", tokens, label,
                tokens_used_today(), budget or "unlimited")


def budget_exceeded() -> bool:
    from app.config import get_settings

    budget = get_settings().LLM_DAILY_TOKEN_BUDGET
    return budget > 0 and tokens_used_today() >= budget


# Live ingest is LLM-heavy and mutates demo data: 3 requests per minute per IP
_ip_ingest_requests: dict[str, list[float]] = defaultdict(list)
MAX_INGEST_PER_MIN = 3


def check_ingest_rate_limit(request: Request) -> str:
    """3 ingest/reset requests per minute per IP, plus the global daily LLM cap."""
    now = time.time()
    ip = get_client_ip(request)
    _ip_ingest_requests[ip] = [t for t in _ip_ingest_requests[ip] if now - t < 60.0]
    if len(_ip_ingest_requests[ip]) >= MAX_INGEST_PER_MIN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Ingest rate limit: at most {MAX_INGEST_PER_MIN} per minute. Try again shortly.",
        )
    global _global_llm_calls
    _global_llm_calls = [t for t in _global_llm_calls if now - t < 86400.0]
    if len(_global_llm_calls) >= MAX_GLOBAL_LLM_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Global daily LLM request quota reached. Please try again tomorrow.",
        )
    _ip_ingest_requests[ip].append(now)
    return ip
