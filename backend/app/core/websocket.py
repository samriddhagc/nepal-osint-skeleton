"""WebSocket connection manager for real-time updates."""
import asyncio
import json
import logging
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class UUIDEncoder(json.JSONEncoder):
    """JSON encoder that handles UUID and datetime objects."""
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class _ViewerSimulator:
    """Server-side viewer count simulator. All clients see the same number."""

    def __init__(self):
        self._current = self._base()
        self._trend = 0
        self._last_tick = time.monotonic()

    @staticmethod
    def _base() -> int:
        """Time-of-day base using Nepal time (UTC+5:45). ~80 at 3:30am, ~280 at 1:30pm."""
        now = datetime.now(timezone.utc)
        utc_h = now.hour + now.minute / 60.0
        npt_h = (utc_h + 5.75) % 24
        phase = ((npt_h - 13.5) / 24) * 2 * math.pi
        return round(180 + 100 * math.cos(phase))

    def tick(self) -> int:
        """Advance simulation by one step. Called on heartbeat (~30s)."""
        target = self._base()
        # Drift trend occasionally
        if random.random() < 0.2:
            self._trend = round((random.random() - 0.5) * 3)
        # Move towards target gradually
        diff = target - self._current
        drift = max(-2, min(2, diff))
        jitter = self._trend + round((random.random() - 0.5) * 4)
        spike = round((random.random() - 0.3) * 8) if random.random() < 0.04 else 0
        self._current = max(60, self._current + drift + jitter + spike)
        return self._current

    @property
    def count(self) -> int:
        return self._current


class ConnectionManager:
    """
    WebSocket connection manager for broadcasting real-time updates.

    Handles:
    - Client connection/disconnection tracking
    - Broadcasting messages to all connected clients
    - Message formatting and encoding
    """

    MAX_CONNECTIONS = 150  # Hard cap — prevents reconnection storms from killing the server

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._viewer_sim = _ViewerSimulator()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        if len(self.active_connections) >= self.MAX_CONNECTIONS:
            await websocket.accept()
            await websocket.close(code=1013, reason="Server overloaded")
            logger.warning(f"WebSocket rejected — at cap ({self.MAX_CONNECTIONS})")
            return False
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
        return True

    async def register(self, websocket: WebSocket):
        """Register an already-accepted WebSocket connection."""
        async with self._lock:
            if websocket not in self.active_connections:
                self.active_connections.append(websocket)
        logger.info(f"WebSocket registered. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]):
        """
        Broadcast a message to all connected clients.

        Args:
            message: Dictionary to broadcast (will be JSON encoded)
        """
        if not self.active_connections:
            return

        # Encode message once
        try:
            encoded = json.dumps(message, cls=UUIDEncoder)
        except Exception as e:
            logger.error(f"Failed to encode message: {e}")
            return

        # Send to all connections, removing failed ones
        disconnected = []
        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_text(encoded)
                except Exception as e:
                    logger.warning(f"Failed to send to client: {e}")
                    disconnected.append(connection)

            # Clean up disconnected clients
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    async def broadcast_new_story(self, story_data: dict[str, Any]):
        """
        Broadcast a new story event to all clients.

        Args:
            story_data: Story data dictionary
        """
        message = {
            "type": "new_story",
            "channel": "feed",
            "event_type": "new_story",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": story_data,
        }
        await self.broadcast(message)
        logger.debug(f"Broadcasted new story: {story_data.get('title', 'Unknown')[:50]}")

    async def broadcast_cluster_update(self, cluster_data: dict[str, Any]):
        """
        Broadcast a cluster update event to all clients.

        Args:
            cluster_data: Cluster data dictionary
        """
        message = {
            "type": "cluster_update",
            "channel": "feed",
            "event_type": "cluster_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": cluster_data,
        }
        await self.broadcast(message)

    async def broadcast_kpi_update(self, kpi_data: dict[str, Any]):
        """
        Broadcast a KPI update event to all clients.

        Called when new stories/disasters are ingested to push fresh KPIs.

        Args:
            kpi_data: KPI snapshot data dictionary
        """
        message = {
            "type": "kpi_update",
            "channel": "system",
            "event_type": "kpi_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": kpi_data,
        }
        await self.broadcast(message)
        logger.debug("Broadcasted KPI update to clients")

    async def send_heartbeat(self):
        """Send heartbeat to all clients to keep connections alive."""
        self._viewer_sim.tick()
        message = {
            "type": "heartbeat",
            "channel": "system",
            "event_type": "heartbeat",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "viewers": self._viewer_sim.count,
        }
        await self.broadcast(message)

    async def broadcast_viewer_count(self):
        """Broadcast current viewer count to all clients."""
        message = {
            "type": "viewer_count",
            "channel": "system",
            "event_type": "viewer_count",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "viewers": self._viewer_sim.count,
        }
        await self.broadcast(message)

    def tick_viewers(self):
        """Advance the viewer simulator by one step."""
        self._viewer_sim.tick()

    @property
    def viewer_count(self) -> int:
        """Get simulated viewer count (same for all clients)."""
        return self._viewer_sim.count

    @property
    def connection_count(self) -> int:
        """Get current number of active connections."""
        return len(self.active_connections)


# Global connection manager instance
news_manager = ConnectionManager()
