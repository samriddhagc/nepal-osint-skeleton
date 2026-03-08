"""Redis-backed API response cache middleware.

Since the dashboard is read-only (all users see the same data),
we compute each endpoint ONCE and serve the cached response to all
subsequent requests within a TTL window.

Covers the top endpoints automatically — no per-route changes needed.
"""
import hashlib
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Routes to cache: path prefix -> TTL in seconds
CACHED_ROUTES: dict[str, int] = {
    "/api/v1/stories/recent": 30,
    "/api/v1/map/events": 30,
    "/api/v1/election-results/live-snapshot": 30,
    "/api/v1/twitter/tweets": 60,
    "/api/v1/analytics/cluster-timeline": 45,
    "/api/v1/fact-check/results": 60,
    "/api/v1/market/summary": 60,
    "/api/v1/briefs/latest": 60,
    "/api/v1/kpi/snapshot": 15,
    "/api/v1/kpi/trends/hourly": 30,
    "/api/v1/announcements/summary": 60,
    "/api/v1/stories/sources": 30,
    "/api/v1/stories": 30,
    "/api/v1/election-results/summary": 30,
    "/api/v1/election-results/parties": 30,
    "/api/v1/province-anomalies/latest": 60,
    "/api/v1/promises/summary": 300,
    "/api/v1/promises": 300,
    "/api/v1/parliament/members": 120,
    "/api/v1/parliament/rankings": 120,
    "/api/v1/parliament/bills": 120,
    "/api/v1/parliament/committees": 120,
}

CACHE_PREFIX = "rcache:"


def _cache_key(path: str, query: str) -> str:
    """Build a short cache key from path + query string."""
    raw = f"{path}?{query}" if query else path
    return CACHE_PREFIX + hashlib.md5(raw.encode()).hexdigest()


def _match_route(path: str) -> int | None:
    """Return TTL if this path should be cached, else None."""
    for prefix, ttl in CACHED_ROUTES.items():
        if path == prefix or path.startswith(prefix + "?") or path.startswith(prefix + "/"):
            return ttl
    # Exact match for /api/v1/stories (without /recent etc)
    if path == "/api/v1/stories":
        return CACHED_ROUTES.get("/api/v1/stories", None)
    return None


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """Caches GET responses in Redis for read-only dashboard endpoints."""

    def __init__(self, app, redis_getter=None):
        super().__init__(app)
        self._get_redis = redis_getter

    async def dispatch(self, request: Request, call_next):
        # Only cache GET requests
        if request.method != "GET":
            return await call_next(request)

        path = request.url.path
        ttl = _match_route(path)
        if ttl is None:
            return await call_next(request)

        # Skip if force_refresh
        if request.query_params.get("force_refresh") == "true":
            return await call_next(request)

        query = str(request.url.query)
        key = _cache_key(path, query)

        # Try cache hit
        try:
            redis = await self._get_redis()
            cached = await redis.get(key)
            if cached is not None:
                return Response(
                    content=cached,
                    media_type="application/json",
                    headers={"X-Cache": "HIT"},
                )
        except Exception:
            # Redis down — fall through to compute
            return await call_next(request)

        # Cache miss — compute response
        response = await call_next(request)

        # Only cache successful JSON responses
        if response.status_code == 200:
            try:
                body_parts = []
                async for chunk in response.body_iterator:
                    if isinstance(chunk, bytes):
                        body_parts.append(chunk)
                    else:
                        body_parts.append(chunk.encode())
                body = b"".join(body_parts)

                # Store in Redis
                await redis.set(key, body, ex=ttl)

                return Response(
                    content=body,
                    status_code=200,
                    media_type="application/json",
                    headers=dict(response.headers) | {"X-Cache": "MISS"},
                )
            except Exception as e:
                logger.warning(f"Cache store failed: {e}")
                # Return original response body
                return Response(
                    content=body,
                    status_code=200,
                    media_type="application/json",
                )

        return response
