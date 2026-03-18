"""GitHub events connector implementation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import aiohttp
import structlog

from config.settings import get_settings
from connectors.base_connector import BaseConnector, RawEvent

log = structlog.get_logger(__name__)
settings = get_settings()


class GitHubConnector(BaseConnector):
    """Fetch recent GitHub repository events.

    Parameters
    ----------
    source_id : str
        Source identifier from configuration.
    repo : str
        Repository in owner/name format.
    event_types : set[str] | None, optional
        Event types to include. Defaults to PushEvent, ReleaseEvent, IssuesEvent.
    lookback_hours : int, default=2
        Lookback window for recent events.
    """

    DEFAULT_EVENT_TYPES = {"PushEvent", "ReleaseEvent", "IssuesEvent"}

    def __init__(
        self,
        source_id: str,
        repo: str,
        event_types: set[str] | None = None,
        lookback_hours: int = 2,
    ) -> None:
        self._source_id = source_id
        self._repo = repo
        self._event_types = event_types or self.DEFAULT_EVENT_TYPES
        self._lookback_hours = lookback_hours
        super().__init__()

    @property
    def source_id(self) -> str:
        """Return connector source identifier."""
        return self._source_id

    async def _fetch_raw(self) -> AsyncIterator[RawEvent]:
        """Fetch repository events from GitHub."""
        url = f"https://api.github.com/repos/{self._repo}/events"
        params = {"per_page": 100}
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._lookback_hours)

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "DataPipeline/1.0",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, params=params) as response:
                if response.status == 403:
                    log.error("Set GITHUB_TOKEN", repo=self._repo)
                    return
                if response.status == 404:
                    log.warning("repo not found", repo=self._repo)
                    return
                response.raise_for_status()
                events = await response.json()

        for event in events:
            created_at = self._parse_datetime(event.get("created_at"))
            if created_at < cutoff:
                break

            event_type = event.get("type")
            if event_type not in self._event_types:
                continue

            parsed = self._parse_event(event)
            if parsed is not None:
                yield parsed

    def _parse_event(self, event: dict[str, Any]) -> RawEvent | None:
        """Convert a GitHub event payload to RawEvent."""
        event_type = event.get("type")
        payload = event.get("payload") or {}
        created_at = self._parse_datetime(event.get("created_at"))
        html_url = (((event.get("repo") or {}).get("name") and f"https://github.com/{self._repo}") or "")
        source_url = html_url or event.get("url") or f"https://api.github.com/repos/{self._repo}"

        if event_type == "ReleaseEvent":
            release = payload.get("release") or {}
            tag_name = release.get("tag_name") or "unknown"
            release_body = (release.get("body") or "")[:500]
            return RawEvent(
                id=str(event.get("id", "")),
                title=f"{self._repo}: Release {tag_name}",
                body=release_body,
                source_url=release.get("html_url") or source_url,
                source=self.source_id,
                source_type="github",
                published=created_at,
                raw_payload=event,
                metadata={"event_type": event_type, "tag_name": tag_name},
            )

        if event_type == "PushEvent":
            ref = str(payload.get("ref") or "")
            branch = ref.split("/")[-1] if ref else "unknown"
            commits = payload.get("commits") or []
            commit_messages = []
            for commit in commits[:5]:
                message = str((commit or {}).get("message") or "").strip()
                if message:
                    commit_messages.append(message)
            summary = "\n".join(f"- {msg}" for msg in commit_messages)
            body = summary if summary else "No commit messages available."
            return RawEvent(
                id=str(event.get("id", "")),
                title=f"{self._repo}: {len(commits)} commit(s) pushed to {branch}",
                body=body,
                source_url=source_url,
                source=self.source_id,
                source_type="github",
                published=created_at,
                raw_payload=event,
                metadata={"event_type": event_type, "branch": branch},
            )

        if event_type == "IssuesEvent":
            issue = payload.get("issue") or {}
            number = issue.get("number")
            action = payload.get("action") or "updated"
            issue_title = issue.get("title") or "Untitled issue"
            body = (issue.get("body") or "")[:500]
            return RawEvent(
                id=str(event.get("id", "")),
                title=f"{self._repo}: Issue #{number} {action} — {issue_title}",
                body=body,
                source_url=issue.get("html_url") or source_url,
                source=self.source_id,
                source_type="github",
                published=created_at,
                raw_payload=event,
                metadata={"event_type": event_type, "action": action, "number": number},
            )

        return None

    async def health_check(self) -> bool:
        """Return True when repository endpoint responds with HTTP 200."""
        url = f"https://api.github.com/repos/{self._repo}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "DataPipeline/1.0",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    return response.status == 200
        except aiohttp.ClientError:
            return False

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        """Parse GitHub timestamps with UTC fallback."""
        if not value:
            return datetime.now(timezone.utc)

        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
