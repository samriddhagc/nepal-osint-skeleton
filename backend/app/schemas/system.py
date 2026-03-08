"""Pydantic schemas for system health and API monitoring endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Component Health ──

class ComponentHealth(BaseModel):
    """Health status of a single system component."""
    status: str  # healthy, degraded, down
    details: dict = {}


class DatabaseHealth(ComponentHealth):
    """Database-specific health info."""
    pool_size: int = 0
    active_connections: int = 0
    waiting: int = 0
    latency_ms: float = 0


class RedisHealth(ComponentHealth):
    """Redis-specific health info."""
    memory_used: str = "0MB"
    memory_peak: str = "0MB"
    connected_clients: int = 0
    keys: int = 0


class WorkerHealth(ComponentHealth):
    """Worker-specific health info."""
    active_tasks: int = 0
    queued_tasks: int = 0
    failed_24h: int = 0


class QueueHealth(ComponentHealth):
    """Queue-specific health info."""
    ingestion_depth: int = 0
    processing_depth: int = 0
    alert_depth: int = 0


# ── System Status ──

class SystemStatusResponse(BaseModel):
    """Full system health response."""
    database: DatabaseHealth
    redis: RedisHealth
    workers: WorkerHealth
    queues: QueueHealth
    uptime_seconds: int = 0
    version: str = "5.0.0"
    environment: str = "development"
    last_deployment: Optional[str] = None


# ── API Metrics ──

class EndpointMetric(BaseModel):
    """Metrics for a single API endpoint."""
    path: str
    method: str
    count: int
    avg_ms: float
    p95_ms: float = 0
    errors: int = 0


class ApiMetricsResponse(BaseModel):
    """Aggregated API metrics."""
    request_count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    avg_response_ms: float = 0
    p95_response_ms: float = 0
    p99_response_ms: float = 0
    endpoints: list[EndpointMetric] = []
    period: str = "24h"
