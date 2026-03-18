from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from workers.normalizer import _clean_html, _send_dlq
from workers.prompts import CLASSIFY_SYSTEM, EXTRACT_SYSTEM, SUMMARIZE_SYSTEM, get_prompt


class TestContentCleaning:
    def test_strips_html_tags(self) -> None:
        raw = "<script>alert('x')</script><b>Apple</b> posted earnings"
        cleaned = _clean_html(raw)
        assert "<script>" not in cleaned
        assert "<b>" not in cleaned
        assert "Apple" in cleaned

    def test_truncates_at_10000_chars(self) -> None:
        cleaned = _clean_html("a" * 12000)
        assert len(cleaned) == 10000

    def test_collapses_whitespace(self) -> None:
        cleaned = _clean_html("Apple    earnings\n\n   beat   estimates")
        assert cleaned == "Apple earnings beat estimates"

    def test_empty_string(self) -> None:
        assert _clean_html("") == ""

    def test_plain_text_unchanged(self) -> None:
        text = "Apple reported strong revenue growth"
        assert _clean_html(text) == text


class TestDLQ:
    @pytest.mark.asyncio
    async def test_sends_dict_to_dlq(self) -> None:
        sender = AsyncMock()
        with patch("workers.normalizer.dlq_topic", sender):
            await _send_dlq({"id": "1", "title": "x"}, reason="low_quality", error="bad")

        assert sender.send.await_count == 1
        payload = sender.send.await_args.kwargs["value"]
        data = json.loads(payload)
        assert data["reason"] == "low_quality"

    @pytest.mark.asyncio
    async def test_sends_bytes_to_dlq(self) -> None:
        sender = AsyncMock()
        with patch("workers.normalizer.dlq_topic", sender):
            await _send_dlq(b'{"id":"1"}', reason="invalid_json")

        payload = sender.send.await_args.kwargs["value"]
        data = json.loads(payload)
        assert data["reason"] == "invalid_json"


class TestPrompts:
    def test_all_categories_in_classify_system(self) -> None:
        for category in [
            "EARNINGS",
            "MACRO",
            "COMPANY_NEWS",
            "REGULATORY",
            "MARKET_DATA",
            "TECH",
            "IRRELEVANT",
        ]:
            assert category in CLASSIFY_SYSTEM

    def test_get_prompt_raises_on_unknown_name(self) -> None:
        with pytest.raises(KeyError):
            get_prompt("unknown")

    def test_get_prompt_returns_tuple_of_strings(self) -> None:
        system, user = get_prompt("classify")
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_summarize_has_length_requirement(self) -> None:
        assert "100-150" in SUMMARIZE_SYSTEM

    def test_extract_defines_schema(self) -> None:
        assert "companies" in EXTRACT_SYSTEM
        assert "people" in EXTRACT_SYSTEM
        assert "amounts" in EXTRACT_SYSTEM
