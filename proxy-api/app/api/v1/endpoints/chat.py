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

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.session import require_authenticated_session, require_capability
from app.api.v1.dependencies.db import get_db
from app.api.v1.presenters.chat import build_chat_history_message_view, build_chat_history_summary
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatHistoryCreateRequest,
    ChatHistoryEnvelope,
    ChatHistoryListEnvelope,
    ChatHistorySummary,
    ChatHistoryTitleUpdateRequest,
)
from app.services.chat.stream import (
    ChatHistoryUnavailableError,
    create_chat_completion_stream,
)
from app.services.chat.errors import ChatHistoryNotFoundError, ChatProxyError
from app.services.chat.history_queries import (
    create_chat_history,
    delete_chat_history,
    get_chat_history,
    list_chat_histories,
    pin_chat_history,
    unpin_chat_history,
    update_chat_history_title,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/histories", response_model=ChatHistoryListEnvelope)
def list_histories(
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistoryListEnvelope:
    return ChatHistoryListEnvelope(
        histories=[
            build_chat_history_summary(history, message_count)
            for history, message_count in list_chat_histories(db, user_id=session.user_id)
        ]
    )


@router.post("/histories", response_model=ChatHistoryEnvelope, status_code=status.HTTP_201_CREATED)
def create_history(
    payload: ChatHistoryCreateRequest,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> ChatHistoryEnvelope:
    history = create_chat_history(db, user_id=session.user_id, title=payload.title)
    return ChatHistoryEnvelope(
        history=build_chat_history_summary(history, 0),
        messages=[],
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

    return ChatHistoryEnvelope(
        history=build_chat_history_summary(history, len(messages)),
        messages=[build_chat_history_message_view(message) for message in messages],
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

    return build_chat_history_summary(history, len(history.messages))


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

    return build_chat_history_summary(history, len(history.messages))


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

    return build_chat_history_summary(history, len(history.messages))


@router.delete("/histories/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history(
    history_id: str,
    response: Response,
    session=Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> Response:
    try:
        delete_chat_history(db, user_id=session.user_id, history_id=history_id)
    except ChatHistoryNotFoundError as exc:
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
