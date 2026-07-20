"""Application infrastructure tuning values that are not deployment-specific."""

REDIS_HEALTH_CHECK_INTERVAL_SECONDS = 30
PROVIDER_HEARTBEAT_MAX_INTERVAL_SECONDS = 30
STALE_EMPTY_HISTORY_MIN_AGE_MINUTES = 5


def validate_runtime_config() -> None:
    if REDIS_HEALTH_CHECK_INTERVAL_SECONDS < 1:
        raise ValueError("REDIS_HEALTH_CHECK_INTERVAL_SECONDS must be positive")
    if PROVIDER_HEARTBEAT_MAX_INTERVAL_SECONDS < 1:
        raise ValueError("PROVIDER_HEARTBEAT_MAX_INTERVAL_SECONDS must be positive")
    if STALE_EMPTY_HISTORY_MIN_AGE_MINUTES < 1:
        raise ValueError("STALE_EMPTY_HISTORY_MIN_AGE_MINUTES must be positive")


validate_runtime_config()
