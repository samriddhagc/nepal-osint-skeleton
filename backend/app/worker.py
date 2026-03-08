"""Background worker process for Nepal OSINT.

Runs scheduled ingestion jobs and publishes realtime events to Redis.
This is intended to run as a single replica in production.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.core.redis import close_redis
from app.tasks.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    logger.info(f"Starting worker for {settings.app_name}...")
    scheduler_started = False
    if settings.run_scheduler:
        start_scheduler()
        scheduler_started = True
    else:
        logger.warning("RUN_SCHEDULER=false; worker started without scheduled jobs")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Shutting down worker...")
        if scheduler_started:
            stop_scheduler()
        await close_redis()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
