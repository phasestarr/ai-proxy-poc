from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatDraftFile, ChatHistoryFile
from app.db.postgres.models.chat_history import ChatDraft, ChatHistory, ChatOperation
from app.db.postgres.models.chat_history import ChatMessage
from app.services.chat.errors import ChatHistoryNotFoundError, ChatProxyError

TERMINAL_OPERATION_STATES = {"succeeded", "failed", "timed_out"}
LIVE_OPERATION_STATES = {"running", "provider_streaming"}
OPERATION_RUNNING = "running"
OPERATION_PROVIDER_STREAMING = "provider_streaming"


class ChatOperationConflictError(RuntimeError):
    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("chat operation already in progress")


class ChatOperationExpiredError(RuntimeError):
    """Raised when an async task no longer owns its persisted operation."""


@dataclass(slots=True, frozen=True)
class OperationHandle:
    id: str
    owner_token: str
    operation_type: str
    chat_history_id: str | None = None
    draft_id: str | None = None


@dataclass(slots=True, frozen=True)
class ProviderHeartbeatResult:
    operation: ChatOperation
    persisted: bool


def begin_history_operation(
    db: Session,
    *,
    session: SessionContext,
    history_id: str,
    operation_type: str,
    timeout_seconds: int | None = None,
) -> OperationHandle:
    history = db.get(ChatHistory, history_id, with_for_update=True)
    if history is None or history.user_id != session.user_id:
        raise ChatHistoryNotFoundError("chat history not found")

    _recover_expired_active_operation(db, history=history)
    if history.active_operation_id:
        raise ChatOperationConflictError(retry_after_seconds=_retry_after_for_active_operation(db, history.active_operation_id))

    operation = _create_operation(
        db,
        session=session,
        chat_history_id=history.id,
        draft_id=None,
        operation_type=operation_type,
        timeout_seconds=timeout_seconds or validating_timeout_seconds(),
    )
    history.active_operation_id = operation.id
    history.active_operation_token = operation.owner_token
    if operation_type == "delete_history":
        history.lifecycle_state = "deleting"
    history.updated_at = utc_now()
    db.commit()
    return _handle(operation)


def begin_new_history_send_operation(
    db: Session,
    *,
    session: SessionContext,
    title: str,
    timeout_seconds: int | None = None,
) -> tuple[ChatHistory, OperationHandle]:
    now = utc_now()
    history = ChatHistory(
        id=str(uuid4()),
        user_id=session.user_id,
        title=title,
        lifecycle_state="active",
        created_at=now,
        updated_at=now,
    )
    db.add(history)
    db.flush()
    operation = _create_operation(
        db,
        session=session,
        chat_history_id=history.id,
        draft_id=None,
        operation_type="send",
        timeout_seconds=timeout_seconds or validating_timeout_seconds(),
    )
    history.active_operation_id = operation.id
    history.active_operation_token = operation.owner_token
    db.commit()
    return history, _handle(operation)


def begin_draft_operation(
    db: Session,
    *,
    session: SessionContext,
    operation_type: str,
    timeout_seconds: int | None = None,
) -> tuple[ChatDraft, OperationHandle]:
    now = utc_now()
    _recover_expired_session_draft_operations(db, session=session)
    active_draft_operation = _load_active_session_draft_operation(db, session=session)
    if active_draft_operation is not None:
        raise ChatOperationConflictError(
            retry_after_seconds=_retry_after_for_active_operation(db, active_draft_operation.id)
        )

    draft = ChatDraft(
        id=str(uuid4()),
        user_id=session.user_id,
        lifecycle_state="active",
        expires_at=now + timedelta(seconds=draft_ttl_seconds()),
        created_at=now,
        updated_at=now,
    )
    db.add(draft)
    db.flush()

    _recover_expired_active_operation(db, draft=draft)
    if draft.active_operation_id:
        raise ChatOperationConflictError(retry_after_seconds=_retry_after_for_active_operation(db, draft.active_operation_id))

    operation = _create_operation(
        db,
        session=session,
        chat_history_id=None,
        draft_id=draft.id,
        operation_type=operation_type,
        timeout_seconds=timeout_seconds or validating_timeout_seconds(),
    )
    draft.active_operation_id = operation.id
    draft.active_operation_token = operation.owner_token
    draft.updated_at = utc_now()
    db.commit()
    return draft, _handle(operation)


