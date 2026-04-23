from __future__ import annotations

from dataclasses import dataclass

from app.config.chat_outcomes import get_error_message


class ChatHistoryNotFoundError(RuntimeError):
    """Raised when a chat history does not belong to the current user."""


@dataclass(slots=True)
class ChatProxyError(RuntimeError):
    code: str
    origin: str
    detail: str
    http_status: int | None = None
    provider: str | None = None
    provider_error_code: str | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.detail)

    @property
    def result_message(self) -> str:
        return get_error_message(self.code)


def build_preparation_error(exc: ValueError) -> ChatProxyError:
    detail = str(exc)
    if detail == "model selection is required":
        return ChatProxyError(
            code="model_required",
            origin="client",
            detail=detail,
            http_status=400,
        )
    if detail.startswith("unsupported model:") or detail.startswith("model is not available:"):
        return ChatProxyError(
            code="model_unsupported",
            origin="client",
            detail=detail,
            http_status=400,
        )
    if detail.startswith("tool is not supported"):
        return ChatProxyError(
            code="tool_unsupported",
            origin="client",
            detail=detail,
            http_status=400,
        )
    return ChatProxyError(
        code="chat_failed",
        origin="proxy",
        detail=detail or "chat preparation failed",
        http_status=500,
    )
