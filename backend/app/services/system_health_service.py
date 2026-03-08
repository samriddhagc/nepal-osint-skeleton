"""System health aggregation service."""
import time
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.core.redis import get_redis
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_start_time = time.time()


class SystemHealthService:
    """Aggregates health status from all system components."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_full_status(self) -> dict:
        """Get comprehensive system health status."""
        database = await self._check_database()
        redis = await self._check_redis()
        workers = await self._check_workers()
        queues = await self._check_queues()

        return {
            "database": database,
            "redis": redis,
            "workers": workers,
            "queues": queues,
            "uptime_seconds": int(time.time() - _start_time),
            "version": "5.0.0",
            "environment": settings.app_env,
            "last_deployment": None,
        }

    async def _check_database(self) -> dict:
        """Check PostgreSQL health with pool stats."""
        try:
            result = await self.db.execute(text("SELECT 1"))
            pool = engine.pool

            # Measure latency
            start = time.time()
            await self.db.execute(text("SELECT 1"))
            latency_ms = round((time.time() - start) * 1000, 1)

            return {
                "status": "healthy",
                "pool_size": pool.size(),
                "active_connections": pool.checkedout(),
                "waiting": pool.overflow(),
                "latency_ms": latency_ms,
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "down",
                "pool_size": 0,
                "active_connections": 0,
                "waiting": 0,
                "latency_ms": 0,
                "error": str(e),
            }

    async def _check_redis(self) -> dict:
        """Check Redis health with memory info."""
        try:
            redis = await get_redis()
            await redis.ping()
            info = await redis.info("memory")
            clients_info = await redis.info("clients")
            keyspace_info = await redis.info("keyspace")

            memory_used = info.get("used_memory_human", "0B")
            memory_peak = info.get("used_memory_peak_human", "0B")
            connected_clients = clients_info.get("connected_clients", 0)

            # Count keys
            keys = 0
            for db_key, db_info in keyspace_info.items():
                if isinstance(db_info, dict):
                    keys += db_info.get("keys", 0)

            return {
                "status": "healthy",
                "memory_used": memory_used,
                "memory_peak": memory_peak,
                "connected_clients": connected_clients,
                "keys": keys,
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "down",
                "memory_used": "0B",
                "memory_peak": "0B",
                "connected_clients": 0,
                "keys": 0,
                "error": str(e),
            }

    async def _check_workers(self) -> dict:
        """Check APScheduler background worker status."""
        try:
            from app.tasks.scheduler import scheduler

            running = scheduler.running
            jobs = scheduler.get_jobs() if running else []

            # Find next fire time across all jobs
            next_run_in_seconds = None
            if jobs:
                import datetime
                now = datetime.datetime.now(datetime.timezone.utc)
                next_times = [
                    (j.next_run_time - now).total_seconds()
                    for j in jobs if j.next_run_time
                ]
                if next_times:
                    next_run_in_seconds = int(min(next_times))

            return {
                "status": "running" if running else "stopped",
                "scheduler_running": running,
                "registered_jobs": len(jobs),
                "next_run_in_seconds": next_run_in_seconds,
            }
        except Exception as e:
            logger.warning(f"Scheduler health check failed: {e}")
            return {
                "status": "stopped",
                "scheduler_running": False,
                "registered_jobs": 0,
                "next_run_in_seconds": None,
            }

    async def _check_queues(self) -> dict:
        """Check scheduler job breakdown by category."""
        # Job ID → category mapping
        INGESTION_JOBS = {
            "poll_priority", "poll_all", "scrape_ratopati", "scrape_news_sources",
            "poll_bipad", "poll_river", "poll_weather", "poll_announcements",
            "poll_twitter", "poll_market", "poll_energy",
            "poll_parliament_members", "poll_parliament_bills",
        }
        PROCESSING_JOBS = {
            "run_clustering", "generate_embeddings", "submit_analysis_batch",
            "process_completed_batches", "recalculate_parliament_scores", "train_ml",
        }
        # Everything else is monitoring/realtime

        try:
            from app.tasks.scheduler import scheduler

            if not scheduler.running:
                return {
                    "status": "stopped",
                    "ingestion_jobs": 0,
                    "processing_jobs": 0,
                    "realtime_jobs": 0,
                }

            jobs = scheduler.get_jobs()
            ingestion = sum(1 for j in jobs if j.id in INGESTION_JOBS)
            processing = sum(1 for j in jobs if j.id in PROCESSING_JOBS)
            realtime = len(jobs) - ingestion - processing

            return {
                "status": "healthy" if jobs else "degraded",
                "ingestion_jobs": ingestion,
                "processing_jobs": processing,
                "realtime_jobs": realtime,
            }
        except Exception:
            return {
                "status": "stopped",
                "ingestion_jobs": 0,
                "processing_jobs": 0,
                "realtime_jobs": 0,
            }

    async def get_api_metrics(self, period: str = "24h") -> dict:
        """Get API metrics from api_metrics table."""
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select, func

        # Parse period
        hours_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
        hours = hours_map.get(period, 24)
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        try:
            # Use raw SQL for aggregation on api_metrics table
            result = await self.db.execute(
                text("""
                    SELECT
                        COUNT(*) as request_count,
                        COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count,
                        COALESCE(AVG(response_time_ms), 0) as avg_ms,
                        COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms), 0) as p95_ms,
                        COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY response_time_ms), 0) as p99_ms
                    FROM api_metrics
                    WHERE recorded_at >= :since
                """),
                {"since": since},
            )
            row = result.fetchone()

            if not row or row[0] == 0:
                return {
                    "request_count": 0,
                    "error_count": 0,
                    "error_rate": 0.0,
                    "avg_response_ms": 0,
                    "p95_response_ms": 0,
                    "p99_response_ms": 0,
                    "endpoints": [],
                    "period": period,
                }

            request_count = row[0]
            error_count = row[1]

            # Per-endpoint breakdown
            endpoints_result = await self.db.execute(
                text("""
                    SELECT
                        endpoint, method,
                        COUNT(*) as cnt,
                        ROUND(AVG(response_time_ms)::numeric, 1) as avg_ms,
                        COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms), 0) as p95_ms,
                        COUNT(CASE WHEN status_code >= 400 THEN 1 END) as errors
                    FROM api_metrics
                    WHERE recorded_at >= :since
                    GROUP BY endpoint, method
                    ORDER BY cnt DESC
                    LIMIT 50
                """),
                {"since": since},
            )

            endpoints = [
                {
                    "path": r[0],
                    "method": r[1],
                    "count": r[2],
                    "avg_ms": float(r[3]),
                    "p95_ms": float(r[4]),
                    "errors": r[5],
                }
                for r in endpoints_result.fetchall()
            ]

            return {
                "request_count": request_count,
                "error_count": error_count,
                "error_rate": round(error_count / request_count, 4) if request_count else 0,
                "avg_response_ms": round(float(row[2]), 1),
                "p95_response_ms": round(float(row[3]), 1),
                "p99_response_ms": round(float(row[4]), 1),
                "endpoints": endpoints,
                "period": period,
            }
        except Exception as e:
            logger.warning(f"Failed to get API metrics: {e}")
            return {
                "request_count": 0,
                "error_count": 0,
                "error_rate": 0.0,
                "avg_response_ms": 0,
                "p95_response_ms": 0,
                "p99_response_ms": 0,
                "endpoints": [],
                "period": period,
            }
