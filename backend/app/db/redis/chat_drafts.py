from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from redis.exceptions import RedisError

from app.config.settings import settings
from app.config.time import utc_now
from app.db.redis.client import get_redis_client
from app.services.chat.histories.state import INTERACTION_STATE_READY

DRAFT_KEY_PREFIX = "ai-proxy:chat:draft"


class ChatDraftUnavailableError(RuntimeError):
    """Raised when Redis-backed draft storage cannot run."""


@dataclass(slots=True, frozen=True)
class ChatDraft:
    draft_chat_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    interaction_state: str
    busy_reason: str | None = None


def create_chat_draft(*, user_id: str) -> ChatDraft:
    now = utc_now()
    draft_chat_id = str(uuid4())
    expires_at = now + timedelta(seconds=settings.chat_draft_ttl_seconds)
    draft = ChatDraft(
        draft_chat_id=draft_chat_id,
        user_id=user_id,
        created_at=now,
        expires_at=expires_at,
        interaction_state=INTERACTION_STATE_READY,
        busy_reason=None,
    )

    try:
        get_redis_client().set(
            _build_draft_key(draft_chat_id=draft_chat_id),
            _serialize_chat_draft(draft),
            ex=max(1, settings.chat_draft_ttl_seconds),
        )
    except RedisError as exc:
        raise ChatDraftUnavailableError("chat draft backend is unavailable") from exc

    return draft


def load_chat_draft(*, draft_chat_id: str) -> ChatDraft | None:
    try:
        raw_payload = get_redis_client().get(_build_draft_key(draft_chat_id=draft_chat_id))
    except RedisError as exc:
        raise ChatDraftUnavailableError("chat draft backend is unavailable") from exc

    if not raw_payload:
        return None

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    created_at_raw = payload.get("created_at")
    user_id = payload.get("user_id")
    interaction_state = payload.get("interaction_state")
    busy_reason = payload.get("busy_reason")
    if not isinstance(created_at_raw, str) or not isinstance(user_id, str) or not user_id.strip():
        return None

    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError:
        return None

    ttl_seconds = get_chat_draft_ttl_seconds(draft_chat_id=draft_chat_id)
    expires_at = utc_now() + timedelta(seconds=ttl_seconds)
    return ChatDraft(
        draft_chat_id=draft_chat_id,
        user_id=user_id.strip(),
        created_at=created_at,
        expires_at=expires_at,
        interaction_state=interaction_state.strip() if isinstance(interaction_state, str) and interaction_state.strip() else INTERACTION_STATE_READY,
        busy_reason=busy_reason.strip() if isinstance(busy_reason, str) and busy_reason.strip() else None,
    )


def refresh_chat_draft(*, draft_chat_id: str) -> bool:
    try:
        refreshed = get_redis_client().expire(
            _build_draft_key(draft_chat_id=draft_chat_id),
            max(1, settings.chat_draft_ttl_seconds),
        )
    except RedisError as exc:
        raise ChatDraftUnavailableError("chat draft backend is unavailable") from exc
    return bool(refreshed)


def set_chat_draft_state(
    *,
    draft_chat_id: str,
    interaction_state: str,
    busy_reason: str | None = None,
) -> bool:
    draft = load_chat_draft(draft_chat_id=draft_chat_id)
    if draft is None:
        return False

    next_draft = ChatDraft(
        draft_chat_id=draft.draft_chat_id,
        user_id=draft.user_id,
        created_at=draft.created_at,
        expires_at=draft.expires_at,
        interaction_state=interaction_state,
        busy_reason=busy_reason,
    )
    ttl_seconds = get_chat_draft_ttl_seconds(draft_chat_id=draft_chat_id)
    try:
        get_redis_client().set(
            _build_draft_key(draft_chat_id=draft_chat_id),
            _serialize_chat_draft(next_draft),
            ex=max(1, ttl_seconds),
        )
    except RedisError as exc:
        raise ChatDraftUnavailableError("chat draft backend is unavailable") from exc
    return True


def delete_chat_draft(*, draft_chat_id: str) -> None:
    try:
        get_redis_client().delete(_build_draft_key(draft_chat_id=draft_chat_id))
    except RedisError:
        return


def get_chat_draft_ttl_seconds(*, draft_chat_id: str) -> int:
    try:
        ttl_seconds = get_redis_client().ttl(_build_draft_key(draft_chat_id=draft_chat_id))
    except RedisError as exc:
        raise ChatDraftUnavailableError("chat draft backend is unavailable") from exc

    if ttl_seconds is None or ttl_seconds <= 0:
        return max(1, settings.chat_draft_ttl_seconds)
    return ttl_seconds


def _build_draft_key(*, draft_chat_id: str) -> str:
    return f"{DRAFT_KEY_PREFIX}:{draft_chat_id}"


def _serialize_chat_draft(draft: ChatDraft) -> bytes:
    payload = json.dumps(
        {
            "draft_chat_id": draft.draft_chat_id,
            "user_id": draft.user_id,
            "created_at": draft.created_at.isoformat(),
            "interaction_state": draft.interaction_state,
            "busy_reason": draft.busy_reason,
        }
    )
    return payload.encode("utf-8")
