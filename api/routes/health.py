"""Health and readiness endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import redis
import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from config.settings import get_settings
from workers.db import get_engine

router = APIRouter(tags=["health"])
log = structlog.get_logger(__name__)
settings = get_settings()


@router.get("/health")
async def health() -> JSONResponse:
    """Return component health status."""
    postgres_task = asyncio.wait_for(_check_postgres(), timeout=3.0)
    qdrant_task = asyncio.wait_for(_check_qdrant(), timeout=3.0)
    redis_task = asyncio.wait_for(_check_redis(), timeout=3.0)

    checks = await asyncio.gather(postgres_task, qdrant_task, redis_task, return_exceptions=True)

    postgres_status = checks[0] if isinstance(checks[0], str) else "degraded"
    qdrant_status = checks[1] if isinstance(checks[1], str) else "degraded"
    redis_status = checks[2] if isinstance(checks[2], str) else "degraded"

    status = "ok" if all(item == "ok" for item in [postgres_status, qdrant_status, redis_status]) else "degraded"
    body = {
        "status": status,
        "checks": {
            "postgres": postgres_status,
            "qdrant": qdrant_status,
            "redis": redis_status,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    status_code = 200 if status == "ok" else 503
    return JSONResponse(status_code=status_code, content=body)


@router.get("/ready")
async def ready() -> dict[str, bool]:
    """Kubernetes readiness probe endpoint."""
    return {"ready": True}


async def _check_postgres() -> str:
    """Check PostgreSQL connectivity."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        log.warning("health.postgres_failed", error=str(exc))
        return "degraded"


async def _check_qdrant() -> str:
    """Check Qdrant connectivity."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        await asyncio.get_running_loop().run_in_executor(None, client.get_collections)
        return "ok"
    except Exception as exc:
        log.warning("health.qdrant_failed", error=str(exc))
        return "degraded"


async def _check_redis() -> str:
    """Check Redis connectivity."""
    try:
        client = redis.Redis.from_url(settings.redis_url)
        await asyncio.get_running_loop().run_in_executor(None, client.ping)
        return "ok"
    except Exception as exc:
        log.warning("health.redis_failed", error=str(exc))
        return "degraded"
