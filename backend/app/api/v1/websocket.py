"""WebSocket endpoints for real-time updates."""
import asyncio
import json as _json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import require_dev
from app.core.websocket import news_manager
from app.core.database import AsyncSessionLocal
from app.repositories.story import StoryRepository
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

# --- Reconnection storm protection ---
# Cap concurrent DB sessions for initial story loads so mass reconnects
# don't exhaust the connection pool.
_initial_stories_sem = asyncio.Semaphore(5)
_initial_stories_cache: str | None = None
_initial_stories_cache_ts: float = 0

router = APIRouter(tags=["websocket"])


async def _authenticate_websocket(websocket: WebSocket) -> bool:
    """Validate ?token= access token for WebSocket connections."""
    token = websocket.query_params.get("token")
    if not token:
        return False

    payload = AuthService.decode_token(token)
    if not payload or payload.type != "access":
        return False

    try:
        user_id = UUID(payload.sub)
    except ValueError:
        return False

    async with AsyncSessionLocal() as db:
        auth = AuthService(db)
        user = await auth.get_user_by_id(user_id)
        if not user or not user.is_active:
            return False

    return True


@router.websocket("/ws/news")
async def news_feed_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time news feed.

    Clients receive:
    - new_story: When a new Nepal story is ingested
    - heartbeat: Every 30 seconds to keep connection alive
    - initial_stories: Recent stories on connection (last 1 hour)

    Message format:
    {
        "type": "new_story" | "heartbeat" | "initial_stories",
        "timestamp": "2026-01-27T12:00:00Z",
        "data": { ... }
    }
    """
    # Auth-first (reject without accepting)
    is_authed = await _authenticate_websocket(websocket)
    if not is_authed:
        await websocket.close(code=1008)
        return

    # Check connection cap before accepting
    if len(news_manager.active_connections) >= news_manager.MAX_CONNECTIONS:
        await websocket.close(code=1013)
        logger.warning("WebSocket rejected — at connection cap")
        return

    await websocket.accept()
    await news_manager.register(websocket)
    logger.info("WebSocket client connected to /ws/news (authed)")

    # Broadcast updated viewer count to all clients
    await news_manager.broadcast_viewer_count()

    try:
        # Send recent stories on connect (last 24 hours)
        await _send_initial_stories(websocket)

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages with timeout for heartbeat
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
                # Handle ping/pong or client messages
                vc = news_manager.viewer_count
                if data == "ping":
                    await websocket.send_text(
                        f'{{"type":"pong","channel":"system","event_type":"pong","timestamp":"{datetime.now(timezone.utc).isoformat()}","viewers":{vc}}}'
                    )
                else:
                    # Back-compat: allow JSON pings: {"type":"ping"} or {"event_type":"ping"}
                    try:
                        import json

                        msg = json.loads(data)
                        if isinstance(msg, dict) and (msg.get("type") == "ping" or msg.get("event_type") == "ping"):
                            await websocket.send_text(
                                f'{{"type":"pong","channel":"system","event_type":"pong","timestamp":"{datetime.now(timezone.utc).isoformat()}","viewers":{vc}}}'
                            )
                    except Exception:
                        pass
            except asyncio.TimeoutError:
                # Send heartbeat with viewer count
                try:
                    news_manager.tick_viewers()
                    vc = news_manager.viewer_count
                    await websocket.send_text(
                        f'{{"type":"heartbeat","channel":"system","event_type":"heartbeat","timestamp":"{datetime.now(timezone.utc).isoformat()}","viewers":{vc}}}'
                    )
                except Exception:
                    # Connection likely closed
                    break

    except WebSocketDisconnect:
        logger.info("Client disconnected from news feed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await news_manager.disconnect(websocket)
        # Broadcast updated viewer count after disconnect
        await news_manager.broadcast_viewer_count()


async def _fetch_initial_stories_json() -> str:
    """Fetch recent stories as pre-serialized JSON. Cached 30s, capped at 50 stories."""
    import time

    global _initial_stories_cache, _initial_stories_cache_ts

    now = time.monotonic()
    if _initial_stories_cache is not None and (now - _initial_stories_cache_ts) < 30:
        return _initial_stories_cache

    async with _initial_stories_sem:
        # Double-check after acquiring semaphore (another coroutine may have refreshed)
        now = time.monotonic()
        if _initial_stories_cache is not None and (now - _initial_stories_cache_ts) < 30:
            return _initial_stories_cache

        async with AsyncSessionLocal() as db:
            repo = StoryRepository(db)
            stories = await repo.get_recent_stories_limited(hours=6, limit=600, nepal_only=True)

            data = []
            for story in stories:
                data.append({
                    "id": str(story.id),
                    "title": story.title,
                    "url": story.url,
                    "summary": story.summary,
                    "source_id": story.source_id,
                    "source_name": story.source_name,
                    "category": story.category,
                    "severity": story.severity,
                    "cluster_id": str(story.cluster_id) if story.cluster_id else None,
                    "published_at": story.published_at.isoformat() if story.published_at else None,
                    "created_at": story.created_at.isoformat() if story.created_at else None,
                })

            # Pre-serialize once — avoids re-serializing per client
            payload = _json.dumps({
                "type": "initial_stories",
                "channel": "feed",
                "event_type": "initial_stories",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            })

            _initial_stories_cache = payload
            _initial_stories_cache_ts = now
            logger.info(f"Cached {len(data)} initial stories ({len(payload)//1024}KB)")
            return payload


async def _send_initial_stories(websocket: WebSocket):
    """Send recent stories (6h, max 50). Pre-serialized + cached to survive mass reconnects."""
    from starlette.websockets import WebSocketState

    if websocket.client_state != WebSocketState.CONNECTED:
        return

    try:
        payload = await _fetch_initial_stories_json()

        if websocket.client_state != WebSocketState.CONNECTED:
            return

        await websocket.send_text(payload)

    except Exception as e:
        logger.warning(f"Failed to send initial stories: {e}")


@router.get("/ws/status")
async def websocket_status(
    _=Depends(require_dev),
):
    """Get WebSocket connection status."""
    return {
        "active_connections": news_manager.connection_count,
        "status": "healthy",
    }
