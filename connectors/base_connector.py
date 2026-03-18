"""Abstract base connector with deduplication, metrics, and Kafka publishing."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4

import structlog
from confluent_kafka import Producer
from prometheus_client import Counter, Histogram

from config.settings import get_settings
from workers.dedup import is_duplicate
from workers.self_healing import CircuitBreaker

log = structlog.get_logger(__name__)
settings = get_settings()

events_ingested_total = Counter(
    "events_ingested_total",
    "Total events ingested by connectors.",
    ["source", "source_type"],
)

connector_errors_total = Counter(
    "connector_errors_total",
    "Total connector errors.",
    ["source", "error_type"],
)

fetch_duration = Histogram(
    "fetch_duration_seconds",
    "Connector fetch duration in seconds.",
    ["source"],
)


@dataclass(slots=True)
class RawEvent:
    """Canonical raw event schema entering the ingestion pipeline.

    Parameters
    ----------
    id : str
        Stable source-side identifier for the event.
    title : str
        Human-readable event title.
    body : str
        Full normalized event body content.
    source_url : str
        Canonical source URL.
    source : str
        Source identifier matching the configured connector.
    source_type : str
        Source category (rss, api, sec, github, scrape, etc.).
    published : datetime
        Publication timestamp. Naive values are interpreted as UTC.
    raw_payload : dict[str, Any], optional
        Original source payload for debugging and traceability.
    metadata : dict[str, Any], optional
        Connector-specific metadata.
    """

    id: str
    title: str
    body: str
    source_url: str
    source: str
    source_type: str
    published: datetime
    raw_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.published.tzinfo is None:
            self.published = self.published.replace(tzinfo=timezone.utc)
        else:
            self.published = self.published.astimezone(timezone.utc)

    @property
    def checksum(self) -> str:
        """Return SHA-256 of {title.strip()}{date[:10]}{source}."""
        date_yyyy_mm_dd = self.published.isoformat()[:10]
        token = f"{self.title.strip()}{date_yyyy_mm_dd}{self.source}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def to_kafka_payload(self) -> bytes:
        """Serialize event as Kafka payload bytes with ingestion metadata."""
        payload = asdict(self)
        payload["published"] = self.published.isoformat()
        payload["checksum"] = self.checksum
        payload["ingested_at"] = datetime.now(tz=timezone.utc).isoformat()
        payload["pipeline_event_id"] = str(uuid4())
        return json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")


class BaseConnector(ABC):
    """Abstract connector base class with deduplication and resilient publishing."""

    def __init__(self) -> None:
        self._producer: Producer | None = None
        self._circuit_breaker = CircuitBreaker(name=self.source_id)

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Return unique connector source identifier."""

    @abstractmethod
    async def _fetch_raw(self) -> AsyncIterator[RawEvent]:
        """Yield raw events from the underlying data source."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True when the source dependency is healthy."""

    async def fetch(self) -> AsyncIterator[RawEvent]:
        """Yield deduplicated events while recording source metrics."""
        with fetch_duration.labels(source=self.source_id).time():
            try:
                if not self._circuit_breaker.is_available():
                    log.warning("connector.circuit_open", source=self.source_id)
                    return

                async for event in self._fetch_raw():
                    if is_duplicate(event.checksum):
                        log.debug(
                            "connector.event_duplicate",
                            source=self.source_id,
                            checksum=event.checksum,
                        )
                        continue

                    events_ingested_total.labels(
                        source=self.source_id,
                        source_type=event.source_type,
                    ).inc()
                    self._circuit_breaker.record_success()
                    yield event
            except Exception as exc:
                self._circuit_breaker.record_failure()
                connector_errors_total.labels(
                    source=self.source_id,
                    error_type=type(exc).__name__,
                ).inc()
                log.error(
                    "connector.fetch_failed",
                    source=self.source_id,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                raise

    async def run_once(self) -> int:
        """Fetch and publish one full batch, returning number of published events."""
        count = 0
        async for event in self.fetch():
            await self._publish_to_kafka(event)
            count += 1

        self.flush_kafka()
        log.info("connector.run_once_complete", source=self.source_id, published=count)
        return count

    async def _publish_to_kafka(self, event: RawEvent) -> None:
        """Publish one event to Kafka using idempotent producer settings."""
        if self._producer is None:
            self._producer = Producer(
                {
                    "bootstrap.servers": settings.kafka_brokers,
                    "enable.idempotence": True,
                    "acks": "all",
                }
            )

        topic = settings.kafka_topic_raw_events
        self._producer.produce(
            topic=topic,
            key=event.checksum.encode("utf-8"),
            value=event.to_kafka_payload(),
            on_delivery=self._on_delivery,
        )
        self._producer.poll(0)

    @staticmethod
    def _on_delivery(err: Any, msg: Any) -> None:
        """Handle asynchronous Kafka delivery callbacks."""
        if err is not None:
            log.error("connector.kafka_delivery_failed", error=str(err))
            return
        log.debug(
            "connector.kafka_delivered",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
        )

    def flush_kafka(self) -> None:
        """Flush buffered Kafka messages synchronously."""
        if self._producer is not None:
            self._producer.flush(10)
