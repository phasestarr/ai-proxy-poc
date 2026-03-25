"""
Purpose:
- Coordinate chat concurrency and quota enforcement through Redis.

Responsibilities:
- Prevent overlapping chat executions per backend session
- Enforce per-user short-window and hourly request limits
- Keep Redis-specific coordination logic out of routers and chat orchestration
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import secrets

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.security import utc_now
from app.db.redis.client import get_redis_client

LOCK_KEY_PREFIX = "ai-proxy:chat:lock"
MINUTE_RATE_KEY_PREFIX = "ai-proxy:chat:rate:minute"
HOUR_RATE_KEY_PREFIX = "ai-proxy:chat:rate:hour"

RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class ChatCoordinationUnavailableError(RuntimeError):
    """Raised when Redis-backed coordination cannot run."""


class ChatRequestInProgressError(RuntimeError):
    """Raised when the current backend session already owns an active chat request."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("a chat request is already in progress for this session")


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


@dataclass(slots=True)
class ChatExecutionLease:
    lock_key: str
    owner_token: str


def acquire_chat_execution_lease(*, session_id: str) -> ChatExecutionLease:
    redis_client = get_redis_client()
    lock_key = _build_lock_key(session_id=session_id)
    owner_token = secrets.token_urlsafe(24)

    try:
        acquired = redis_client.set(
            lock_key,
            owner_token,
            nx=True,
            ex=max(1, settings.chat_inflight_lock_ttl_seconds),
        )
        if acquired:
            return ChatExecutionLease(lock_key=lock_key, owner_token=owner_token)

        retry_after_seconds = _normalize_retry_after(
            redis_client.ttl(lock_key),
            fallback_seconds=settings.chat_inflight_lock_ttl_seconds,
        )
        raise ChatRequestInProgressError(retry_after_seconds=retry_after_seconds)
    except ChatRequestInProgressError:
        raise
    except RedisError as exc:
        raise ChatCoordinationUnavailableError("chat coordination backend is unavailable") from exc


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


def release_chat_execution_lease(lease: ChatExecutionLease | None) -> None:
    if lease is None:
        return

    try:
        get_redis_client().eval(
            RELEASE_LOCK_SCRIPT,
            1,
            lease.lock_key,
            lease.owner_token,
        )
    except RedisError:
        return


def _build_lock_key(*, session_id: str) -> str:
    return f"{LOCK_KEY_PREFIX}:{session_id}"


def _build_minute_rate_key(*, user_id: str, current_time) -> str:
    minute_bucket = current_time.strftime("%Y%m%d%H%M")
    return f"{MINUTE_RATE_KEY_PREFIX}:{user_id}:{minute_bucket}"


def _build_hour_rate_key(*, user_id: str, current_time) -> str:
    hour_bucket = current_time.strftime("%Y%m%d%H")
    return f"{HOUR_RATE_KEY_PREFIX}:{user_id}:{hour_bucket}"


def _normalize_retry_after(ttl_seconds: int, *, fallback_seconds: int) -> int:
    if ttl_seconds is None or ttl_seconds <= 0:
        return max(1, fallback_seconds)
    return ttl_seconds


def _seconds_until_next_minute(current_time) -> int:
    next_minute = (current_time.replace(second=0, microsecond=0) + timedelta(minutes=1))
    return max(1, int((next_minute - current_time).total_seconds()))


def _seconds_until_next_hour(current_time) -> int:
    next_hour = (current_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    return max(1, int((next_hour - current_time).total_seconds()))
