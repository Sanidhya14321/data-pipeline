"""NewsAPI connector implementation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import aiohttp
import structlog

from config.settings import get_settings
from connectors.base_connector import BaseConnector, RawEvent

log = structlog.get_logger(__name__)
settings = get_settings()


class NewsAPIConnector(BaseConnector):
    """Fetch news articles from NewsAPI.

    Parameters
    ----------
    source_id : str
        Source identifier from configuration.
    query : str
        Query passed to NewsAPI everything endpoint.
    language : str, default="en"
        Language filter.
    lookback_hours : int, default=2
        Lookback window for recent articles.
    """

    BASE_URL = "https://newsapi.org/v2"

    def __init__(
        self,
        source_id: str,
        query: str,
        language: str = "en",
        lookback_hours: int = 2,
    ) -> None:
        self._source_id = source_id
        self._query = query
        self._language = language
        self._lookback_hours = lookback_hours
        super().__init__()

    @property
    def source_id(self) -> str:
        """Return connector source identifier."""
        return self._source_id

    async def _fetch_raw(self) -> AsyncIterator[RawEvent]:
        """Fetch recent articles from NewsAPI everything endpoint."""
        from_timestamp = (datetime.now(timezone.utc) - timedelta(hours=self._lookback_hours)).isoformat()
        params = {
            "q": self._query,
            "language": self._language,
            "sortBy": "publishedAt",
            "from": from_timestamp,
            "pageSize": 100,
            "apiKey": settings.news_api_key,
        }

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.BASE_URL}/everything", params=params) as response:
                if response.status == 429:
                    raise RuntimeError("rate limit")
                response.raise_for_status()
                payload = await response.json()

        if payload.get("status") != "ok":
            raise RuntimeError(f"newsapi error: {payload.get('status')}")

        for article in payload.get("articles", []):
            title = article.get("title")
            if title is None or title.strip() == "[Removed]":
                continue

            published = self._parse_published(article.get("publishedAt"))
            description = (article.get("description") or "").strip()
            content = (article.get("content") or "").strip()
            body = "\n\n".join(part for part in [description, content] if part)

            source_url = (article.get("url") or "").strip()
            if not source_url:
                continue

            source_obj = article.get("source") or {}
            external_id = source_url
            if article.get("urlToImage"):
                external_id = f"{source_url}#{article.get('publishedAt', '')}"

            yield RawEvent(
                id=external_id,
                title=title.strip(),
                body=body,
                source_url=source_url,
                source=self.source_id,
                source_type="api",
                published=published,
                raw_payload=article,
                metadata={
                    "provider": "newsapi",
                    "query": self._query,
                    "author": article.get("author"),
                    "source_name": source_obj.get("name"),
                },
            )

    async def health_check(self) -> bool:
        """Return True if NewsAPI top-headlines endpoint responds with ok status."""
        params = {
            "country": "us",
            "pageSize": 1,
            "apiKey": settings.news_api_key,
        }
        timeout = aiohttp.ClientTimeout(total=10)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.BASE_URL}/top-headlines", params=params) as response:
                    if response.status != 200:
                        return False
                    payload = await response.json()
                    return payload.get("status") == "ok"
        except aiohttp.ClientError:
            return False

    @staticmethod
    def _parse_published(value: str | None) -> datetime:
        """Parse publishedAt timestamp with fallback to current UTC time."""
        if not value:
            return datetime.now(timezone.utc)

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
