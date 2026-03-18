from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure required settings exist before importing modules that instantiate Settings at import time.
os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
os.environ.setdefault("KAFKA_SASL_MECHANISM", "PLAIN")
os.environ.setdefault("KAFKA_USERNAME", "test")
os.environ.setdefault("KAFKA_PASSWORD", "test")
os.environ.setdefault("KAFKA_TOPIC_RAW_EVENTS", "raw.events")
os.environ.setdefault("KAFKA_TOPIC_NORMALIZED_EVENTS", "normalized.events")
os.environ.setdefault("KAFKA_TOPIC_EMBEDDING_JOBS", "embedding.jobs")
os.environ.setdefault("KAFKA_TOPIC_DLQ", "dead.letter.queue")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("POSTGRES_POOL_MIN_SIZE", "1")
os.environ.setdefault("POSTGRES_POOL_MAX_SIZE", "2")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test-key")
os.environ.setdefault("QDRANT_COLLECTION", "pipeline_docs")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_DB", "0")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("GROQ_CLASSIFY_MODEL", "llama-3.1-8b-instant")
os.environ.setdefault("GROQ_EXTRACT_MODEL", "llama-3.3-70b-versatile")
os.environ.setdefault("LLM_REQUEST_TIMEOUT_SECONDS", "30")
os.environ.setdefault("NEWS_API_KEY", "test-key")
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("SEC_USER_AGENT", "TestCompany contact@test.com")
os.environ.setdefault("GITHUB_API_BASE_URL", "https://api.github.com")
os.environ.setdefault("COMPOSIO_API_KEY", "test-key")
os.environ.setdefault("COMPOSIO_WEBHOOK_SECRET", "test-key")
os.environ.setdefault("PIPELINE_API_KEY", "test-key")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("APP_HOST", "0.0.0.0")
os.environ.setdefault("APP_PORT", "8080")
os.environ.setdefault("METRICS_PORT", "9090")

from connectors.base_connector import RawEvent


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_raw_event() -> RawEvent:
    return RawEvent(
        id="apple-q2-2024",
        title="Apple Reports Record Q2 Revenue of $110 Billion",
        body=(
            "Apple reported quarterly revenue of $110 billion, with iPhone and Services growth "
            "driving upside versus expectations. Management highlighted margin expansion, stronger "
            "cash flow, and continued demand in key regions while flagging supply-chain and FX risks."
        ),
        source_url="https://www.reuters.com/world/us/apple-q2-2024",
        source="reuters-world-rss",
        source_type="rss",
        published=datetime(2024, 5, 2, 14, 30, tzinfo=timezone.utc),
        raw_payload={"provider": "reuters"},
        metadata={"category_hint": "earnings"},
    )


@pytest.fixture
def sample_normalized_event() -> dict:
    return {
        "id": "norm-123",
        "raw_event_id": "raw-123",
        "title": "Apple Reports Record Q2 Revenue of $110 Billion",
        "body": "Apple posted strong earnings and services growth across major markets.",
        "summary": "Apple posted record quarterly revenue and highlighted services momentum.",
        "source_url": "https://www.reuters.com/world/us/apple-q2-2024",
        "source": "reuters-world-rss",
        "source_type": "rss",
        "published": "2024-05-02T14:30:00+00:00",
        "category": "EARNINGS",
        "category_confidence": 0.97,
        "entities": {
            "companies": [{"name": "Apple", "ticker": "AAPL", "exchange": "NASDAQ"}],
            "people": ["Tim Cook"],
            "amounts": ["110000000000"],
            "dates": ["2024-05-02"],
        },
        "quality_score": 9,
        "embedding_text": (
            "Apple Reports Record Q2 Revenue of $110 Billion\n\n"
            "Apple posted record quarterly revenue and highlighted services momentum."
        ),
        "normalized_at": "2024-05-02T14:31:00+00:00",
        "tickers": ["AAPL"],
    }


@pytest.fixture
def mock_rss_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>Apple Beats Q2 Expectations</title>
      <link>https://example.com/apple-q2</link>
      <description>Apple revenue reached new highs with strong services growth.</description>
      <pubDate>Thu, 02 May 2024 14:30:00 GMT</pubDate>
      <guid>apple-q2-2024</guid>
    </item>
    <item>
      <title>Microsoft Cloud Growth Accelerates</title>
      <link>https://example.com/msft-cloud</link>
      <description>Azure growth remained resilient in enterprise segments.</description>
      <pubDate>Fri, 03 May 2024 12:00:00 GMT</pubDate>
      <guid>msft-cloud-2024</guid>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def mock_groq() -> AsyncMock:
    client = AsyncMock()
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                text='{"category":"EARNINGS","confidence":0.96,"reason":"quarterly results"}'
            )
        ]
    )
    client.messages.create = AsyncMock(return_value=response)
    return client


@pytest.fixture
def mock_redis() -> MagicMock:
    client = MagicMock()
    client.set = MagicMock(side_effect=[True, False])
    return client


@pytest.fixture
def mock_qdrant() -> MagicMock:
    client = MagicMock()
    result = MagicMock()
    result.id = "point-1"
    result.score = 0.92
    result.payload = {
        "id": "norm-123",
        "title": "Apple Reports Record Q2 Revenue of $110 Billion",
        "summary": "Apple beat expectations.",
        "source": "reuters-world-rss",
        "source_url": "https://example.com/apple-q2",
        "published": "2024-05-02T14:30:00+00:00",
        "category": "EARNINGS",
        "source_type": "rss",
    }
    client.search = MagicMock(return_value=[result])
    return client


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    producer = MagicMock()
    producer.produce = MagicMock()
    producer.flush = MagicMock(return_value=0)
    producer.poll = MagicMock(return_value=0)
    return producer
