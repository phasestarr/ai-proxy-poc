"""
Purpose:
- Coordinate chat concurrency and quota enforcement through Redis.

Responsibilities:
- Enforce per-user short-window and hourly request limits
- Keep Redis-specific rate-limit logic out of routers and chat orchestration
"""

from __future__ import annotations

from datetime import timedelta

from redis.exceptions import RedisError

from app.config.settings import settings
from app.config.time import utc_now
from app.db.redis.client import get_redis_client

MINUTE_RATE_KEY_PREFIX = "ai-proxy:chat:rate:minute"
HOUR_RATE_KEY_PREFIX = "ai-proxy:chat:rate:hour"


class ChatCoordinationUnavailableError(RuntimeError):
    """Raised when Redis-backed coordination cannot run."""


class ChatRateLimitExceededError(RuntimeError):
    """Raised when a user exceeds configured chat request quotas."""

    def __init__(
        self,
        *,
        window: str,
        limit: int,
        retry_after_seconds: int,
    ) -> None:
        self.window = window
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"chat rate limit exceeded: {limit} requests per {window}")


def enforce_chat_rate_limits(*, user_id: str) -> None:
    redis_client = get_redis_client()
    now = utc_now()

    minute_key = _build_minute_rate_key(user_id=user_id, current_time=now)
    hour_key = _build_hour_rate_key(user_id=user_id, current_time=now)

    minute_ttl_seconds = _seconds_until_next_minute(now)
    hour_ttl_seconds = _seconds_until_next_hour(now)

    try:
        pipeline = redis_client.pipeline(transaction=True)
        pipeline.incr(minute_key)
        pipeline.expire(minute_key, minute_ttl_seconds)
        pipeline.incr(hour_key)
        pipeline.expire(hour_key, hour_ttl_seconds)
        minute_count, _, hour_count, _ = pipeline.execute()
    except RedisError as exc:
        raise ChatCoordinationUnavailableError("chat coordination backend is unavailable") from exc

    if minute_count > settings.chat_rate_limit_per_minute:
        raise ChatRateLimitExceededError(
            window="minute",
            limit=settings.chat_rate_limit_per_minute,
            retry_after_seconds=minute_ttl_seconds,
        )

    if hour_count > settings.chat_rate_limit_per_hour:
        raise ChatRateLimitExceededError(
            window="hour",
            limit=settings.chat_rate_limit_per_hour,
            retry_after_seconds=hour_ttl_seconds,
        )


def _build_minute_rate_key(*, user_id: str, current_time) -> str:
    minute_bucket = current_time.strftime("%Y%m%d%H%M")
    return f"{MINUTE_RATE_KEY_PREFIX}:{user_id}:{minute_bucket}"


def _build_hour_rate_key(*, user_id: str, current_time) -> str:
    hour_bucket = current_time.strftime("%Y%m%d%H")
    return f"{HOUR_RATE_KEY_PREFIX}:{user_id}:{hour_bucket}"


def _seconds_until_next_minute(current_time) -> int:
    next_minute = (current_time.replace(second=0, microsecond=0) + timedelta(minutes=1))
    return max(1, int((next_minute - current_time).total_seconds()))


def _seconds_until_next_hour(current_time) -> int:
    next_hour = (current_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    return max(1, int((next_hour - current_time).total_seconds()))
