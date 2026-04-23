"""
Anthropic Messages API request assembly.

Purpose:
- Keep provider request defaults and config wiring out of the stream executor.
- Separate hosted tool wiring from future function-calling wiring.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config.chat_instructions import build_chat_system_instruction
from app.config.providers.anthropic import anthropic_settings
from app.providers.anthropic.tools import build_anthropic_hosted_tools
from app.providers.types import ProviderFunctionDeclaration


def build_anthropic_messages_request(
    *,
    model: str,
    request_system_instruction: str | None,
    messages: list[dict[str, object]],
    selected_tool_ids: Iterable[str],
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> dict[str, object]:
    del function_declarations

    request_kwargs: dict[str, object] = {
        "model": model,
        "max_tokens": anthropic_settings.max_tokens,
        "system": build_chat_system_instruction(
            request_system_instruction=request_system_instruction,
        ),
        "messages": messages,
    }

    configured_tools = build_anthropic_hosted_tools(selected_tool_ids=selected_tool_ids)
    if configured_tools:
        request_kwargs["tools"] = configured_tools

    return request_kwargs