def assert_operation_current(
    db: Session,
    handle: OperationHandle,
    *,
    allow_expired: bool = False,
) -> ChatOperation:
    operation = db.get(ChatOperation, handle.id)
    if operation is None or operation.owner_token != handle.owner_token or operation.state in TERMINAL_OPERATION_STATES:
        raise ChatOperationExpiredError("chat operation is no longer current")
    now = utc_now()
    if not allow_expired and (
        operation.deadline_at <= now
        or (operation.provider_max_deadline_at is not None and operation.provider_max_deadline_at <= now)
    ):
        raise ChatOperationExpiredError("chat operation deadline has expired")
    if operation.chat_history_id is not None:
        history = db.get(ChatHistory, operation.chat_history_id)
        if (
            history is None
            or history.active_operation_id != operation.id
            or history.active_operation_token != operation.owner_token
        ):
            raise ChatOperationExpiredError("chat operation no longer owns the history")
    else:
        draft = db.get(ChatDraft, operation.draft_id)
        if (
            draft is None
            or draft.active_operation_id != operation.id
            or draft.active_operation_token != operation.owner_token
        ):
            raise ChatOperationExpiredError("chat operation no longer owns the draft")
    return operation


def reassign_operation_to_history(
    db: Session,
    handle: OperationHandle,
    *,
    history: ChatHistory,
    draft: ChatDraft | None = None,
) -> OperationHandle:
    operation = assert_operation_current(db, handle)
    now = utc_now()
    if draft is not None:
        if draft.active_operation_id == operation.id and draft.active_operation_token == operation.owner_token:
            draft.active_operation_id = None
            draft.active_operation_token = None
        operation.draft_id = None

    operation.chat_history_id = history.id
    operation.updated_at = now
    history.active_operation_id = operation.id
    history.active_operation_token = operation.owner_token
    history.updated_at = now
    db.flush()
    if draft is not None:
        db.delete(draft)
        db.flush()
    return _handle(operation)


def transition_operation(
    db: Session,
    handle: OperationHandle,
    *,
    state: str,
    timeout_seconds: int | None = None,
    provider_max_seconds: int | None = None,
) -> ChatOperation:
    operation = assert_operation_current(db, handle)
    now = utc_now()
    operation.state = state
    operation.updated_at = now
    if timeout_seconds is not None:
        operation.deadline_at = now + timedelta(seconds=max(1, timeout_seconds))
    if state == OPERATION_PROVIDER_STREAMING:
        operation.provider_started_at = operation.provider_started_at or now
        operation.last_provider_event_at = operation.last_provider_event_at or now
        operation.provider_max_deadline_at = now + timedelta(
            seconds=max(1, provider_max_seconds or provider_max_runtime_seconds())
        )
    db.commit()
    return operation


def record_provider_event_heartbeat(db: Session, handle: OperationHandle) -> ProviderHeartbeatResult:
    operation = assert_operation_current(db, handle)
    now = utc_now()
    last_persisted_event_at = operation.last_provider_event_at
    first_event = operation.first_provider_event_at is None
    heartbeat_due = (
        last_persisted_event_at is None
        or (now - last_persisted_event_at).total_seconds() >= provider_heartbeat_interval_seconds()
    )
    if not first_event and not heartbeat_due and operation.state == OPERATION_PROVIDER_STREAMING:
        return ProviderHeartbeatResult(operation=operation, persisted=False)

    if operation.state != OPERATION_PROVIDER_STREAMING:
        operation.state = OPERATION_PROVIDER_STREAMING
        operation.provider_started_at = operation.provider_started_at or now
        operation.provider_max_deadline_at = operation.provider_max_deadline_at or (
            now + timedelta(seconds=provider_max_runtime_seconds())
        )
    operation.first_provider_event_at = operation.first_provider_event_at or now
    operation.last_provider_event_at = now
    operation.deadline_at = now + timedelta(seconds=provider_event_idle_timeout_seconds())
    operation.updated_at = now
    return ProviderHeartbeatResult(operation=operation, persisted=True)


