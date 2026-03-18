"""Faust stream processing worker for raw event normalization."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bleach
import faust
import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka import AIOKafkaProducer
from groq import AsyncGroq
from prometheus_client import Counter, Histogram, start_http_server

from config.settings import get_settings
from workers.db import init_schema, insert_normalized_article
from workers.dedup import is_duplicate
from workers.prompts import get_prompt

log = structlog.get_logger(__name__)
settings = get_settings()

MODEL_HAIKU = settings.groq_classify_model
MODEL_SONNET = settings.groq_extract_model

pipeline_events_normalized_total = Counter(
    "pipeline_events_normalized_total",
    "Count of events successfully normalized.",
)

pipeline_events_dlq_total = Counter(
    "pipeline_events_dlq_total",
    "Count of events sent to DLQ.",
    ["reason"],
)

pipeline_normalize_duration_seconds = Histogram(
    "pipeline_normalize_duration_seconds",
    "End-to-end normalization duration per event in seconds.",
)

pipeline_llm_calls_total = Counter(
    "pipeline_llm_calls_total",
    "Count of LLM calls by prompt type.",
    ["prompt_type"],
)


def _patch_aiokafka_producer_init() -> None:
    """Make faust producer init compatible with aiokafka under local runtime."""
    original_init = AIOKafkaProducer.__init__

    if getattr(original_init, "_pipeline_api_version_patch", False):
        return

    def patched_init(self, *args, **kwargs):
        kwargs.pop("api_version", None)
        return original_init(self, *args, **kwargs)

    setattr(patched_init, "_pipeline_api_version_patch", True)
    AIOKafkaProducer.__init__ = patched_init


_patch_aiokafka_producer_init()


def _patch_aiokafka_consumer_init() -> None:
    """Make faust consumer init compatible with aiokafka under local runtime."""
    original_init = AIOKafkaConsumer.__init__

    if getattr(original_init, "_pipeline_api_version_patch", False):
        return

    def patched_init(self, *args, **kwargs):
        kwargs.pop("api_version", None)
        return original_init(self, *args, **kwargs)

    setattr(patched_init, "_pipeline_api_version_patch", True)
    AIOKafkaConsumer.__init__ = patched_init


_patch_aiokafka_consumer_init()

app = faust.App(
    "normalizer",
    broker=f"kafka://{settings.kafka_brokers}",
    consumer_auto_offset_reset="earliest",
    producer_acks=-1,
)

raw_topic = app.topic(settings.kafka_topic_raw_events, value_type=bytes)
normalized_topic = app.topic(settings.kafka_topic_normalized_events, value_type=bytes)
embedding_topic = app.topic(settings.kafka_topic_embedding_jobs, value_type=bytes)
dlq_topic = app.topic(settings.kafka_topic_dlq, value_type=bytes)

_groq_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    """Return a shared Groq async client."""
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.groq_api_key)
    return _groq_client


@app.agent(raw_topic, concurrency=4)
async def normalize(stream: faust.StreamT[bytes]) -> None:
    """Normalize raw events and publish enriched records downstream."""
    async for message in stream:
        with pipeline_normalize_duration_seconds.time():
            await _process_message(message)


async def _process_message(message: bytes) -> None:
    """Run the exact 10-step normalization pipeline for one Kafka message."""
    # Step 1: JSON parse (-> DLQ if invalid_json)
    try:
        raw = json.loads(message)
    except json.JSONDecodeError as exc:
        await _send_dlq(message, reason="invalid_json", error=str(exc))
        return

    # Step 2: Validate title + published exist (-> DLQ if schema_validation_failed)
    title = str(raw.get("title") or "").strip()
    published = raw.get("published")
    if not title or not published:
        await _send_dlq(raw, reason="schema_validation_failed", error="missing title or published")
        return

    # Step 3: Dedup check via is_duplicate() (skip silently if duplicate, no DLQ)
    checksum = str(raw.get("checksum") or _compute_checksum(raw))
    if is_duplicate(checksum):
        return

    # Step 4: HTML clean + word count >= 30 (-> DLQ if content_too_short)
    raw_body = str(raw.get("body") or raw.get("content") or raw.get("summary") or "")
    clean_body = _clean_html(raw_body)
    if len(clean_body.split()) < 30:
        await _send_dlq(raw, reason="content_too_short", error="body has fewer than 30 words")
        return

    # Step 5: Quality gate LLM (-> DLQ if low_quality)
    quality = await _llm_call(
        prompt_type="quality",
        model=MODEL_HAIKU,
        title=title,
        body_preview=clean_body[:600],
    )
    quality_pass = bool(quality.get("pass", False))
    quality_score = int(quality.get("score", 0)) if isinstance(quality, dict) else 0
    if not quality_pass:
        await _send_dlq(raw, reason="low_quality", error=str(quality.get("reason", "llm rejected")))
        return

    # Step 6: Classification LLM (-> DLQ if IRRELEVANT)
    classification = await _llm_call(
        prompt_type="classify",
        model=MODEL_HAIKU,
        title=title,
        source=str(raw.get("source") or "unknown"),
        body_preview=clean_body[:600],
    )
    category = str(classification.get("category") or "IRRELEVANT").upper()
    category_confidence = float(classification.get("confidence") or 0.0)
    if category == "IRRELEVANT":
        await _send_dlq(raw, reason="IRRELEVANT", error=str(classification.get("reason", "irrelevant")))
        return

    # Step 7: Entity extraction LLM
    entities = await _llm_call(
        prompt_type="extract",
        model=MODEL_SONNET,
        text=clean_body[:8000],
    )
    if not isinstance(entities, dict):
        entities = {}

    # Step 8: Summarization LLM
    summary_result = await _llm_call(
        prompt_type="summarize",
        model=MODEL_SONNET,
        title=title,
        body=clean_body[:10000],
    )
    summary = str(summary_result.get("summary") or "").strip() if isinstance(summary_result, dict) else ""
    if not summary:
        summary = clean_body[:800]

    normalized_id = str(uuid4())
    ticker_list: list[str] = []
    companies = entities.get("companies", []) if isinstance(entities, dict) else []
    if isinstance(companies, list):
        for company in companies:
            if isinstance(company, dict):
                ticker = company.get("ticker")
                if isinstance(ticker, str) and ticker.strip():
                    ticker_list.append(ticker.strip().upper())

    # Build required normalized event payload
    normalized_event = {
        "id": normalized_id,
        "raw_event_id": str(raw.get("pipeline_event_id") or raw.get("id") or normalized_id),
        "title": title,
        "body": clean_body[:10000],
        "summary": summary,
        "source_url": str(raw.get("source_url") or ""),
        "source": str(raw.get("source") or "unknown"),
        "source_type": str(raw.get("source_type") or "unknown"),
        "published": str(published),
        "category": category,
        "category_confidence": category_confidence,
        "entities": entities,
        "quality_score": quality_score,
        "embedding_text": f"{title}\n\n{summary}",
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "tickers": ticker_list,
    }

    # Step 9: Write to PostgreSQL via insert_normalized_article() (-> DLQ if db_write_failed)
    try:
        await insert_normalized_article(normalized_event)
    except Exception as exc:
        await _send_dlq(raw, reason="db_write_failed", error=str(exc))
        return

    # Step 10: Publish to normalized.events AND embedding.jobs topics
    normalized_bytes = json.dumps(normalized_event).encode("utf-8")
    embedding_job = {
        "id": normalized_event["id"],
        "raw_event_id": normalized_event["raw_event_id"],
        "text": normalized_event["embedding_text"],
        "metadata": {
            "source": normalized_event["source"],
            "source_type": normalized_event["source_type"],
            "category": normalized_event["category"],
            "published": normalized_event["published"],
            "source_url": normalized_event["source_url"],
            "title": normalized_event["title"],
            "tickers": normalized_event["tickers"],
        },
    }
    await normalized_topic.send(value=normalized_bytes)
    await embedding_topic.send(value=json.dumps(embedding_job).encode("utf-8"))
    pipeline_events_normalized_total.inc()


async def _llm_call(prompt_type: str, model: str, **kwargs: Any) -> dict[str, Any]:
    """Call Groq with timeout and one retry, returning {} on final failure."""
    system_prompt, user_template = get_prompt(prompt_type)
    user_text = user_template.format(**kwargs)

    for attempt in range(2):
        pipeline_llm_calls_total.labels(prompt_type=prompt_type).inc()
        try:
            response = await asyncio.wait_for(
                _get_client().chat.completions.create(
                    model=model,
                    max_tokens=600,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text},
                    ],
                ),
                timeout=15.0,
            )
            text_out = response.choices[0].message.content or ""
            parsed = _safe_json_parse(text_out.strip())
            if isinstance(parsed, dict):
                return parsed
            raise ValueError("LLM response was not a JSON object")
        except Exception as exc:
            log.warning(
                "normalizer.llm_call_failed",
                prompt_type=prompt_type,
                model=model,
                attempt=attempt + 1,
                error=str(exc),
            )
            if attempt == 0:
                await asyncio.sleep(2)

    return {}


def _clean_html(raw: str) -> str:
    """Strip HTML, collapse whitespace, and cap content length."""
    cleaned = bleach.clean(raw, tags=[], strip=True)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:10000]


async def _send_dlq(original: bytes | dict[str, Any], reason: str, error: str = "") -> None:
    """Publish failed messages to DLQ and increment DLQ metrics."""
    if isinstance(original, bytes):
        original_message = original.decode("utf-8", errors="replace")
    else:
        original_message = json.dumps(original, default=str)

    payload = {
        "original_message": original_message,
        "reason": reason,
        "error": error,
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "retry_count": 0,
    }
    await dlq_topic.send(value=json.dumps(payload).encode("utf-8"))
    pipeline_events_dlq_total.labels(reason=reason).inc()


def _safe_json_parse(raw_text: str) -> Any:
    """Parse strict JSON with lightweight code-fence stripping fallback."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    return json.loads(text)


def _compute_checksum(raw: dict[str, Any]) -> str:
    """Compute fallback checksum when source payload did not include one."""
    title = str(raw.get("title") or "").strip()
    source = str(raw.get("source") or "")
    published = str(raw.get("published") or "")
    token = f"{title}{published[:10]}{source}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@app.task
async def on_start() -> None:
    """Start Prometheus endpoint on worker startup."""
    await init_schema()
    start_http_server(settings.prometheus_port)
    log.info("normalizer.startup", prometheus_port=settings.prometheus_port)


if __name__ == "__main__":
    app.main()
