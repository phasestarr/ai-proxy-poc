from __future__ import annotations

from dataclasses import dataclass

from app.schemas.authentication import AuthIssueResponse


@dataclass(slots=True)
class AuthResponseError(Exception):
    status_code: int
    payload: AuthIssueResponse
    clear_cookie: bool = False
    clear_conflict_cookie: bool = False

