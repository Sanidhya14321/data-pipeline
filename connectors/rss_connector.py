"""RSS connector implementation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import struct_time
from typing import Any, AsyncIterator

import aiohttp
import feedparser
import structlog

from connectors.base_connector import BaseConnector, RawEvent

log = structlog.get_logger(__name__)


class RSSConnector(BaseConnector):
    """Fetch events from an RSS/Atom feed.

    Parameters
    ----------
    source_id : str
        Source identifier from configuration.
    url : str
        RSS/Atom feed URL.
    timeout : int, default=15
        HTTP timeout in seconds.
    """

    USER_AGENT = "DataPipeline/1.0"

    def __init__(self, source_id: str, url: str, timeout: int = 15) -> None:
        self._source_id = source_id
        self._url = url
        self._timeout = timeout
        super().__init__()

    @property
    def source_id(self) -> str:
        """Return connector source identifier."""
        return self._source_id

    async def _fetch_raw(self) -> AsyncIterator[RawEvent]:
        """Fetch and parse RSS entries without blocking the event loop."""
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        headers = {"User-Agent": self.USER_AGENT}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(self._url) as response:
                response.raise_for_status()
                xml_text = await response.text()

        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, xml_text)

        for entry in getattr(feed, "entries", []):
            event = self._parse_entry(entry)
            if event is not None:
                yield event

    def _parse_entry(self, entry: Any) -> RawEvent | None:
        """Parse one feed entry into a RawEvent or return None if required fields are missing."""
        title = (getattr(entry, "title", "") or "").strip()
        link = (getattr(entry, "link", "") or "").strip()

        if not title or not link:
            log.debug("rss.entry_skipped_missing_fields", source=self.source_id)
            return None

        body = ""
        content_blocks = getattr(entry, "content", None)
        if isinstance(content_blocks, list) and content_blocks:
            first_block = content_blocks[0]
            if isinstance(first_block, dict):
                body = (first_block.get("value") or "").strip()
            else:
                body = (getattr(first_block, "value", "") or "").strip()

        if not body:
            body = (getattr(entry, "summary", "") or "").strip()
        if not body:
            body = (getattr(entry, "description", "") or "").strip()

        published = self._parse_date(entry)
        entry_id = (getattr(entry, "id", "") or getattr(entry, "guid", "") or link).strip()

        return RawEvent(
            id=entry_id,
            title=title,
            body=body,
            source_url=link,
            source=self.source_id,
            source_type="rss",
            published=published,
            raw_payload=dict(entry) if hasattr(entry, "keys") else {},
            metadata={"feed_url": self._url},
        )

    def _parse_date(self, entry: Any) -> datetime:
        """Parse RSS entry time using common feed fields and fallback to now()."""
        parsed_value = getattr(entry, "published_parsed", None)
        if isinstance(parsed_value, struct_time):
            return datetime(*parsed_value[:6], tzinfo=timezone.utc)

        parsed_value = getattr(entry, "updated_parsed", None)
        if isinstance(parsed_value, struct_time):
            return datetime(*parsed_value[:6], tzinfo=timezone.utc)

        published_text = (getattr(entry, "published", "") or "").strip()
        if published_text:
            try:
                parsed_dt = parsedate_to_datetime(published_text)
                if parsed_dt.tzinfo is None:
                    return parsed_dt.replace(tzinfo=timezone.utc)
                return parsed_dt.astimezone(timezone.utc)
            except (TypeError, ValueError):
                pass

        return datetime.now(tz=timezone.utc)

    async def health_check(self) -> bool:
        """Return True when the feed endpoint responds with HTTP 200."""
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        headers = {"User-Agent": self.USER_AGENT}

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(self._url) as response:
                    return response.status == 200
        except aiohttp.ClientError:
            return False
