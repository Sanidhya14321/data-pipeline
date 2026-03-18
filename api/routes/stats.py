"""Pipeline stats endpoint."""

from __future__ import annotations

from fastapi import APIRouter
import structlog

from workers.db import get_connector_states, get_pipeline_stats

router = APIRouter(tags=["stats"])
log = structlog.get_logger(__name__)


@router.get("/stats")
async def stats() -> dict:
    """Return aggregate pipeline statistics and connector states."""
    try:
        aggregates = await get_pipeline_stats()
        connectors = await get_connector_states()
    except Exception as exc:
        log.warning("stats.backend_unavailable", error=str(exc))
        return {
            "events_today": 0,
            "events_total": 0,
            "sources_active": 0,
            "connectors": [],
            "status": "degraded",
        }

    return {
        "events_today": aggregates.get("events_today", 0),
        "events_total": aggregates.get("events_total", 0),
        "sources_active": aggregates.get("sources_active", 0),
        "connectors": connectors,
        "status": "ok",
    }
