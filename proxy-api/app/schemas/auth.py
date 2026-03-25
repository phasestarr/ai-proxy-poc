"""
Purpose:
- Define authentication and session related API schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SessionView(BaseModel):
    user_id: str
    auth_type: Literal["guest", "microsoft"]
    display_name: str
    email: str | None = None
    capabilities: list[str]
    persistent: bool
    idle_expires_at: datetime
    absolute_expires_at: datetime


class AuthSessionEnvelope(BaseModel):
    authenticated: Literal[True] = True
    session: SessionView


class AuthAnonymousResponse(BaseModel):
    authenticated: Literal[False] = False
    reason: str
    login_required: bool = True
