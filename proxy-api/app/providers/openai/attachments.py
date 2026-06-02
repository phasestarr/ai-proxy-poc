from __future__ import annotations

import base64
import hashlib
from copy import deepcopy

from app.providers.openai.client import build_openai_client
from app.providers.openai.count_tokens import OPENAI_ATTACHMENT_COUNT_MODEL_ID
from app.providers.openai.models import list_openai_models, resolve_openai_model_runtime

_OPENAI_ATTACHMENT_CONTEXT_TEXT = (
    "The following files are attached to this chat history. "
    "Treat them as persistent reference context for every turn in this conversation."
)
_OPENAI_IMAGE_DETAIL = "auto"


def resolve_openai_attachment_count_model() -> str:
    # Generic OpenAI helper work should stay on the mini tier unless explicitly overridden.
    preferred_public_model_id = OPENAI_ATTACHMENT_COUNT_MODEL_ID
    for model in list_openai_models():
        if model.public_id == preferred_public_model_id and model.available:
            return model.public_id
    for model in list_openai_models():
        if model.available:
            return model.public_id
    raise ValueError("no available openai model for attachment token counting")


async def count_openai_file_tokens(
    *,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> tuple[int, str]:
    public_model_id = resolve_openai_attachment_count_model()
    runtime = resolve_openai_model_runtime(public_model_id=public_model_id)
    encoded_file = f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('ascii')}"
    content_block = build_openai_count_content_block(
        display_name=display_name,
        mime_type=mime_type,
        encoded_file=encoded_file,
    )

    client = build_openai_client()
    try:
        response = await client.responses.input_tokens.count(
            model=runtime.provider_model,
            truncation="disabled",
            input=[
                {
                    "role": "user",
                    "content": [content_block],
                }
            ],
        )
        input_tokens = getattr(response, "input_tokens", None)
        if input_tokens is None:
            raise RuntimeError("openai input token count did not return a token value")
        return int(input_tokens), public_model_id
    finally:
        await client.close()


async def count_openai_file_reference_tokens(
    *,
    mime_type: str,
    provider_file_id: str,
) -> tuple[int, str]:
    public_model_id = resolve_openai_attachment_count_model()
    runtime = resolve_openai_model_runtime(public_model_id=public_model_id)
    content_block = build_openai_file_reference_block(
        mime_type=mime_type,
        provider_file_id=provider_file_id,
    )

    client = build_openai_client()
    try:
        response = await client.responses.input_tokens.count(
            model=runtime.provider_model,
            truncation="disabled",
            input=[
                {
                    "role": "user",
                    "content": [content_block],
                }
            ],
        )
        input_tokens = getattr(response, "input_tokens", None)
        if input_tokens is None:
            raise RuntimeError("openai input token count did not return a token value")
        return int(input_tokens), public_model_id
    finally:
        await client.close()


async def upload_openai_file(
    *,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> str:
    client = build_openai_client()
    try:
        uploaded = await client.files.create(
            file=(display_name, file_bytes, mime_type),
            purpose="vision" if mime_type.startswith("image/") else "user_data",
        )
        file_id = getattr(uploaded, "id", None)
        if not file_id:
            raise RuntimeError("openai file upload did not return a file id")
        return str(file_id)
    finally:
        await client.close()


async def delete_openai_file(*, provider_file_id: str) -> None:
    client = build_openai_client()
    try:
        await client.files.delete(provider_file_id)
    except Exception as exc:
        if is_openai_file_not_found_error(exc):
            return
        raise
    finally:
        await client.close()


async def openai_file_exists(*, provider_file_id: str) -> bool:
    client = build_openai_client()
    try:
        await client.files.retrieve(provider_file_id)
        return True
    except Exception as exc:
        if is_openai_file_not_found_error(exc):
            return False
        raise
    finally:
        await client.close()


def is_openai_file_not_found_error(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404


def inject_openai_history_files(
    *,
    payload: dict[str, object],
    history_id: str,
    attachments: list[dict[str, object]],
) -> dict[str, object]:
    if not attachments:
        return payload

    next_payload = deepcopy(payload)
    input_messages = list(next_payload.get("input") or [])

    attachment_blocks: list[dict[str, object]] = [
        {
            "type": "input_text",
            "text": _OPENAI_ATTACHMENT_CONTEXT_TEXT,
        }
    ]
    cache_key_parts: list[str] = [history_id]
    for attachment in attachments:
        display_name = str(attachment["display_name"])
        provider_file_id = str(attachment["provider_file_id"])
        mime_type = str(attachment["mime_type"] or "")
        attachment_blocks.append(
            {
                "type": "input_text",
                "text": f"Attachment: {display_name}",
            }
        )
        attachment_blocks.append(build_openai_file_reference_block(mime_type=mime_type, provider_file_id=provider_file_id))
        cache_key_parts.append(provider_file_id)

    input_messages.insert(
        0,
        {
            "role": "user",
            "content": attachment_blocks,
        },
    )
    next_payload["input"] = input_messages
    next_payload["prompt_cache_key"] = _build_openai_prompt_cache_key(cache_key_parts)
    return next_payload


def _build_openai_prompt_cache_key(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_openai_count_content_block(
    *,
    display_name: str,
    mime_type: str,
    encoded_file: str,
) -> dict[str, object]:
    if mime_type.startswith("image/"):
        return {
            "type": "input_image",
            "detail": _OPENAI_IMAGE_DETAIL,
            "image_url": encoded_file,
        }
    return {
        "type": "input_file",
        "filename": display_name,
        "file_data": encoded_file,
    }


def build_openai_file_reference_block(*, mime_type: str, provider_file_id: str) -> dict[str, object]:
    if mime_type.startswith("image/"):
        return {
            "type": "input_image",
            "detail": _OPENAI_IMAGE_DETAIL,
            "file_id": provider_file_id,
        }
    return {
        "type": "input_file",
        "file_id": provider_file_id,
    }
