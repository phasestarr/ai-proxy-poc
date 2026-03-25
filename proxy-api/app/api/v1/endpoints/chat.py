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

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.v1.dependencies.auth import require_capability
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.stream import (
    ChatCoordinationUnavailableError,
    ChatProviderUnavailableError,
    ChatRateLimitExceededError,
    ChatRequestInProgressError,
    create_chat_completion_stream,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    session=Depends(require_capability("chat:send")),
) -> StreamingResponse:
    try:
        event_stream = create_chat_completion_stream(payload, session=session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ChatRequestInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="chat request already in progress",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ChatRateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ChatCoordinationUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ChatProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
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
