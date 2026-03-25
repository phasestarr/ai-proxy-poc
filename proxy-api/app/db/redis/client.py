"""
Purpose:
- Configure and expose shared Redis access for runtime coordination.

Responsibilities:
- Create a process-wide Redis client
- Fail fast on missing Redis connectivity at startup
- Keep Redis wiring out of routers and domain services
"""

from __future__ import annotations

from redis import Redis

from app.core.config import settings

redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=False,
    health_check_interval=30,
)


def get_redis_client() -> Redis:
    return redis_client


def verify_redis_connection() -> None:
    redis_client.ping()


def close_redis_client() -> None:
    redis_client.close()
