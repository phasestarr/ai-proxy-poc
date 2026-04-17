"""
Vertex request config assembly.

Purpose:
- Keep provider request defaults and config wiring out of the stream executor.
- Separate hosted tool wiring from future function-calling wiring.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config.chat_instructions import build_chat_system_instruction
from app.providers.types import ProviderFunctionDeclaration
from app.providers.vertex.functions import build_vertex_function_tool_config, build_vertex_function_tools
from app.providers.vertex.tools import build_vertex_hosted_tools

_VERTEX_GENERATION_CONFIG: dict[str, object] = {}
_VERTEX_REQUEST_LABELS: dict[str, str] = {}
_VERTEX_SAFETY_SETTINGS: tuple[dict[str, object], ...] = ()


def build_vertex_generate_content_config(
    *,
    types,
    request_system_instruction: str | None,
    selected_tool_ids: Iterable[str],
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
):
    config_kwargs: dict[str, object] = {
        "system_instruction": build_chat_system_instruction(
            request_system_instruction=request_system_instruction,
        ),
    }

    configured_tools = [
        *build_vertex_hosted_tools(
            selected_tool_ids=selected_tool_ids,
            types_module=types,
        ),
        *build_vertex_function_tools(
            function_declarations=function_declarations,
            types_module=types,
        ),
    ]
    if configured_tools:
        config_kwargs["tools"] = configured_tools

    tool_config = build_vertex_function_tool_config(
        function_declarations=function_declarations,
        types_module=types,
    )
    if tool_config is not None:
        config_kwargs["tool_config"] = tool_config

    if _VERTEX_GENERATION_CONFIG:
        config_kwargs.update(_VERTEX_GENERATION_CONFIG)

    safety_settings = _build_vertex_safety_settings(types_module=types)
    if safety_settings:
        config_kwargs["safety_settings"] = safety_settings

    if _VERTEX_REQUEST_LABELS:
        config_kwargs["labels"] = dict(_VERTEX_REQUEST_LABELS)

    return types.GenerateContentConfig(**config_kwargs)


def _build_vertex_safety_settings(*, types_module) -> list[object]:
    if not _VERTEX_SAFETY_SETTINGS:
        return []

    safety_setting_type = getattr(types_module, "SafetySetting", None)
    if safety_setting_type is None:
        return [dict(item) for item in _VERTEX_SAFETY_SETTINGS]

    return [safety_setting_type(**item) for item in _VERTEX_SAFETY_SETTINGS]
