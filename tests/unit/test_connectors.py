from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import redis

from connectors.rss_connector import RSSConnector


def _patch_aiohttp_get(mock_session_cls: MagicMock, *, status: int = 200, text: str = "") -> None:
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.text = AsyncMock(return_value=text)
    mock_response.raise_for_status = MagicMock()

    mock_req_cm = AsyncMock()
    mock_req_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_req_cm.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_req_cm)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_session_cls.return_value = mock_session_cm


class TestRSSConnector:
    @pytest.mark.asyncio
    async def test_parses_two_articles(self, mock_rss_xml: str) -> None:
        connector = RSSConnector(source_id="test-rss", url="https://example.com/feed")
        with patch("aiohttp.ClientSession") as mock_session_cls:
            _patch_aiohttp_get(mock_session_cls, text=mock_rss_xml)
            events = [event async for event in connector._fetch_raw()]

        assert len(events) == 2
        assert events[0].title == "Apple Beats Q2 Expectations"

    @pytest.mark.asyncio
    async def test_assigns_utc_timezone(self, mock_rss_xml: str) -> None:
        connector = RSSConnector(source_id="test-rss", url="https://example.com/feed")
        with patch("aiohttp.ClientSession") as mock_session_cls:
            _patch_aiohttp_get(mock_session_cls, text=mock_rss_xml)
            events = [event async for event in connector._fetch_raw()]

        assert all(event.published.tzinfo is not None for event in events)

    @pytest.mark.asyncio
    async def test_empty_feed_returns_nothing(self) -> None:
        connector = RSSConnector(source_id="test-rss", url="https://example.com/feed")
        empty_feed = """<?xml version=\"1.0\"?><rss version=\"2.0\"><channel></channel></rss>"""
        with patch("aiohttp.ClientSession") as mock_session_cls:
            _patch_aiohttp_get(mock_session_cls, text=empty_feed)
            events = [event async for event in connector._fetch_raw()]

        assert events == []

    def test_source_id_property(self) -> None:
        connector = RSSConnector(source_id="reuters", url="https://example.com/feed")
        assert connector.source_id == "reuters"

    @pytest.mark.asyncio
    async def test_source_type_is_rss(self, mock_rss_xml: str) -> None:
        connector = RSSConnector(source_id="reuters", url="https://example.com/feed")
        with patch("aiohttp.ClientSession") as mock_session_cls:
            _patch_aiohttp_get(mock_session_cls, text=mock_rss_xml)
            events = [event async for event in connector._fetch_raw()]

        assert events[0].source_type == "rss"

    @pytest.mark.asyncio
    async def test_health_check_true_on_200(self) -> None:
        connector = RSSConnector(source_id="reuters", url="https://example.com/feed")
        with patch("aiohttp.ClientSession") as mock_session_cls:
            _patch_aiohttp_get(mock_session_cls, status=200)
            assert await connector.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_false_on_error(self) -> None:
        connector = RSSConnector(source_id="reuters", url="https://example.com/feed")
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.side_effect = aiohttp.ClientError("network failure")
            assert await connector.health_check() is False


class TestDeduplication:
    def test_new_event_not_duplicate(self) -> None:
        fake_redis = MagicMock()
        fake_redis.set.return_value = True
        with patch("workers.dedup._get_redis", return_value=fake_redis):
            from workers.dedup import is_duplicate

            assert is_duplicate("checksum-1") is False

    def test_existing_event_is_duplicate(self) -> None:
        fake_redis = MagicMock()
        fake_redis.set.return_value = False
        with patch("workers.dedup._get_redis", return_value=fake_redis):
            from workers.dedup import is_duplicate

            assert is_duplicate("checksum-1") is True

    def test_redis_down_fails_open(self) -> None:
        fake_redis = MagicMock()
        fake_redis.set.side_effect = redis.RedisError("redis down")
        with patch("workers.dedup._get_redis", return_value=fake_redis):
            from workers.dedup import is_duplicate

            assert is_duplicate("checksum-1") is False

    def test_checksum_is_deterministic(self, sample_raw_event) -> None:
        assert sample_raw_event.checksum == sample_raw_event.checksum

    def test_different_titles_different_checksums(self, sample_raw_event) -> None:
        from copy import copy

        event_2 = copy(sample_raw_event)
        event_2.title = "Different title"
        assert sample_raw_event.checksum != event_2.checksum


class TestCircuitBreaker:
    def test_closed_by_default(self) -> None:
        from workers.self_healing import CircuitBreaker, CircuitState

        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_available() is True

    def test_opens_after_threshold(self) -> None:
        from workers.self_healing import CircuitBreaker, CircuitState

        breaker = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_rejects_calls_when_open(self) -> None:
        from workers.self_healing import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        assert breaker.is_available() is False

    def test_transitions_to_half_open_after_timeout(self) -> None:
        from workers.self_healing import CircuitBreaker, CircuitState

        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        breaker.record_failure()
        time.sleep(0.05)
        assert breaker.is_available() is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_closes_after_success_in_half_open(self) -> None:
        from workers.self_healing import CircuitBreaker, CircuitState

        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, success_threshold=2)
        breaker.record_failure()
        time.sleep(0.05)
        breaker.is_available()
        breaker.record_success()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED


class TestRetryDecorator:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self) -> None:
        from workers.self_healing import retry_with_backoff

        calls = {"count": 0}

        @retry_with_backoff(max_retries=3)
        async def fn() -> str:
            calls["count"] += 1
            return "ok"

        assert await fn() == "ok"
        assert calls["count"] == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self) -> None:
        from workers.self_healing import retry_with_backoff

        calls = {"count": 0}

        @retry_with_backoff(max_retries=3, base_delay=0.001)
        async def fn() -> str:
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("try again")
            return "ok"

        assert await fn() == "ok"
        assert calls["count"] == 3

    @pytest.mark.asyncio
    async def test_raises_after_exhausted_retries(self) -> None:
        from workers.self_healing import retry_with_backoff

        @retry_with_backoff(max_retries=2, base_delay=0.001)
        async def fn() -> None:
            raise ValueError("permanent")

        with pytest.raises(ValueError):
            await fn()
