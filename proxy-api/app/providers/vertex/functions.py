"""
Vertex function-calling scaffolding.

Purpose:
- Keep future custom function declaration wiring separate from hosted tools.
- Allow the request builder to combine hosted tools and function tools cleanly.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.providers.types import ProviderFunctionDeclaration

_VERTEX_FUNCTION_CALLING_MODE = "AUTO"


def build_vertex_function_tools(
    *,
    function_declarations: Iterable[ProviderFunctionDeclaration],
    types_module=None,
) -> list[object]:
    normalized_declarations = _normalize_function_declarations(function_declarations)
    if not normalized_declarations:
        return []

    tool_payload = {
        "function_declarations": [
            {
                "name": declaration.name,
                "description": declaration.description,
                "parameters_json_schema": declaration.parameters_json_schema,
            }
            for declaration in normalized_declarations
        ]
    }

    tool_type = getattr(types_module, "Tool", None) if types_module is not None else None
    if tool_type is None:
        return [tool_payload]

    return [tool_type(**tool_payload)]


def build_vertex_function_tool_config(
    *,
    function_declarations: Iterable[ProviderFunctionDeclaration],
    types_module=None,
):
    if not _normalize_function_declarations(function_declarations):
        return None

    tool_config_payload = {
        "function_calling_config": {
            "mode": _VERTEX_FUNCTION_CALLING_MODE,
        }
    }

    tool_config_type = getattr(types_module, "ToolConfig", None) if types_module is not None else None
    if tool_config_type is None:
        return tool_config_payload

    return tool_config_type(**tool_config_payload)


def _normalize_function_declarations(
    function_declarations: Iterable[ProviderFunctionDeclaration],
) -> list[ProviderFunctionDeclaration]:
    normalized: list[ProviderFunctionDeclaration] = []
    seen_names: set[str] = set()
    for declaration in function_declarations:
        normalized_name = declaration.name.strip()
        if not normalized_name or normalized_name in seen_names:
            continue
        normalized.append(declaration)
        seen_names.add(normalized_name)
    return normalized
