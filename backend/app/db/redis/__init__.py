"""
Redis persistence package.

Purpose:
- Group Redis client wiring and Redis-backed coordination logic.
"""

from app.db.redis.client import close_redis_client, get_redis_client, verify_redis_connection

__all__ = [
    "close_redis_client",
    "get_redis_client",
    "verify_redis_connection",
]