def promote_draft_to_history(
    db: Session,
    *,
    draft: ChatDraft,
    title: str,
) -> ChatHistory:
    now = utc_now()
    history = ChatHistory(
        id=draft.id,
        user_id=draft.user_id,
        title=title,
        lifecycle_state="active",
        created_at=now,
        updated_at=now,
    )
    db.add(history)
    db.flush()

    draft_files = db.execute(
        select(ChatDraftFile).where(
            ChatDraftFile.draft_id == draft.id,
            ChatDraftFile.user_id == draft.user_id,
        )
        .order_by(ChatDraftFile.created_at.asc(), ChatDraftFile.id.asc())
    ).scalars().all()
    for draft_file in draft_files:
        db.add(
            ChatHistoryFile(
                id=draft_file.id,
                user_id=draft_file.user_id,
                chat_history_id=history.id,
                stored_file_id=draft_file.stored_file_id,
                display_name=draft_file.display_name,
                mime_type=draft_file.mime_type,
                byte_size=draft_file.byte_size,
                is_active=draft_file.is_active,
                created_at=draft_file.created_at,
                updated_at=now,
            )
        )
        db.delete(draft_file)
    db.flush()
    return history


def complete_operation(
    db: Session,
    handle: OperationHandle,
    *,
    state: str = "succeeded",
    result_code: str | None = None,
    error_detail: str | None = None,
    clear_scope: bool = True,
    allow_expired: bool = False,
    commit: bool = True,
) -> bool:
    try:
        operation = assert_operation_current(db, handle, allow_expired=allow_expired)
    except ChatOperationExpiredError:
        return False
    now = utc_now()
    operation.state = state
    operation.result_code = result_code
    operation.error_detail = error_detail
    operation.completed_at = now
    operation.updated_at = now
    if clear_scope:
        _clear_scope_owner(db, operation)
    if commit:
        db.commit()
    return True


def delete_empty_history_for_operation(db: Session, handle: OperationHandle) -> bool:
    operation = db.get(ChatOperation, handle.id)
    if operation is None or operation.owner_token != handle.owner_token or operation.chat_history_id is None:
        return False
    history = db.get(ChatHistory, operation.chat_history_id)
    if history is None:
        return False
    message_count = int(
        db.execute(select(func.count(ChatMessage.id)).where(ChatMessage.chat_history_id == history.id)).scalar_one()
        or 0
    )
    file_count = int(
        db.execute(select(func.count(ChatHistoryFile.id)).where(ChatHistoryFile.chat_history_id == history.id)).scalar_one()
        or 0
    )
    if message_count or file_count:
        return False
    db.delete(history)
    db.commit()
    return True


def fail_operation_from_error(db: Session, handle: OperationHandle, error: ChatProxyError) -> bool:
    return complete_operation(
        db,
        handle,
        state="failed",
        result_code=error.code,
        error_detail=error.detail,
    )


def validating_timeout_seconds() -> int:
    return max(1, settings.chat_validating_operation_timeout_seconds)


def provider_event_idle_timeout_seconds() -> int:
    return max(1, settings.chat_provider_event_idle_timeout_seconds)


def provider_max_runtime_seconds() -> int:
    return max(1, settings.chat_provider_max_runtime_seconds)


