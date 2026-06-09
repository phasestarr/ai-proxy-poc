"""
Purpose:
- Application entry point for the FastAPI backend.

Responsibilities:
- Create the FastAPI application instance
- Register routers
- Initialize shared infrastructure
- Run lightweight background housekeeping
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.router import api_router
from app.api.v1.dependencies.request import get_client_ip
from app.api.v1.errors.authentication import AuthResponseError
from app.auth.cookies import clear_session_conflict_cookie, clear_session_cookie
from app.auth.session_lifecycle import resolve_session
from app.config.settings import settings
from app.db.postgres.migrations import run_database_migrations
from app.db.postgres.session import SessionLocal
from app.db.redis.client import close_redis_client, verify_redis_connection
from app.services.chat.completions.request_audit import persist_chat_request_validation_rejection
from app.workers.housekeeping import run_housekeeping_once

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


@app.exception_handler(AuthResponseError)
async def handle_auth_response_error(_, exc: AuthResponseError) -> JSONResponse:
    response = JSONResponse(
        status_code=exc.status_code,
        content=exc.payload.model_dump(mode="json"),
    )
    if exc.clear_cookie:
        clear_session_cookie(response)
    if exc.clear_conflict_cookie:
        clear_session_conflict_cookie(response)
    return response


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request, exc: RequestValidationError):
    if request.url.path == "/api/v1/chat/completions":
        try:
            with SessionLocal() as db:
                lookup = resolve_session(
                    db,
                    raw_session_key=request.cookies.get(settings.auth_session_cookie_name),
                    client_ip=get_client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                    touch=False,
                )
                persist_chat_request_validation_rejection(
                    db,
                    session=lookup.context,
                    validation_error=exc,
                )
        except Exception:
            logger.exception("Failed to persist chat request validation rejection.")

    return await request_validation_exception_handler(request, exc)


@app.on_event("startup")
async def startup() -> None:
    await _initialize_dependencies()
    app.state.housekeeping_task = asyncio.create_task(_housekeeping_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    for task_name in ("housekeeping_task",):
        task = getattr(app.state, task_name, None)
        if task is None:
            continue
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


async def _housekeeping_loop() -> None:
    interval_seconds = max(60, settings.housekeeping_interval_minutes * 60)

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await run_housekeeping_once()
        except Exception:
            logger.exception("Background housekeeping failed.")


async def _initialize_dependencies() -> None:
    max_attempts = max(1, settings.startup_dependency_max_attempts)
    retry_seconds = max(0.1, settings.startup_dependency_retry_seconds)

    for attempt in range(1, max_attempts + 1):
        try:
            verify_redis_connection()
            run_database_migrations()
            await run_housekeeping_once()
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
