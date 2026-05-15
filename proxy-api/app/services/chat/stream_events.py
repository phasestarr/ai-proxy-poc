from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic import BaseModel

from app.schemas.chat import ChatStreamErrorEvent, ChatStreamStartEvent
from app.services.chat.errors import ChatProxyError
from app.services.chat.turns import PersistedChatTurn


@dataclass(slots=True, frozen=True)
class LiveStreamEvent:
    event_name: str
    payload: BaseModel


class LiveChatStreamSink:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[LiveStreamEvent] = asyncio.Queue()
        self._active = True

    def emit(self, event_name: str, payload: BaseModel) -> None:
        if self._active:
            self._queue.put_nowait(LiveStreamEvent(event_name=event_name, payload=payload))

    async def get(self) -> LiveStreamEvent:
        return await self._queue.get()

    def close(self) -> None:
        self._active = False


async def stream_live_chat_completion(
    sink: LiveChatStreamSink,
):
    try:
        while True:
            event = await sink.get()
            yield encode_sse_event(event.event_name, event.payload)
            if event.event_name in {"done", "error"}:
                return
    finally:
        sink.close()


def build_start_event(turn: PersistedChatTurn) -> ChatStreamStartEvent:
    return ChatStreamStartEvent(
        model=turn.model_id,
        provider=turn.provider,
        chat_history_id=turn.history_id,
        user_message_id=turn.user_message_id,
        assistant_message_id=turn.assistant_message_id,
    )


def build_error_event(error: ChatProxyError) -> ChatStreamErrorEvent:
    return ChatStreamErrorEvent(
        result_code=error.code,
        result_message=error.result_message,
        retry_after_seconds=error.retry_after_seconds,
        detail=error.detail,
    )


def encode_sse_event(event_name: str, payload: BaseModel) -> bytes:
    return f"event: {event_name}\ndata: {payload.model_dump_json()}\n\n".encode("utf-8")
