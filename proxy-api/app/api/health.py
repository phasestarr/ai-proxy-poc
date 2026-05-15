"""
Purpose:
- Provide a minimal health check endpoint for the backend.

Current responsibilities:
- Confirm that the FastAPI process is running and reachable

Planned future usage:
- Serve as a lightweight readiness or liveness probe target
- Stay intentionally simple and dependency-light

Notes:
- Do not add heavy logic or provider/database calls to this route.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "proxy-api",
    }
