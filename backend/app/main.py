"""Nepal OSINT - FastAPI Application."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.api.v1.router import router as api_v1_router
from app.api.v1.websocket import router as ws_router
from app.core.realtime_bus import start_news_subscriber
from app.core.redis import close_redis
from app.core.websocket import news_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info(f"Starting {settings.app_name}...")

    tasks = [
        asyncio.create_task(start_news_subscriber(news_manager.broadcast)),
    ]

    # Start background scheduler (RSS polling, scraping, etc.)
    # Controlled by RUN_SCHEDULER env var; defaults to True
    if settings.run_scheduler:
        from app.tasks.scheduler import start_scheduler
        start_scheduler()
        logger.info("Scheduler started automatically")

    yield
    logger.info("Shutting down...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    description="Open-source backend for Nepal OSINT platform",
    version="5.0.0",
    lifespan=lifespan,
)

# ── Request timing middleware for API monitoring ──

class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Records request timing to api_metrics via Redis buffer, flushed to DB periodically."""

    _buffer: list[dict] = []
    _buffer_lock = None
    _flush_task: asyncio.Task | None = None
    FLUSH_INTERVAL = 60
    MAX_BUFFER = 500

    @classmethod
    def _get_lock(cls):
        if cls._buffer_lock is None:
            cls._buffer_lock = asyncio.Lock()
        return cls._buffer_lock

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)

        path = request.url.path
        if path.startswith("/api/") and not path.endswith("/health"):
            async with self._get_lock():
                self._buffer.append({
                    "endpoint": path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "response_time_ms": duration_ms,
                    "user_id": None,
                })

            if self._flush_task is None or self._flush_task.done():
                self.__class__._flush_task = asyncio.create_task(self._flush_loop())

        return response

    @classmethod
    async def _flush_loop(cls):
        """Background loop that flushes buffered metrics to DB."""
        while True:
            await asyncio.sleep(cls.FLUSH_INTERVAL)
            await cls._flush_buffer()

    @classmethod
    async def _flush_buffer(cls):
        """Flush buffered metrics to DB in a single batch."""
        async with cls._get_lock():
            if not cls._buffer:
                return
            batch = cls._buffer[:]
            cls._buffer.clear()

        if not batch:
            return

        try:
            from app.core.database import AsyncSessionLocal
            from sqlalchemy import text

            async with AsyncSessionLocal() as db:
                await db.execute(
                    text(
                        "INSERT INTO api_metrics (endpoint, method, status_code, response_time_ms, user_id) "
                        "VALUES (:endpoint, :method, :status_code, :response_time_ms, :user_id)"
                    ),
                    batch,
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to flush {len(batch)} metrics: {e}")


app.add_middleware(RequestTimingMiddleware)

# ── Response cache: compute once, serve to all (read-only dashboard) ──
from app.core.response_cache import ResponseCacheMiddleware
from app.core.redis import get_redis as _get_redis
app.add_middleware(ResponseCacheMiddleware, redis_getter=_get_redis)

# In development, allow local-network origins so the UI can be opened from
# localhost, 127.0.0.1, or LAN IPs without CORS failures.
dev_local_origin_regex = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|0\.0\.0\.0|"
    r"(?:\d{1,3}\.){3}\d{1,3}"
    r")(?::\d+)?$"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=dev_local_origin_regex if settings.app_env == "development" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_v1_router)

# Include WebSocket router (at root level, not under /api/v1)
app.include_router(ws_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "5.0.0",
        "status": "operational",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    """Readiness check endpoint (DB + Redis)."""
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        redis = await get_redis()
        await redis.ping()
    except Exception as e:
        logger.warning(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Not ready")

    return {"status": "ready"}
