"""Redis-backed deduplication helpers for ingestion workers."""

from __future__ import annotations

import redis
import structlog

from config.settings import get_settings

log = structlog.get_logger(__name__)

_SEEN_PREFIX = "seen:"
_DEFAULT_WINDOW_SECONDS = 86400
_REDIS_CLIENT: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """Return a lazily initialized Redis client.

    Returns
    -------
    redis.Redis
        Shared Redis client instance.
    """
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        settings = get_settings()
        _REDIS_CLIENT = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
        )
    return _REDIS_CLIENT


def is_duplicate(checksum: str, window_seconds: int = _DEFAULT_WINDOW_SECONDS) -> bool:
    """Return whether a checksum has already been seen in the deduplication window.

    Parameters
    ----------
    checksum : str
        Content checksum to check.
    window_seconds : int, default=86400
        TTL window for considering duplicates.

    Returns
    -------
    bool
        True if duplicate, False if new.

    Notes
    -----
    This operation is atomic via Redis SET with nx=True and ex=<ttl>.
    If Redis is unavailable, this function fails open and returns False.
    """
    try:
        is_new = _get_redis().set(
            f"{_SEEN_PREFIX}{checksum}",
            "1",
            nx=True,
            ex=window_seconds,
        )
        return not bool(is_new)
    except redis.RedisError as exc:
        log.warning(
            "dedup.redis_error",
            error=str(exc),
            checksum=checksum,
            fail_open=True,
        )
        return False


def mark_seen(checksum: str, window_seconds: int = _DEFAULT_WINDOW_SECONDS) -> bool:
    """Mark a checksum as seen with an expiration window.

    Parameters
    ----------
    checksum : str
        Content checksum to mark.
    window_seconds : int, default=86400
        TTL applied to the seen marker.

    Returns
    -------
    bool
        True if Redis accepted the write, False when Redis is unavailable.
    """
    try:
        return bool(_get_redis().set(f"{_SEEN_PREFIX}{checksum}", "1", ex=window_seconds))
    except redis.RedisError as exc:
        log.warning("dedup.mark_seen_failed", error=str(exc), checksum=checksum)
        return False


def clear_seen(checksum: str) -> bool:
    """Remove a checksum marker from Redis.

    Parameters
    ----------
    checksum : str
        Content checksum to clear.

    Returns
    -------
    bool
        True if a key was removed, False otherwise.
    """
    try:
        deleted = _get_redis().delete(f"{_SEEN_PREFIX}{checksum}")
        return bool(deleted)
    except redis.RedisError as exc:
        log.warning("dedup.clear_seen_failed", error=str(exc), checksum=checksum)
        return False
