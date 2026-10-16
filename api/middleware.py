"""Request ids, request logging and rate limiting.

Logging writes one line per request: request id, method, route template, status and duration.
It never logs bodies, headers, query strings or path values, so shopper text and keys stay out.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable

from fastapi import FastAPI, Request

from .errors import error_response
from .settings import trust_proxy

logger = logging.getLogger("planogram_api")

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_NOT_LIMITED = {"/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
WINDOW_SECONDS = 60.0


class SlidingWindowLimiter:
    """At most `limit` requests per client in any 60-second window. In memory, per process."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, client: str) -> float:
        """0 if allowed (and counted), else seconds until the next request would be allowed."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(client, deque())
            while hits and now - hits[0] >= WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= self.limit:
                return WINDOW_SECONDS - (now - hits[0])
            hits.append(now)
            if len(self._hits) > 10_000:  # drop idle clients so memory stays bounded
                for key in [k for k, v in self._hits.items() if not v]:
                    del self._hits[key]
            return 0.0


def _client_address(request: Request) -> str:
    if trust_proxy():
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded.strip():
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _route_template(request: Request) -> str:
    """The matched route's template, e.g. /stores/{store_id}/search (never the actual path values)."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


def install_middleware(app: FastAPI, limiter: SlidingWindowLimiter) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        if request.url.path not in _NOT_LIMITED and request.method != "OPTIONS":
            wait = limiter.check(_client_address(request))
            if wait > 0:
                response = error_response(
                    request_id, 429, "RATE_LIMITED",
                    f"Too many requests: at most {limiter.limit} per minute. Try again shortly.",
                    {"Retry-After": str(max(1, math.ceil(wait)))},
                )
                return _finish(app, request, response, request_id, started)

        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.error("request_id=%s unhandled %s", request_id, type(exc).__name__)
            response = error_response(request_id, 500, "INTERNAL_ERROR", "Something went wrong on our side.")
        return _finish(app, request, response, request_id, started)


def _finish(app: FastAPI, request: Request, response, request_id: str, started: float):
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s route=%s status=%s duration_ms=%.1f",
        request_id, request.method, _route_template(request), response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response
