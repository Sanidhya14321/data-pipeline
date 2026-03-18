from __future__ import annotations

import asyncio
import json
import os
import time
from uuid import uuid4

import pytest
from confluent_kafka import Producer
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import text

from workers.db import get_engine

pytestmark = pytest.mark.integration


def _publish_raw_event(event_id: str) -> None:
    producer = Producer({"bootstrap.servers": os.getenv("KAFKA_BROKERS", "localhost:9092")})
    payload = {
        "pipeline_event_id": event_id,
        "title": f"Integration Apple Earnings {event_id}",
        "body": (
            "Apple reported record revenue and services growth while guiding for continued margin "
            "stability. Management highlighted demand trends across major geographies and product "
            "segments with strong cash generation."
        ),
        "source_url": "https://example.com/e2e",
        "source": "integration-test",
        "source_type": "api",
        "published": "2024-05-02T14:30:00+00:00",
    }
    producer.produce(os.getenv("KAFKA_TOPIC_RAW_EVENTS", "raw.events"), value=json.dumps(payload).encode())
    producer.flush()


@pytest.mark.asyncio
async def test_event_appears_in_postgres() -> None:
    event_id = f"e2e-{uuid4().hex[:10]}"
    _publish_raw_event(event_id)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        async with get_engine().connect() as conn:
            row = await conn.execute(
                text(
                    "SELECT pipeline_id FROM normalized_articles "
                    "WHERE pipeline_id = :pipeline_id LIMIT 1"
                ),
                {"pipeline_id": event_id},
            )
            found = row.fetchone()
            if found:
                return
        await asyncio.sleep(2)

    pytest.fail(f"Event {event_id} did not appear in PostgreSQL within 30s")


@pytest.mark.asyncio
async def test_event_appears_in_qdrant() -> None:
    event_id = f"e2e-{uuid4().hex[:10]}"
    _publish_raw_event(event_id)

    client = QdrantClient(
        url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY") or None,
    )

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        points, _ = client.scroll(
            collection_name=os.getenv("QDRANT_COLLECTION", "pipeline_docs"),
            scroll_filter=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value="integration-test"))]
            ),
            limit=10,
            with_payload=True,
            with_vectors=False,
        )
        if points:
            return
        await asyncio.sleep(2)

    pytest.fail("Vectorized event did not appear in Qdrant within 30s")


@pytest.mark.asyncio
async def test_semantic_search_finds_event() -> None:
    import httpx

    event_id = f"e2e-{uuid4().hex[:10]}"
    _publish_raw_event(event_id)

    deadline = time.monotonic() + 30
    async with httpx.AsyncClient(base_url="http://localhost:8080", timeout=10.0) as client:
        while time.monotonic() < deadline:
            response = await client.post(
                "/api/v1/search",
                headers={"X-Pipeline-Key": os.getenv("PIPELINE_API_KEY", "test-key")},
                json={"query": "Apple record revenue services growth", "top_k": 5},
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results and float(results[0].get("score", 0.0)) > 0.5:
                    return
            await asyncio.sleep(2)

    pytest.fail("Semantic search did not return a result with score > 0.5 within 30s")
