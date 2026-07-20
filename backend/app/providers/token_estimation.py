from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import tiktoken

from app.config.chat import DEFAULT_TEXT_TOKEN_ENCODING


def estimate_token_count_from_text(value: str) -> int:
    return max(1, len(_get_default_encoding().encode(value)))

def estimate_token_count_from_object(
    value: Any,
    *,
    base_tokens: int = 0,
) -> int:
    serialized = _safe_serialize(value)
    encoding = _get_default_encoding()
    token_count = len(encoding.encode(serialized))
    return max(1, base_tokens + token_count)


@lru_cache(maxsize=1)
def _get_default_encoding():
    return tiktoken.get_encoding(DEFAULT_TEXT_TOKEN_ENCODING)


def _safe_serialize(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_fallback_json_default)
    except TypeError:
        return repr(value)


def _fallback_json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return value.__dict__
    return repr(value)
