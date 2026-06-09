"""
Purpose:
- Define chat completion related HTTP endpoints.

Responsibilities:
- Accept chat requests from the frontend
- Validate input payloads through schemas
- Delegate processing to the chat service layer
- Return server-sent event streams to the client

Flow:
- router -> schema validation -> service -> response

Notes:
- This file is intentionally thin.
- Provider-specific implementation must live outside the router layer.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.session import require_authenticated_session, require_capability
from app.api.v1.dependencies.db import get_db
from app.api.v1.presenters.chat import (
    build_attachment_limits_view,
    build_chat_history_file_view,
    build_chat_history_message_view,
    build_chat_history_summary,
)
from app.db.redis.chat_coordination import (
    ChatCoordinationUnavailableError,
    ChatRequestInProgressError,
    acquire_chat_execution_lease,
    release_chat_execution_lease,
)
from app.db.redis.chat_drafts import ChatDraftUnavailableError, create_chat_draft, load_chat_draft, set_chat_draft_state
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatDraftEnvelope,
    ChatDraftView,
    ChatHistoryFilesEnvelope,
    ChatHistoryEnvelope,
    ChatHistoryListEnvelope,
    ChatHistoryFileUpdateRequest,
    ChatHistorySummary,
    ChatHistoryTitleUpdateRequest,
)
from app.services.chat.attachments import (
    ChatHistoryDuplicateFileError,
    ChatHistoryFileNotFoundError,
    attach_file_to_history,
    delete_file_from_history,
    delete_history_with_files,
    get_history_file,
    list_history_files,
    update_history_file_activation,
)
from app.services.chat.completions.orchestrator import (
    ChatHistoryUnavailableError,
    create_chat_completion_stream,
)
from app.services.chat.completions.request_audit import persist_chat_proxy_rejection
from app.services.chat.errors import ChatHistoryNotFoundError, ChatProxyError
from app.services.chat.histories.service import (
    get_chat_history,
    list_chat_histories,
    load_user_history,
    pin_chat_history,
    unpin_chat_history,
    update_chat_history_title,
)
from app.services.chat.histories.state import (
    BUSY_REASON_ATTACH_FILE,
    BUSY_REASON_DELETE_FILE,
    BUSY_REASON_DELETE_HISTORY,
    INTERACTION_STATE_READY,
    INTERACTION_STATE_VALIDATING,
    apply_history_interaction_state,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/histories", response_model=ChatHistoryListEnvelope)
def list_histories(
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistoryListEnvelope:
    return ChatHistoryListEnvelope(
        histories=[
            build_chat_history_summary(history, message_count, attachment_count)
            for history, message_count, attachment_count in list_chat_histories(db, user_id=session.user_id)
        ],
        attachment_limits=build_attachment_limits_view(),
    )


@router.post("/drafts", response_model=ChatDraftEnvelope, status_code=status.HTTP_201_CREATED)
def create_draft(
    session=Depends(require_authenticated_session),
) -> ChatDraftEnvelope:
    try:
        draft = create_chat_draft(user_id=session.user_id)
    except ChatDraftUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="chat draft backend is unavailable",
        ) from exc

    return ChatDraftEnvelope(
        draft=ChatDraftView(
            draft_chat_id=draft.draft_chat_id,
            expires_at=draft.expires_at,
            interaction_state=draft.interaction_state,
            busy_reason=draft.busy_reason,
        ),
        attachment_limits=build_attachment_limits_view(),
    )


@router.get("/drafts/{draft_chat_id}", response_model=ChatDraftEnvelope)
def get_draft(
    draft_chat_id: str,
    session=Depends(require_authenticated_session),
) -> ChatDraftEnvelope:
    try:
        draft = load_chat_draft(draft_chat_id=draft_chat_id)
    except ChatDraftUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="chat draft backend is unavailable",
        ) from exc

    if draft is None or draft.user_id != session.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat draft not found")

    return ChatDraftEnvelope(
        draft=ChatDraftView(
            draft_chat_id=draft.draft_chat_id,
            expires_at=draft.expires_at,
            interaction_state=draft.interaction_state,
            busy_reason=draft.busy_reason,
        ),
        attachment_limits=build_attachment_limits_view(),
    )


@router.get("/histories/{history_id}", response_model=ChatHistoryEnvelope)
def get_history(
    history_id: str,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistoryEnvelope:
    try:
        history, messages = get_chat_history(db, user_id=session.user_id, history_id=history_id)
    except ChatHistoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc
    files = list_history_files(db, user_id=session.user_id, history_id=history.id)

    return ChatHistoryEnvelope(
        history=build_chat_history_summary(history, len(messages), len(files)),
        files=[build_chat_history_file_view(history_file) for history_file in files],
        messages=[build_chat_history_message_view(message) for message in messages],
        attachment_limits=build_attachment_limits_view(),
    )


@router.patch("/histories/{history_id}/title", response_model=ChatHistorySummary)
def update_history_title(
    history_id: str,
    payload: ChatHistoryTitleUpdateRequest,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistorySummary:
    try:
        history = update_chat_history_title(
            db,
            user_id=session.user_id,
            history_id=history_id,
            title=payload.title,
        )
    except ChatHistoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc

    return build_chat_history_summary(history, len(history.messages), len(history.files))


@router.put("/histories/{history_id}/pin", response_model=ChatHistorySummary)
def pin_history(
    history_id: str,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistorySummary:
    try:
        history = pin_chat_history(db, user_id=session.user_id, history_id=history_id)
    except ChatHistoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc

    return build_chat_history_summary(history, len(history.messages), len(history.files))


@router.delete("/histories/{history_id}/pin", response_model=ChatHistorySummary)
def unpin_history(
    history_id: str,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistorySummary:
    try:
        history = unpin_chat_history(db, user_id=session.user_id, history_id=history_id)
    except ChatHistoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc

    return build_chat_history_summary(history, len(history.messages), len(history.files))


@router.post("/files", response_model=ChatHistoryFilesEnvelope, status_code=status.HTTP_201_CREATED)
async def upload_history_file(
    chat_history_id: str | None = Form(default=None),
    draft_chat_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistoryFilesEnvelope:
    normalized_history_id = (chat_history_id or "").strip() or None
    normalized_draft_id = (draft_chat_id or "").strip() or None
    if bool(normalized_history_id) == bool(normalized_draft_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exactly one of chat_history_id or draft_chat_id is required")

    lease = None
    try:
        lease = acquire_chat_execution_lease(chat_history_id=normalized_history_id or normalized_draft_id or "")
        _mark_upload_target_validating(
            db=db,
            user_id=session.user_id,
            history_id=normalized_history_id,
            draft_chat_id=normalized_draft_id,
        )
        history, files = await attach_file_to_history(
            db,
            user_id=session.user_id,
            history_id=normalized_history_id,
            draft_chat_id=normalized_draft_id,
            upload=file,
        )
    except ChatRequestInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"chat operation already in progress; retry after {exc.retry_after_seconds} seconds",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ChatCoordinationUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="chat coordination backend is unavailable") from exc
    except ChatHistoryNotFoundError as exc:
        _reset_upload_target_ready(
            db=db,
            user_id=session.user_id,
            history_id=normalized_history_id,
            draft_chat_id=normalized_draft_id,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc
    except ChatHistoryDuplicateFileError as exc:
        _reset_upload_target_ready(
            db=db,
            user_id=session.user_id,
            history_id=normalized_history_id,
            draft_chat_id=normalized_draft_id,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        _reset_upload_target_ready(
            db=db,
            user_id=session.user_id,
            history_id=normalized_history_id,
            draft_chat_id=normalized_draft_id,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        _reset_upload_target_ready(
            db=db,
            user_id=session.user_id,
            history_id=normalized_history_id,
            draft_chat_id=normalized_draft_id,
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception:
        _reset_upload_target_ready(
            db=db,
            user_id=session.user_id,
            history_id=normalized_history_id,
            draft_chat_id=normalized_draft_id,
        )
        raise
    finally:
        release_chat_execution_lease(lease)

    return ChatHistoryFilesEnvelope(
        history=build_chat_history_summary(history, len(history.messages), len(files)),
        files=[build_chat_history_file_view(history_file) for history_file in files],
        deleted_history_id=None,
        attachment_limits=build_attachment_limits_view(),
    )


@router.delete("/histories/{history_id}/files/{file_id}", response_model=ChatHistoryFilesEnvelope)
async def delete_history_file(
    history_id: str,
    file_id: str,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistoryFilesEnvelope:
    lease = None
    try:
        lease = acquire_chat_execution_lease(chat_history_id=history_id)
        _set_history_busy_state(
            db=db,
            user_id=session.user_id,
            history_id=history_id,
            interaction_state=INTERACTION_STATE_VALIDATING,
            busy_reason=BUSY_REASON_DELETE_FILE,
        )
        history, files, deleted_history_id = await delete_file_from_history(
            db,
            user_id=session.user_id,
            history_id=history_id,
            file_id=file_id,
        )
    except ChatRequestInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"chat operation already in progress; retry after {exc.retry_after_seconds} seconds",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ChatCoordinationUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="chat coordination backend is unavailable") from exc
    except ChatHistoryNotFoundError as exc:
        _set_history_busy_state(
            db=db,
            user_id=session.user_id,
            history_id=history_id,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc
    except ChatHistoryFileNotFoundError as exc:
        _set_history_busy_state(
            db=db,
            user_id=session.user_id,
            history_id=history_id,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat file not found") from exc
    except Exception:
        _set_history_busy_state(
            db=db,
            user_id=session.user_id,
            history_id=history_id,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        raise
    finally:
        release_chat_execution_lease(lease)

    return ChatHistoryFilesEnvelope(
        history=build_chat_history_summary(history, len(history.messages), len(files)) if history is not None else None,
        files=[build_chat_history_file_view(history_file) for history_file in files],
        deleted_history_id=deleted_history_id,
        attachment_limits=build_attachment_limits_view(),
    )


@router.patch("/histories/{history_id}/files/{file_id}", response_model=ChatHistoryFilesEnvelope)
async def update_history_file(
    history_id: str,
    file_id: str,
    payload: ChatHistoryFileUpdateRequest,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistoryFilesEnvelope:
    lease = None
    try:
        lease = acquire_chat_execution_lease(chat_history_id=history_id)
        history, files = update_history_file_activation(
            db,
            user_id=session.user_id,
            history_id=history_id,
            file_id=file_id,
            is_active=payload.is_active,
        )
    except ChatRequestInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"chat operation already in progress; retry after {exc.retry_after_seconds} seconds",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ChatCoordinationUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="chat coordination backend is unavailable") from exc
    except ChatHistoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc
    except ChatHistoryFileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat file not found") from exc
    finally:
        release_chat_execution_lease(lease)

    return ChatHistoryFilesEnvelope(
        history=build_chat_history_summary(history, len(history.messages), len(files)),
        files=[build_chat_history_file_view(history_file) for history_file in files],
        deleted_history_id=None,
        attachment_limits=build_attachment_limits_view(),
    )


@router.get("/histories/{history_id}/files/{file_id}/content")
def get_history_file_content(
    history_id: str,
    file_id: str,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> Response:
    history_file = get_history_file(
        db,
        user_id=session.user_id,
        history_id=history_id,
        file_id=file_id,
    )
    if history_file is None or history_file.stored_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat file not found")

    safe_filename = history_file.display_name.replace('"', "")
    return Response(
        content=history_file.stored_file.content,
        media_type=history_file.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{safe_filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.delete("/histories/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history(
    history_id: str,
    response: Response,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> Response:
    lease = None
    try:
        lease = acquire_chat_execution_lease(chat_history_id=history_id)
        _set_history_busy_state(
            db=db,
            user_id=session.user_id,
            history_id=history_id,
            interaction_state=INTERACTION_STATE_VALIDATING,
            busy_reason=BUSY_REASON_DELETE_HISTORY,
        )
        await delete_history_with_files(db, user_id=session.user_id, history_id=history_id)
    except ChatRequestInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"chat operation already in progress; retry after {exc.retry_after_seconds} seconds",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ChatCoordinationUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="chat coordination backend is unavailable") from exc
    except ChatHistoryNotFoundError as exc:
        _set_history_busy_state(
            db=db,
            user_id=session.user_id,
            history_id=history_id,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc
    except Exception:
        _set_history_busy_state(
            db=db,
            user_id=session.user_id,
            history_id=history_id,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        raise
    finally:
        release_chat_execution_lease(lease)

    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    session=Depends(require_capability("chat:send")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        event_stream = create_chat_completion_stream(payload, session=session, db=db)
    except ChatProxyError as exc:
        persist_chat_proxy_rejection(
            db,
            session=session,
            payload=payload,
            error=exc,
        )
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        raise HTTPException(
            status_code=exc.http_status or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.result_message,
            headers=headers or None,
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ChatHistoryUnavailableError as exc:
        persist_chat_proxy_rejection(
            db,
            session=session,
            payload=payload,
            error=ChatProxyError(
                code="chat_history_not_found",
                origin="proxy",
                detail=str(exc),
                http_status=status.HTTP_404_NOT_FOUND,
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return StreamingResponse(
        event_stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _mark_upload_target_validating(
    *,
    db: Session,
    user_id: str,
    history_id: str | None,
    draft_chat_id: str | None,
) -> None:
    if draft_chat_id:
        promoted_history = load_user_history(
            db,
            user_id=user_id,
            history_id=draft_chat_id,
        )
        if promoted_history is not None:
            apply_history_interaction_state(
                promoted_history,
                interaction_state=INTERACTION_STATE_VALIDATING,
                busy_reason=BUSY_REASON_ATTACH_FILE,
            )
            db.commit()
            return
        set_chat_draft_state(
            draft_chat_id=draft_chat_id,
            interaction_state=INTERACTION_STATE_VALIDATING,
            busy_reason=BUSY_REASON_ATTACH_FILE,
        )
        return
    _set_history_busy_state(
        db=db,
        user_id=user_id,
        history_id=history_id,
        interaction_state=INTERACTION_STATE_VALIDATING,
        busy_reason=BUSY_REASON_ATTACH_FILE,
    )


def _reset_upload_target_ready(
    *,
    db: Session,
    user_id: str,
    history_id: str | None,
    draft_chat_id: str | None,
) -> None:
    if draft_chat_id:
        promoted_history = load_user_history(
            db,
            user_id=user_id,
            history_id=draft_chat_id,
        )
        if promoted_history is not None:
            apply_history_interaction_state(
                promoted_history,
                interaction_state=INTERACTION_STATE_READY,
                busy_reason=None,
            )
            db.commit()
            return
        set_chat_draft_state(
            draft_chat_id=draft_chat_id,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        return
    _set_history_busy_state(
        db=db,
        user_id=user_id,
        history_id=history_id,
        interaction_state=INTERACTION_STATE_READY,
        busy_reason=None,
    )


def _set_history_busy_state(
    *,
    db: Session,
    user_id: str,
    history_id: str | None,
    interaction_state: str,
    busy_reason: str | None,
) -> None:
    history = load_user_history(
        db,
        user_id=user_id,
        history_id=history_id,
    )
    if history is None:
        return
    apply_history_interaction_state(
        history,
        interaction_state=interaction_state,
        busy_reason=busy_reason,
    )
    db.commit()