def provider_heartbeat_interval_seconds() -> int:
    return max(1, min(30, provider_event_idle_timeout_seconds() // 3 or 1))


def draft_ttl_seconds() -> int:
    return max(1, settings.chat_draft_ttl_seconds)


def _create_operation(
    db: Session,
    *,
    session: SessionContext,
    chat_history_id: str | None,
    draft_id: str | None,
    operation_type: str,
    timeout_seconds: int,
) -> ChatOperation:
    now = utc_now()
    operation = ChatOperation(
        id=str(uuid4()),
        user_id=session.user_id,
        auth_session_id=session.session_id,
        chat_history_id=chat_history_id,
        draft_id=draft_id,
        operation_type=operation_type,
        state=OPERATION_RUNNING,
        owner_token=secrets.token_urlsafe(24),
        deadline_at=now + timedelta(seconds=max(1, timeout_seconds)),
        created_at=now,
        updated_at=now,
    )
    db.add(operation)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ChatOperationConflictError(retry_after_seconds=validating_timeout_seconds()) from exc
    return operation


def _handle(operation: ChatOperation) -> OperationHandle:
    return OperationHandle(
        id=operation.id,
        owner_token=operation.owner_token,
        operation_type=operation.operation_type,
        chat_history_id=operation.chat_history_id,
        draft_id=operation.draft_id,
    )


def _recover_expired_active_operation(
    db: Session,
    *,
    history: ChatHistory | None = None,
    draft: ChatDraft | None = None,
) -> None:
    owner = history or draft
    if owner is None or not owner.active_operation_id:
        return
    operation = db.get(ChatOperation, owner.active_operation_id)
    now = utc_now()
    if operation is None:
        owner.active_operation_id = None
        owner.active_operation_token = None
        return
    max_deadline = operation.provider_max_deadline_at
    deadline_passed = operation.deadline_at <= now
    max_deadline_passed = max_deadline is not None and max_deadline <= now
    if operation.state in TERMINAL_OPERATION_STATES or deadline_passed or max_deadline_passed:
        operation.state = "timed_out" if operation.state not in TERMINAL_OPERATION_STATES else operation.state
        operation.result_code = operation.result_code or "chat_operation_timeout"
        operation.completed_at = operation.completed_at or now
        operation.updated_at = now
        owner.active_operation_id = None
        owner.active_operation_token = None
        if isinstance(owner, ChatHistory) and owner.lifecycle_state == "deleting":
            owner.lifecycle_state = "active"
        owner.updated_at = now


def _recover_expired_session_draft_operations(db: Session, *, session: SessionContext) -> None:
    if not session.session_id:
        return
    operations = db.execute(
        select(ChatOperation)
        .where(
            ChatOperation.user_id == session.user_id,
            ChatOperation.auth_session_id == session.session_id,
            ChatOperation.operation_type == "attach_file",
            ChatOperation.draft_id.is_not(None),
            ChatOperation.state.in_(tuple(LIVE_OPERATION_STATES)),
        )
        .order_by(ChatOperation.created_at.asc(), ChatOperation.id.asc())
    ).scalars().all()
    for operation in operations:
        draft = db.get(ChatDraft, operation.draft_id, with_for_update=True)
        if draft is not None:
            _recover_expired_active_operation(db, draft=draft)


def _load_active_session_draft_operation(db: Session, *, session: SessionContext) -> ChatOperation | None:
    if not session.session_id:
        return None
    now = utc_now()
    return db.execute(
        select(ChatOperation)
        .where(
            ChatOperation.user_id == session.user_id,
            ChatOperation.auth_session_id == session.session_id,
            ChatOperation.operation_type == "attach_file",
            ChatOperation.draft_id.is_not(None),
            ChatOperation.state.in_(tuple(LIVE_OPERATION_STATES)),
            ChatOperation.deadline_at > now,
            or_(
                ChatOperation.provider_max_deadline_at.is_(None),
                ChatOperation.provider_max_deadline_at > now,
            ),
        )
        .order_by(ChatOperation.created_at.asc(), ChatOperation.id.asc())
    ).scalars().first()


def _retry_after_for_active_operation(db: Session, operation_id: str) -> int:
    operation = db.get(ChatOperation, operation_id)
    if operation is None:
        return validating_timeout_seconds()
    remaining = (operation.deadline_at - utc_now()).total_seconds()
    if operation.provider_max_deadline_at is not None:
        remaining = min(remaining, (operation.provider_max_deadline_at - utc_now()).total_seconds())
    return max(1, int(remaining))


def _clear_scope_owner(db: Session, operation: ChatOperation) -> None:
    if operation.chat_history_id is not None:
        history = db.get(ChatHistory, operation.chat_history_id)
        if history is not None and history.active_operation_id == operation.id and history.active_operation_token == operation.owner_token:
            history.active_operation_id = None
            history.active_operation_token = None
            if history.lifecycle_state == "deleting":
                history.lifecycle_state = "active"
            history.updated_at = utc_now()
    else:
        draft = db.get(ChatDraft, operation.draft_id)
        if draft is not None and draft.active_operation_id == operation.id and draft.active_operation_token == operation.owner_token:
            draft.active_operation_id = None
            draft.active_operation_token = None
            draft.updated_at = utc_now()
