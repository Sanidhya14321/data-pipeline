"""Semantic search endpoint backed by Qdrant vectors."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range
from sentence_transformers import SentenceTransformer

from config.settings import get_settings

router = APIRouter(tags=["search"])
log = structlog.get_logger(__name__)
settings = get_settings()

_executor = ThreadPoolExecutor(max_workers=2)
_model = SentenceTransformer("all-MiniLM-L6-v2")
_qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)


class SearchFilter(BaseModel):
    """Optional query filters for vector search."""

    source_type: list[str] | None = None
    category: list[str] | None = None
    tickers: list[str] | None = None
    date_after: str | None = None
    date_before: str | None = None


class SearchRequest(BaseModel):
    """Search request payload."""

    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(10, ge=1, le=50)
    filter: SearchFilter | None = None


class SearchResult(BaseModel):
    """Single search result record."""

    id: str
    title: str
    summary: str
    score: float
    source: str
    source_url: str
    published: str
    category: str
    source_type: str


class SearchResponse(BaseModel):
    """Search response payload."""

    results: list[SearchResult]
    total: int
    latency_ms: int


@router.post("/search", response_model=SearchResponse)
async def search_endpoint(
    payload: SearchRequest,
    x_pipeline_key: str | None = Header(default=None, alias="X-Pipeline-Key"),
) -> SearchResponse:
    """Run semantic vector search against Qdrant."""
    if not x_pipeline_key or x_pipeline_key != settings.pipeline_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    started = time.perf_counter()
    query_vector = await _embed_query(payload.query)
    qdrant_filter = _build_qdrant_filter(payload.filter)

    try:
        points = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: _qdrant.search(
                collection_name="pipeline_docs",
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=payload.top_k,
                with_payload=True,
            ),
        )
    except (UnexpectedResponse, Exception) as exc:
        log.error("search.qdrant_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="Search index unavailable") from exc

    results: list[SearchResult] = []
    for point in points:
        payload_map = point.payload or {}
        results.append(
            SearchResult(
                id=str(point.id),
                title=str(payload_map.get("title") or ""),
                summary=str(payload_map.get("summary") or ""),
                score=float(point.score),
                source=str(payload_map.get("source") or ""),
                source_url=str(payload_map.get("source_url") or ""),
                published=str(payload_map.get("published") or ""),
                category=str(payload_map.get("category") or ""),
                source_type=str(payload_map.get("source_type") or ""),
            )
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "search.query_executed",
        query=payload.query[:50],
        result_count=len(results),
        latency_ms=latency_ms,
    )

    return SearchResponse(results=results, total=len(results), latency_ms=latency_ms)


async def _embed_query(query: str) -> list[float]:
    """Embed query text in a thread pool to avoid blocking event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor,
        lambda: _model.encode(query, normalize_embeddings=True).tolist(),
    )


def _build_qdrant_filter(search_filter: SearchFilter | None) -> Filter | None:
    """Build Qdrant filter using FieldCondition, MatchValue, and Range."""
    if search_filter is None:
        return None

    must_conditions: list[Any] = []

    def _list_match_filter(key: str, values: list[str] | None) -> None:
        if not values:
            return
        should_conditions = [
            FieldCondition(key=key, match=MatchValue(value=value)) for value in values if value
        ]
        if should_conditions:
            must_conditions.append(Filter(should=should_conditions))

    _list_match_filter("source_type", search_filter.source_type)
    _list_match_filter("category", search_filter.category)
    _list_match_filter("tickers", search_filter.tickers)

    date_gte = _to_timestamp(search_filter.date_after)
    date_lte = _to_timestamp(search_filter.date_before)
    if date_gte is not None or date_lte is not None:
        must_conditions.append(
            FieldCondition(
                key="published_ts",
                range=Range(gte=date_gte, lte=date_lte),
            )
        )

    if not must_conditions:
        return None
    return Filter(must=must_conditions)


def _to_timestamp(value: str | None) -> float | None:
    """Convert ISO date string to unix timestamp, returning None on parse errors."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return None
