"""
Purpose:
- Provide backend health checks for Docker Compose startup ordering.

Current responsibilities:
- Confirm that the FastAPI process is running and reachable
- Optionally run the deployment smoke check once before reporting healthy
"""

from __future__ import annotations

from dataclasses import dataclass
import threading

from app.config.settings import settings
from app.config.time import utc_now
from app.deployment_smoke.runner import run_smoke_check
from fastapi import APIRouter, HTTPException

router = APIRouter()

_SMOKE_LOCK = threading.Lock()


@dataclass(slots=True)
class DeploymentSmokeState:
    passed: bool = False
    last_error: str | None = None
    last_checked_at: str | None = None


_smoke_state = DeploymentSmokeState()


@router.get("/health")
def health_check() -> dict:
    if settings.deployment_smoke_required:
        _ensure_deployment_smoke_passed()
    return {
        "status": "ok",
        "service": "ai-proxy",
        "deployment_smoke_required": settings.deployment_smoke_required,
        "deployment_smoke_passed": _smoke_state.passed if settings.deployment_smoke_required else None,
    }


def _ensure_deployment_smoke_passed() -> None:
    if _smoke_state.passed:
        return

    with _SMOKE_LOCK:
        if _smoke_state.passed:
            return
        _smoke_state.last_checked_at = utc_now().isoformat()
        try:
            run_smoke_check()
        except Exception as exc:
            _smoke_state.last_error = str(exc)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "deployment_smoke_failed",
                    "message": "deployment smoke check has not passed",
                    "last_error": _smoke_state.last_error,
                    "last_checked_at": _smoke_state.last_checked_at,
                },
            ) from exc
        _smoke_state.passed = True
        _smoke_state.last_error = None
