"""Redis pub/sub bridge for cross-process real-time updates.

API replicas subscribe and broadcast to connected WebSocket clients.
Workers publish events to Redis without needing in-process WebSocket state.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

NEWS_CHANNEL = "nepalosint:ws:news"
MAP_CHANNEL = "nepalosint:ws:map"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_dumps(message: dict[str, Any]) -> str:
    return json.dumps(message, default=_json_default)


async def publish_news(message: dict[str, Any]) -> None:
    """Publish a message onto the news WebSocket channel."""
    redis = await get_redis()
    await redis.publish(NEWS_CHANNEL, _json_dumps(message))


async def publish_map(message: dict[str, Any]) -> None:
    """Publish a message onto the map WebSocket channel."""
    redis = await get_redis()
    await redis.publish(MAP_CHANNEL, _json_dumps(message))


async def _run_subscriber(
    channel: str,
    broadcast_fn: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    redis = await get_redis()
    pubsub = redis.pubsub()

    await pubsub.subscribe(channel)
    logger.info(f"Subscribed to Redis channel: {channel}")

    try:
        async for raw in pubsub.listen():
            if raw is None:
                continue
            if raw.get("type") != "message":
                continue

            data = raw.get("data")
            if data is None:
                continue
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Skipping invalid JSON from {channel}")
                continue

            try:
                await broadcast_fn(message)
            except Exception:
                logger.exception(f"Broadcast handler failed for {channel}")

    except asyncio.CancelledError:
        raise
    finally:
        try:
            await pubsub.unsubscribe(channel)
        finally:
            await pubsub.close()
            logger.info(f"Unsubscribed from Redis channel: {channel}")


async def start_news_subscriber(
    broadcast_fn: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Run a Redis subscriber that forwards messages to WebSocket clients."""
    await _run_subscriber(NEWS_CHANNEL, broadcast_fn)


async def start_map_subscriber(
    broadcast_fn: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Run a Redis subscriber that forwards map overlay messages."""
    await _run_subscriber(MAP_CHANNEL, broadcast_fn)

