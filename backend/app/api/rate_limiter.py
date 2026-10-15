"""Backend Rate Limiter and Daily LLM Usage Guard.

Enforces:
1. Per-IP rate limiting: 20 requests/minute, 200 requests/day.
2. Global daily LLM call cap: 500 calls/day.
"""

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


def record_llm_call() -> None:
    """Record a completed LLM invocation against the global daily cap."""
    _global_llm_calls.append(time.time())
