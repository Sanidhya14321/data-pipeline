"""Fallback search path powered by Groq plus lightweight web scraping."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import aiohttp
import feedparser
import structlog
from groq import AsyncGroq

from config.settings import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

_groq_client: AsyncGroq | None = None


class FallbackResult(dict):
    """Dictionary wrapper for fallback result rows."""


def _get_groq_client() -> AsyncGroq:
    """Return shared Groq client for fallback prompts."""
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.groq_api_key)
    return _groq_client


async def fallback_web_search(query: str, top_k: int) -> list[FallbackResult]:
    """Run fallback discovery by rewriting query with Groq and scraping web pages."""
    rewritten_query = await _rewrite_query(query)
    rss_url = f"https://news.google.com/rss/search?q={quote_plus(rewritten_query)}"

    feed = await asyncio.get_running_loop().run_in_executor(None, feedparser.parse, rss_url)
    entries = list(feed.entries or [])[: max(top_k * 3, 10)]
    if not entries:
        return []

    connector = aiohttp.TCPConnector(limit=6)
    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        scraped = await asyncio.gather(
            *[_build_result_from_entry(session, entry, idx) for idx, entry in enumerate(entries)],
            return_exceptions=True,
        )

    results: list[FallbackResult] = []
    for item in scraped:
        if isinstance(item, dict):
            results.append(FallbackResult(item))

    return results[:top_k]


async def _build_result_from_entry(
    session: aiohttp.ClientSession,
    entry: Any,
    position: int,
) -> dict[str, Any] | None:
    """Fetch article and shape a fallback search item."""
    link = str(getattr(entry, "link", "") or "")
    title = str(getattr(entry, "title", "") or "").strip()
    published = str(getattr(entry, "published", "") or "")

    if not link or not title:
        return None

    raw_summary = str(getattr(entry, "summary", "") or "")
    summary_seed = _clean_text(raw_summary)

    body_text = await _fetch_page_text(session, link)
    source_text = body_text if body_text else summary_seed
    summary = await _summarize_article(title=title, body=source_text)

    source_name = "web"
    source_meta = getattr(entry, "source", None)
    if source_meta and isinstance(source_meta, dict):
        source_name = str(source_meta.get("title") or "web")

    return {
        "id": f"fallback-{position}-{abs(hash(link))}",
        "title": title,
        "summary": summary or summary_seed[:600],
        "score": max(0.25, 1.0 - (position * 0.04)),
        "source": source_name,
        "source_url": link,
        "published": _normalize_published(published),
        "category": "WEB_FALLBACK",
        "source_type": "fallback_scrape",
    }


async def _fetch_page_text(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch and strip article page to plain text."""
    try:
        async with session.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DataPipelineBot/1.0)"},
            allow_redirects=True,
        ) as response:
            if response.status >= 400:
                return ""
            html = await response.text(errors="ignore")
    except Exception as exc:
        log.debug("fallback.fetch_failed", url=url, error=str(exc))
        return ""

    # Keep extraction lightweight to avoid adding large parser dependencies.
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", html)
    text = re.sub(r"(?is)<[^>]+>", " ", html)
    return _clean_text(text)[:6000]


async def _rewrite_query(query: str) -> str:
    """Use Groq to rewrite user query for better open-web recall."""
    system = (
        "You rewrite search queries for financial and technical news retrieval. "
        "Return strict JSON only with shape {\"query\":\"...\"}."
    )

    user = (
        "Original query: "
        f"{query}\n"
        "Create one concise query string with important entities and keywords."
    )

    parsed = await _call_groq_json(system=system, user=user, max_tokens=120)
    rewritten = str(parsed.get("query") or "").strip()
    return rewritten or query


async def _summarize_article(title: str, body: str) -> str:
    """Use Groq to produce a compact summary for fallback results."""
    if not body:
        return ""

    system = (
        "You summarize web articles for search results. "
        "Return strict JSON only with shape {\"summary\":\"...\"}."
    )
    user = (
        f"Title: {title}\n"
        f"Body: {body[:3500]}\n"
        "Write a factual summary in 2-3 sentences, include named entities and numbers."
    )

    parsed = await _call_groq_json(system=system, user=user, max_tokens=220)
    return str(parsed.get("summary") or "").strip()


async def _call_groq_json(system: str, user: str, max_tokens: int) -> dict[str, Any]:
    """Call Groq once with timeout and return parsed JSON payload."""
    try:
        response = await asyncio.wait_for(
            _get_groq_client().chat.completions.create(
                model=settings.groq_extract_model,
                temperature=0,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            ),
            timeout=12,
        )
    except Exception as exc:
        log.warning("fallback.groq_call_failed", error=str(exc))
        return {}

    text_out = response.choices[0].message.content or ""
    return _safe_json_parse(text_out)


def _safe_json_parse(payload: str) -> dict[str, Any]:
    """Parse JSON and tolerate fenced blocks from model output."""
    raw = payload.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        parsed = json.loads(raw.strip())
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean_text(text: str) -> str:
    """Normalize whitespace and decode escaped entities."""
    cleaned = unescape(text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _normalize_published(value: str) -> str:
    """Normalize published date fallback to current UTC ISO timestamp."""
    if value.strip():
        return value.strip()
    return datetime.utcnow().isoformat() + "Z"
