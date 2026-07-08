"""
Purpose:
- Define chat completion related HTTP endpoints.

Responsibilities:
- Accept chat requests from the frontend
- Validate input payloads through schemas
- Delegate processing to the chat service layer
- Return server-sent event streams to the client
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.db import get_db
from app.api.v1.dependencies.session import require_authenticated_session, require_capability
from app.api.v1.presenters.chat import (
    build_attachment_limits_view,
    build_chat_history_file_view,
    build_chat_history_message_view,
    build_chat_history_summary,
)
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatHistoryEnvelope,
    ChatHistoryFilesEnvelope,
    ChatHistoryFileUpdateRequest,
    ChatHistoryListEnvelope,
    ChatHistorySummary,
    ChatHistoryTitleUpdateRequest,
)
from app.services.chat.attachments import (
    ChatHistoryDuplicateFileError,
    ChatHistoryFileNotFoundError,
    attach_file_to_history,
    delete_file_from_history,
    delete_history_with_files,
    discard_draft_with_files,
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
    pin_chat_history,
    unpin_chat_history,
    update_chat_history_title,
)
from app.services.chat.operations import (
    ChatOperationConflictError,
    ChatOperationExpiredError,
    OperationHandle,
    begin_draft_operation,
    begin_history_operation,
    complete_operation,
    promote_draft_to_history,
    reassign_operation_to_history,
    validating_timeout_seconds,
)
from app.services.chat.attachments.validation import build_history_title_from_filename

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
    request: Request,
    chat_history_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistoryFilesEnvelope:
    normalized_history_id = (chat_history_id or "").strip() or None
    form_keys = set((await request.form()).keys())
    unsupported_form_keys = form_keys - {"chat_history_id", "file"}
    if unsupported_form_keys:
        unsupported = sorted(unsupported_form_keys)[0]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unsupported form field: {unsupported}",
        )

    operation: OperationHandle | None = None
    staging_draft_id: str | None = None
    try:
        if normalized_history_id:
            operation = begin_history_operation(
                db,
                session=session,
                history_id=normalized_history_id,
                operation_type="attach_file",
                timeout_seconds=validating_timeout_seconds(),
            )
        else:
            draft, operation = begin_draft_operation(
                db,
                session=session,
                operation_type="attach_file",
                timeout_seconds=validating_timeout_seconds(),
            )
            staging_draft_id = draft.id
        history, draft, files = await asyncio.wait_for(
            attach_file_to_history(
                db,
                user_id=session.user_id,
                history_id=normalized_history_id,
                staging_draft_id=staging_draft_id,
                upload=file,
                operation=operation,
            ),
            timeout=validating_timeout_seconds(),
        )
        if draft is not None:
            title = build_history_title_from_filename(files[0].display_name if files else "")
            history = promote_draft_to_history(
                db,
                draft=draft,
                title=title,
            )
            operation = reassign_operation_to_history(db, operation, history=history, draft=draft)
            staging_draft_id = None
            files = list_history_files(db, user_id=session.user_id, history_id=history.id)
        complete_operation(db, operation, state="succeeded", allow_expired=True)
    except asyncio.TimeoutError as exc:
        _rollback_and_timeout(db, operation)
        await _cleanup_staging_draft(db, user_id=session.user_id, draft_id=staging_draft_id)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="chat validation took too long") from exc
    except ChatOperationConflictError as exc:
        raise _operation_conflict(exc) from exc
    except ChatOperationExpiredError as exc:
        db.rollback()
        await _cleanup_staging_draft(db, user_id=session.user_id, draft_id=staging_draft_id)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="chat operation expired") from exc
    except ChatHistoryNotFoundError as exc:
        _rollback_and_fail(db, operation, result_code="chat_history_not_found", detail=str(exc))
        await _cleanup_staging_draft(db, user_id=session.user_id, draft_id=staging_draft_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc
    except ChatHistoryDuplicateFileError as exc:
        _rollback_and_fail(db, operation, result_code="duplicate_attachment", detail=str(exc))
        await _cleanup_staging_draft(db, user_id=session.user_id, draft_id=staging_draft_id)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        _rollback_and_fail(db, operation, result_code="invalid_attachment", detail=str(exc))
        await _cleanup_staging_draft(db, user_id=session.user_id, draft_id=staging_draft_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        _rollback_and_fail(db, operation, result_code="attachment_backend_unavailable", detail=str(exc))
        await _cleanup_staging_draft(db, user_id=session.user_id, draft_id=staging_draft_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return ChatHistoryFilesEnvelope(
        history=build_chat_history_summary(history, len(history.messages), len(files)) if history is not None else None,
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
    operation: OperationHandle | None = None
    try:
        operation = begin_history_operation(
            db,
            session=session,
            history_id=history_id,
            operation_type="delete_file",
            timeout_seconds=validating_timeout_seconds(),
        )
        history, files, deleted_history_id = await asyncio.wait_for(
            delete_file_from_history(
                db,
                user_id=session.user_id,
                history_id=history_id,
                file_id=file_id,
                operation=operation,
            ),
            timeout=validating_timeout_seconds(),
        )
        complete_operation(db, operation, state="succeeded", allow_expired=True)
    except asyncio.TimeoutError as exc:
        _rollback_and_timeout(db, operation)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="chat validation took too long") from exc
    except ChatOperationConflictError as exc:
        raise _operation_conflict(exc) from exc
    except ChatOperationExpiredError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="chat operation expired") from exc
    except ChatHistoryNotFoundError as exc:
        _rollback_and_fail(db, operation, result_code="chat_history_not_found", detail=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc
    except ChatHistoryFileNotFoundError as exc:
        _rollback_and_fail(db, operation, result_code="chat_file_not_found", detail=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat file not found") from exc

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
    operation: OperationHandle | None = None
    try:
        operation = begin_history_operation(
            db,
            session=session,
            history_id=history_id,
            operation_type="toggle_file",
            timeout_seconds=validating_timeout_seconds(),
        )
        history, files = update_history_file_activation(
            db,
            user_id=session.user_id,
            history_id=history_id,
            file_id=file_id,
            is_active=payload.is_active,
            operation=operation,
        )
        complete_operation(db, operation, state="succeeded", allow_expired=True)
    except ChatOperationConflictError as exc:
        raise _operation_conflict(exc) from exc
    except ChatOperationExpiredError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="chat operation expired") from exc
    except ChatHistoryNotFoundError as exc:
        _rollback_and_fail(db, operation, result_code="chat_history_not_found", detail=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc
    except ChatHistoryFileNotFoundError as exc:
        _rollback_and_fail(db, operation, result_code="chat_file_not_found", detail=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat file not found") from exc

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
    operation: OperationHandle | None = None
    try:
        operation = begin_history_operation(
            db,
            session=session,
            history_id=history_id,
            operation_type="delete_history",
            timeout_seconds=validating_timeout_seconds(),
        )
        await asyncio.wait_for(
            delete_history_with_files(
                db,
                user_id=session.user_id,
                history_id=history_id,
                operation=operation,
            ),
            timeout=validating_timeout_seconds(),
        )
    except asyncio.TimeoutError as exc:
        _rollback_and_timeout(db, operation)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="chat validation took too long") from exc
    except ChatOperationConflictError as exc:
        raise _operation_conflict(exc) from exc
    except ChatOperationExpiredError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="chat operation expired") from exc
    except ChatHistoryNotFoundError as exc:
        _rollback_and_fail(db, operation, result_code="chat_history_not_found", detail=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat history not found") from exc

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


def _operation_conflict(_: ChatOperationConflictError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="chat operation already in progress",
    )


def _rollback_and_timeout(db: Session, operation: OperationHandle | None) -> None:
    db.rollback()
    if operation is not None:
        complete_operation(
            db,
            operation,
            state="timed_out",
            result_code="chat_validation_timeout",
            error_detail="chat validation took too long",
            allow_expired=True,
        )


def _rollback_and_fail(
    db: Session,
    operation: OperationHandle | None,
    *,
    result_code: str,
    detail: str,
) -> None:
    db.rollback()
    if operation is not None:
        complete_operation(
            db,
            operation,
            state="failed",
            result_code=result_code,
            error_detail=detail,
        )


async def _cleanup_staging_draft(db: Session, *, user_id: str, draft_id: str | None) -> None:
    if draft_id is None:
        return
    try:
        await discard_draft_with_files(db, user_id=user_id, draft_id=draft_id)
    except Exception:
        db.rollback()
