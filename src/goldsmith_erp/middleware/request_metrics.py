# src/goldsmith_erp/middleware/request_metrics.py
"""
Lightweight request metrics middleware.

Tracks:
- Request count per minute   (ring buffer, deque maxlen=60)
- Response time percentiles  (p50 / p95 / p99) over the last 1 000 requests
- Error counts for 4xx and 5xx responses

No external dependencies, no DB writes, resets on restart.
"""
from __future__ import annotations

import statistics
import time
from collections import deque
from typing import Any, Deque, Dict, List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# ---------------------------------------------------------------------------
# Module-level ring buffers — all access is single-threaded inside asyncio
# ---------------------------------------------------------------------------

# One entry per completed request: (minute_bucket: int, duration_ms: float, status_code: int)
# minute_bucket = int(time.time() // 60)
_REQUEST_LOG: Deque[Tuple[int, float, int]] = deque(maxlen=1_000)

# Counts per 60 one-minute buckets  → requests per minute
_MINUTE_BUCKETS: Deque[Tuple[int, int]] = deque(maxlen=60)  # (minute_key, count)

_error_4xx: int = 0
_error_5xx: int = 0
_total_requests: int = 0


def _record(duration_ms: float, status_code: int) -> None:
    """Append a completed request to the shared ring buffer."""
    global _error_4xx, _error_5xx, _total_requests

    _total_requests += 1
    minute_key = int(time.time() // 60)
    _REQUEST_LOG.append((minute_key, duration_ms, status_code))

    if 400 <= status_code < 500:
        _error_4xx += 1
    elif status_code >= 500:
        _error_5xx += 1

    # Update per-minute bucket counter
    if _MINUTE_BUCKETS and _MINUTE_BUCKETS[-1][0] == minute_key:
        last_key, last_count = _MINUTE_BUCKETS[-1]
        _MINUTE_BUCKETS[-1] = (last_key, last_count + 1)
    else:
        _MINUTE_BUCKETS.append((minute_key, 1))


def get_metrics() -> Dict[str, Any]:
    """
    Return current request metrics as a plain dict.

    Shape::

        {
            "total_requests": int,
            "requests_per_minute": float,   # average over last 60 min buckets
            "current_minute_requests": int,
            "response_time_ms": {
                "p50": float,
                "p95": float,
                "p99": float,
            },
            "errors": {
                "4xx": int,
                "5xx": int,
            },
        }
    """
    durations: List[float] = [d for (_, d, _) in _REQUEST_LOG]

    if durations:
        sorted_dur = sorted(durations)
        n = len(sorted_dur)
        p50 = sorted_dur[int(n * 0.50)]
        p95 = sorted_dur[min(int(n * 0.95), n - 1)]
        p99 = sorted_dur[min(int(n * 0.99), n - 1)]
    else:
        p50 = p95 = p99 = 0.0

    # Requests per minute: average of non-empty minute buckets
    if _MINUTE_BUCKETS:
        rpm_avg = round(
            sum(count for (_, count) in _MINUTE_BUCKETS) / len(_MINUTE_BUCKETS), 1
        )
        current_minute_key = int(time.time() // 60)
        current_minute_requests = next(
            (count for (key, count) in reversed(_MINUTE_BUCKETS) if key == current_minute_key),
            0,
        )
    else:
        rpm_avg = 0.0
        current_minute_requests = 0

    return {
        "total_requests": _total_requests,
        "requests_per_minute": rpm_avg,
        "current_minute_requests": current_minute_requests,
        "response_time_ms": {
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
        },
        "errors": {
            "4xx": _error_4xx,
            "5xx": _error_5xx,
        },
    }


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that records response time and status code for every
    request passing through the application.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # Unhandled exception — count as 500
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _record(duration_ms, 500)
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _record(duration_ms, status_code)
        return response
