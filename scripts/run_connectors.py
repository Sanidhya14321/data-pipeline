"""Connector orchestrator that schedules all enabled sources."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from urllib.parse import urlparse

import structlog
import yaml

from connectors.api_connector import NewsAPIConnector
from connectors.base_connector import BaseConnector
from connectors.github_connector import GitHubConnector
from connectors.rss_connector import RSSConnector
from connectors.sec_connector import SECConnector
from workers.db import init_schema, update_connector_state
from workers.self_healing import GracefulShutdown

log = structlog.get_logger(__name__)


def load_sources(path: str = "config/sources.yaml") -> list[dict]:
    """Load enabled sources from YAML configuration.

    Parameters
    ----------
    path : str, default="config/sources.yaml"
        Relative or absolute path to source config file.

    Returns
    -------
    list[dict]
        Enabled source configuration objects.
    """
    config_path = Path(path)
    if not config_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[1]
        config_path = repo_root / path

    with config_path.open("r", encoding="utf-8") as fp:
        payload = yaml.safe_load(fp) or {}

    sources = payload.get("sources")
    if not isinstance(sources, list):
        return []

    return [source for source in sources if isinstance(source, dict) and source.get("enabled") is True]


def build_connector(source: dict) -> BaseConnector | None:
    """Build connector instance from one source configuration object.

    Parameters
    ----------
    source : dict
        Source entry from config/sources.yaml.

    Returns
    -------
    BaseConnector | None
        Connector instance for known source type; None for unknown/invalid sources.
    """
    source_id = str(source.get("id") or "").strip()
    source_type = str(source.get("type") or "").strip().lower()

    if not source_id or not source_type:
        log.warning("connector_factory.invalid_source", source=source)
        return None

    if source_type == "rss":
        url = str(source.get("url") or "").strip()
        if not url:
            log.warning("connector_factory.missing_url", source_id=source_id)
            return None
        return RSSConnector(source_id=source_id, url=url)

    if source_type == "api":
        provider = str(source.get("provider") or "newsapi").strip().lower()
        if provider != "newsapi":
            log.warning("connector_factory.unknown_api_provider", source_id=source_id, provider=provider)
            return None
        query = str(source.get("query") or "").strip()
        if not query:
            log.warning("connector_factory.missing_query", source_id=source_id)
            return None
        language = str(source.get("language") or "en").strip() or "en"
        return NewsAPIConnector(source_id=source_id, query=query, language=language)

    if source_type == "sec":
        filing_types_raw = source.get("filing_types")
        if isinstance(filing_types_raw, list):
            filing_types = [str(item) for item in filing_types_raw if item]
        else:
            # Backward-compatible support for single form_type field.
            fallback_form = source.get("form_type")
            filing_types = [str(fallback_form)] if fallback_form else ["10-Q", "8-K"]

        tickers_raw = source.get("tickers")
        tickers = [str(item).upper() for item in tickers_raw if item] if isinstance(tickers_raw, list) else []
        if not tickers:
            log.warning("connector_factory.missing_tickers", source_id=source_id)
            return None
        return SECConnector(source_id=source_id, filing_types=filing_types, tickers=tickers)

    if source_type == "github":
        repo = str(source.get("repo") or "").strip()
        if not repo:
            url = str(source.get("url") or "").strip()
            if url:
                parsed = urlparse(url)
                parts = [part for part in parsed.path.split("/") if part]
                # Supports /repos/{owner}/{repo}/events and /{owner}/{repo}
                if len(parts) >= 3 and parts[0] == "repos":
                    repo = f"{parts[1]}/{parts[2]}"
                elif len(parts) >= 2:
                    repo = f"{parts[0]}/{parts[1]}"

        if not repo:
            log.warning("connector_factory.missing_repo", source_id=source_id)
            return None

        event_types_raw = source.get("event_types")
        event_types = (
            {str(item) for item in event_types_raw if item}
            if isinstance(event_types_raw, list)
            else None
        )
        return GitHubConnector(source_id=source_id, repo=repo, event_types=event_types)

    log.warning("connector_factory.unknown_type", source_id=source_id, source_type=source_type)
    return None


async def run_connector_loop(connector: BaseConnector, interval_minutes: int) -> None:
    """Run a connector forever at fixed intervals without crashing.

    Parameters
    ----------
    connector : BaseConnector
        Connector instance to execute.
    interval_minutes : int
        Run interval in minutes.
    """
    interval_seconds = max(60, int(interval_minutes) * 60)

    while True:
        started = time.monotonic()
        try:
            count = await connector.run_once()
            connector.flush_kafka()
            await update_connector_state(source_id=connector.source_id, success=True)
            log.info(
                "connector.loop_success",
                source_id=connector.source_id,
                events_published=count,
                interval_minutes=interval_minutes,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(
                "connector.loop_error",
                source_id=connector.source_id,
                error=str(exc),
            )
            await update_connector_state(
                source_id=connector.source_id,
                success=False,
                error=str(exc),
            )

        elapsed = time.monotonic() - started
        sleep_seconds = max(0.0, interval_seconds - elapsed)
        await asyncio.sleep(sleep_seconds)


async def main() -> None:
    """Initialize schema, register connectors, and keep tasks alive until shutdown."""
    await init_schema()

    sources = load_sources()
    tasks: list[asyncio.Task] = []

    for source in sources:
        connector = build_connector(source)
        if connector is None:
            continue

        interval = int(source.get("interval_minutes") or 5)
        task = asyncio.create_task(
            run_connector_loop(connector, interval),
            name=f"connector:{connector.source_id}",
        )
        tasks.append(task)
        log.info("connector.registered", source_id=connector.source_id, interval_minutes=interval)

    async with GracefulShutdown() as shutdown:
        await shutdown.wait_for_stop()

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("connector.orchestrator_stopped", task_count=len(tasks))


if __name__ == "__main__":
    asyncio.run(main())
