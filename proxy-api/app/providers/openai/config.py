"""
OpenAI Responses API request assembly.

Purpose:
- Keep provider request defaults and config wiring out of the stream executor.
- Separate hosted tool wiring from future function-calling wiring.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config.chat_instructions import build_chat_system_instruction
from app.providers.types import ProviderFunctionDeclaration
from app.providers.openai.tools import build_openai_hosted_tools

_OPENAI_REQUEST_DEFAULTS: dict[str, object] = {
    "store": False,
}


def build_openai_responses_request(
    *,
    model: str,
    request_system_instruction: str | None,
    input_messages: list[dict[str, object]],
    selected_tool_ids: Iterable[str],
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> dict[str, object]:
    del function_declarations

    request_kwargs: dict[str, object] = {
        "model": model,
        "instructions": build_chat_system_instruction(
            request_system_instruction=request_system_instruction,
        ),
        "input": input_messages,
        **_OPENAI_REQUEST_DEFAULTS,
    }

    configured_tools = build_openai_hosted_tools(selected_tool_ids=selected_tool_ids)
    if configured_tools:
        request_kwargs["tools"] = configured_tools

    return request_kwargs

