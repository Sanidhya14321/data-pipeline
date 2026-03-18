"""Batch vectorizer worker consuming embedding jobs and writing to Qdrant."""

from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import structlog
from confluent_kafka import Consumer
from prometheus_client import Counter, Gauge, Histogram
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from config.settings import get_settings
from workers.self_healing import GracefulShutdown, retry_with_backoff

log = structlog.get_logger(__name__)
settings = get_settings()

pipeline_events_vectorized_total = Counter(
    "pipeline_events_vectorized_total",
    "Count of documents successfully vectorized and upserted.",
)

pipeline_embed_duration_seconds = Histogram(
    "pipeline_embed_duration_seconds",
    "Embedding generation duration in seconds.",
)

pipeline_qdrant_upsert_duration_seconds = Histogram(
    "pipeline_qdrant_upsert_duration_seconds",
    "Qdrant upsert duration in seconds.",
)

pipeline_vectorizer_batch_size = Gauge(
    "pipeline_vectorizer_batch_size",
    "Current vectorizer batch size.",
)


class Vectorizer:
    """Consume embedding jobs from Kafka and upsert vectors into Qdrant."""

    def __init__(self) -> None:
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self._qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_brokers,
                "group.id": "vectorizer-group",
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create pipeline_docs collection when missing."""
        collection_name = "pipeline_docs"
        existing = self._qdrant.get_collections().collections
        if any(collection.name == collection_name for collection in existing):
            return

        self._qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        log.info("vectorizer.collection_created", collection=collection_name)

    async def run(self) -> None:
        """Run batching loop with graceful shutdown and manual offset commits."""
        self._consumer.subscribe([settings.kafka_topic_embedding_jobs])

        batch: list[dict[str, Any]] = []
        msgs: list[Any] = []
        batch_started_at: float | None = None

        try:
            async with GracefulShutdown() as shutdown:
                while shutdown.running:
                    msg = self._consumer.poll(timeout=1.0)
                    now = time.monotonic()

                    if msg is not None:
                        if msg.error():
                            log.warning("vectorizer.kafka_error", error=str(msg.error()))
                            continue

                        try:
                            payload = json.loads(msg.value())
                        except json.JSONDecodeError as exc:
                            log.warning("vectorizer.invalid_job", error=str(exc))
                            self._consumer.commit(message=msg)
                            continue

                        text = payload.get("text")
                        if not isinstance(text, str) or not text.strip():
                            log.warning("vectorizer.job_missing_text")
                            self._consumer.commit(message=msg)
                            continue

                        if batch_started_at is None:
                            batch_started_at = now

                        batch.append(payload)
                        msgs.append(msg)

                    should_flush = False
                    if batch and len(batch) >= 32:
                        should_flush = True
                    elif batch and batch_started_at is not None and (now - batch_started_at) >= 5.0:
                        should_flush = True

                    if should_flush:
                        await self._process_batch(batch, msgs)
                        batch.clear()
                        msgs.clear()
                        batch_started_at = None

                if batch:
                    await self._process_batch(batch, msgs)
        finally:
            self._consumer.close()
            self._executor.shutdown(wait=True)

    async def _process_batch(self, batch: list[dict[str, Any]], msgs: list[Any]) -> None:
        """Embed a batch and upsert to Qdrant before committing offsets."""
        if not batch:
            return

        texts = [str(job["text"]) for job in batch]
        pipeline_vectorizer_batch_size.set(len(batch))

        with pipeline_embed_duration_seconds.time():
            loop = asyncio.get_running_loop()
            vectors = await loop.run_in_executor(
                self._executor,
                lambda: self._model.encode(
                    texts,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ).tolist(),
            )

        points: list[PointStruct] = []
        for job, vector in zip(batch, vectors):
            payload = job.get("metadata")
            if not isinstance(payload, dict):
                payload = {}

            points.append(
                PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload=payload,
                )
            )

        with pipeline_qdrant_upsert_duration_seconds.time():
            await self._upsert_with_retry(points)

        for msg in msgs:
            self._consumer.commit(message=msg)

        pipeline_events_vectorized_total.inc(len(batch))
        log.info("vectorizer.batch_processed", count=len(batch))

    @retry_with_backoff(max_retries=3)
    async def _upsert_with_retry(self, points: list[PointStruct]) -> None:
        """Upsert vectors to Qdrant with retry handling."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._qdrant.upsert(
                collection_name="pipeline_docs",
                points=points,
                wait=True,
            ),
        )


if __name__ == "__main__":
    asyncio.run(Vectorizer().run())
