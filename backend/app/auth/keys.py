from __future__ import annotations

import hashlib
import secrets


def generate_session_key() -> str:
    return f"s1_{secrets.token_urlsafe(32)}"


def hash_session_key(raw_session_key: str) -> str:
    return hashlib.sha256(raw_session_key.encode("utf-8")).hexdigest()


def generate_conflict_ticket_key() -> str:
    return f"c1_{secrets.token_urlsafe(32)}"


def hash_conflict_ticket_key(raw_conflict_ticket: str) -> str:
    return hashlib.sha256(raw_conflict_ticket.encode("utf-8")).hexdigest()

