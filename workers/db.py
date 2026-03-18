"""Async PostgreSQL access layer for ingestion workers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config.settings import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Return shared async SQLAlchemy engine.

    Returns
    -------
    AsyncEngine
        Singleton async engine configured for PostgreSQL.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            pool_pre_ping=True,
        )
    return _engine


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";

CREATE TABLE IF NOT EXISTS raw_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id TEXT UNIQUE,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    checksum TEXT,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_events_source_type ON raw_events(source_type);
CREATE INDEX IF NOT EXISTS idx_raw_events_ingested_at_desc ON raw_events(ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_events_checksum ON raw_events(checksum);

CREATE TABLE IF NOT EXISTS normalized_articles (
    id UUID PRIMARY KEY,
    pipeline_id TEXT UNIQUE,
    title TEXT,
    body TEXT,
    summary TEXT,
    source_url TEXT,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    published TIMESTAMPTZ,
    category TEXT,
    category_confidence REAL,
    entities JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_score REAL,
    tickers TEXT[],
    embedding_text TEXT,
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_norm_source ON normalized_articles(source);
CREATE INDEX IF NOT EXISTS idx_norm_category ON normalized_articles(category);
CREATE INDEX IF NOT EXISTS idx_norm_published_desc ON normalized_articles(published DESC);
CREATE INDEX IF NOT EXISTS idx_norm_tickers_gin ON normalized_articles USING GIN(tickers);

CREATE TABLE IF NOT EXISTS connector_state (
    source_id TEXT PRIMARY KEY,
    last_run TIMESTAMPTZ,
    last_success TIMESTAMPTZ,
    run_count INT NOT NULL DEFAULT 0,
    error_count INT NOT NULL DEFAULT 0,
    last_error TEXT
);
"""

SCHEMA_STATEMENTS = [
    statement.strip()
    for statement in SCHEMA_SQL.split(";")
    if statement.strip()
]


async def init_schema() -> None:
    """Create required tables and indexes if they do not already exist."""
    async with get_engine().begin() as conn:
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(text(statement))
    log.info("db.schema_initialized")


async def insert_normalized_article(data: dict) -> str:
    """Insert normalized article with idempotent conflict handling.

    Parameters
    ----------
    data : dict
        Normalized article payload.

    Returns
    -------
    str
        Inserted UUID string or existing provided id when conflict occurs.
    """
    article_id = str(data.get("id") or uuid4())
    pipeline_id = str(data.get("pipeline_id") or data.get("raw_event_id") or article_id)

    query = text(
        """
        INSERT INTO normalized_articles (
            id,
            pipeline_id,
            title,
            body,
            summary,
            source_url,
            source,
            source_type,
            published,
            category,
            category_confidence,
            entities,
            quality_score,
            tickers,
            embedding_text
        )
        VALUES (
            CAST(:id AS uuid),
            :pipeline_id,
            :title,
            :body,
            :summary,
            :source_url,
            :source,
            :source_type,
            :published,
            :category,
            :category_confidence,
            CAST(:entities AS jsonb),
            :quality_score,
            :tickers,
            :embedding_text
        )
        ON CONFLICT (pipeline_id) DO NOTHING
        RETURNING id
        """
    )

    params = {
        "id": article_id,
        "pipeline_id": pipeline_id,
        "title": data.get("title"),
        "body": data.get("body"),
        "summary": data.get("summary"),
        "source_url": data.get("source_url"),
        "source": data.get("source", ""),
        "source_type": data.get("source_type", ""),
        "published": data.get("published"),
        "category": data.get("category"),
        "category_confidence": data.get("category_confidence"),
        "entities": json.dumps(data.get("entities", {})),
        "quality_score": data.get("quality_score"),
        "tickers": data.get("tickers", []),
        "embedding_text": data.get("embedding_text"),
    }

    async with get_engine().begin() as conn:
        result = await conn.execute(query, params)
        row = result.fetchone()

    if row is None:
        return article_id
    return str(row[0])


async def update_connector_state(source_id: str, success: bool, error: str | None = None) -> None:
    """Upsert connector execution state.

    Parameters
    ----------
    source_id : str
        Connector source identifier.
    success : bool
        Whether the latest run succeeded.
    error : str | None, default=None
        Error message for failed runs.
    """
    now = datetime.now(timezone.utc)
    query = text(
        """
        INSERT INTO connector_state (
            source_id,
            last_run,
            last_success,
            run_count,
            error_count,
            last_error
        )
        VALUES (
            :source_id,
            :now,
            :last_success,
            1,
            :error_count,
            :last_error
        )
        ON CONFLICT (source_id) DO UPDATE SET
            last_run = :now,
            last_success = CASE WHEN :success THEN :now ELSE connector_state.last_success END,
            run_count = connector_state.run_count + 1,
            error_count = connector_state.error_count + :error_count,
            last_error = :last_error
        """
    )

    params = {
        "source_id": source_id,
        "now": now,
        "last_success": now if success else None,
        "error_count": 0 if success else 1,
        "last_error": None if success else error,
        "success": success,
    }

    async with get_engine().begin() as conn:
        await conn.execute(query, params)


async def get_pipeline_stats() -> dict[str, int]:
    """Return aggregate pipeline metrics from normalized articles.

    Returns
    -------
    dict[str, int]
        Dictionary with keys events_today, events_total, sources_active.
    """
    query = text(
        """
        SELECT
            COUNT(*) FILTER (WHERE normalized_at > now() - interval '24 hours') AS events_today,
            COUNT(*) AS events_total,
            COUNT(DISTINCT source) FILTER (WHERE normalized_at > now() - interval '24 hours')
                AS sources_active
        FROM normalized_articles
        """
    )

    async with get_engine().connect() as conn:
        result = await conn.execute(query)
        row = result.fetchone()

    if row is None:
        return {"events_today": 0, "events_total": 0, "sources_active": 0}

    mapping = row._mapping
    return {
        "events_today": int(mapping.get("events_today") or 0),
        "events_total": int(mapping.get("events_total") or 0),
        "sources_active": int(mapping.get("sources_active") or 0),
    }


async def get_connector_states() -> list[dict]:
    """Return all connector state rows ordered by most recent run."""
    query = text(
        """
        SELECT source_id, last_run, last_success, run_count, error_count, last_error
        FROM connector_state
        ORDER BY last_run DESC NULLS LAST
        """
    )

    async with get_engine().connect() as conn:
        result = await conn.execute(query)
        rows = result.fetchall()

    return [dict(row._mapping) for row in rows]
