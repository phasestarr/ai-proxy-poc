"""
Purpose:
- Application entry point for the FastAPI backend.

Responsibilities:
- Create the FastAPI application instance
- Register routers
- Initialize shared infrastructure
- Run lightweight background cleanup for auth data
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.router import api_router
from app.config.settings import settings
from app.db.postgres.session import SessionLocal, init_database
from app.db.redis.client import close_redis_client, verify_redis_connection
from app.services.auth import purge_expired_auth_data

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


@app.on_event("startup")
async def startup() -> None:
    await _initialize_dependencies()
    app.state.auth_cleanup_task = asyncio.create_task(_auth_cleanup_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "auth_cleanup_task", None)
    if task is None:
        return

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    close_redis_client()


app.include_router(health_router)
app.include_router(api_router)


@app.get("/")
def root() -> dict:
    return {
        "message": "AI Proxy API is running",
    }


async def _auth_cleanup_loop() -> None:
    interval_seconds = max(60, settings.auth_cleanup_interval_minutes * 60)

    while True:
        await asyncio.sleep(interval_seconds)
        with SessionLocal() as db:
            purge_expired_auth_data(db)


async def _initialize_dependencies() -> None:
    max_attempts = max(1, settings.startup_dependency_max_attempts)
    retry_seconds = max(0.1, settings.startup_dependency_retry_seconds)

    for attempt in range(1, max_attempts + 1):
        try:
            verify_redis_connection()
            init_database()
            with SessionLocal() as db:
                purge_expired_auth_data(db)
            logger.info("Application dependencies are ready.")
            return
        except Exception as exc:
            if attempt >= max_attempts:
                logger.exception(
                    "Application dependency initialization failed after %s attempts.",
                    max_attempts,
                )
                raise

            logger.warning(
                "Dependency initialization attempt %s/%s failed: %s. Retrying in %.1f seconds.",
                attempt,
                max_attempts,
                exc,
                retry_seconds,
            )
            await asyncio.sleep(retry_seconds)
