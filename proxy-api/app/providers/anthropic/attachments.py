from __future__ import annotations

import base64
from copy import deepcopy

from app.providers.anthropic.client import build_anthropic_client
from app.providers.anthropic.models import list_anthropic_models, resolve_anthropic_model_runtime

ANTHROPIC_FILES_BETA = "files-api-2025-04-14"
_ANTHROPIC_ATTACHMENT_CONTEXT_TEXT = (
    "The following files are attached to this chat history. "
    "Treat them as persistent reference context for every turn in this conversation."
)


def resolve_anthropic_attachment_count_model() -> str:
    # Generic Anthropic helper work should stay on the Haiku tier unless explicitly overridden.
    preferred_public_model_id = "claude-haiku-4-5"
    for model in list_anthropic_models():
        if model.public_id == preferred_public_model_id and model.available:
            return model.public_id
    for model in list_anthropic_models():
        if model.available:
            return model.public_id
    raise ValueError("no available anthropic model for attachment token counting")


async def count_anthropic_file_tokens(
    *,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> tuple[int, str]:
    public_model_id = resolve_anthropic_attachment_count_model()
    runtime = resolve_anthropic_model_runtime(public_model_id=public_model_id)
    encoded_file = base64.b64encode(file_bytes).decode("ascii")

    client = build_anthropic_client()
    try:
        response = await client.beta.messages.count_tokens(
            model=runtime.provider_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        build_anthropic_count_content_block(
                            display_name=display_name,
                            mime_type=mime_type,
                            encoded_file=encoded_file,
                        )
                    ],
                }
            ],
        )
        input_tokens = getattr(response, "input_tokens", None)
        if input_tokens is None:
            raise RuntimeError("anthropic input token count did not return a token value")
        return int(input_tokens), public_model_id
    finally:
        await client.close()


async def upload_anthropic_file(
    *,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> str:
    client = build_anthropic_client()
    try:
        uploaded = await client.beta.files.upload(
            file=(display_name, file_bytes, mime_type),
        )
        file_id = getattr(uploaded, "id", None)
        if not file_id:
            raise RuntimeError("anthropic file upload did not return a file id")
        return str(file_id)
    finally:
        await client.close()


async def delete_anthropic_file(*, provider_file_id: str) -> None:
    client = build_anthropic_client()
    try:
        await client.beta.files.delete(provider_file_id)
    finally:
        await client.close()


def inject_anthropic_history_files(
    *,
    payload: dict[str, object],
    attachments: list[dict[str, object]],
) -> dict[str, object]:
    if not attachments:
        return payload

    next_payload = deepcopy(payload)
    message_blocks: list[dict[str, object]] = [
        {
            "type": "text",
            "text": _ANTHROPIC_ATTACHMENT_CONTEXT_TEXT,
        }
    ]

    for index, attachment in enumerate(attachments):
        block = build_anthropic_file_reference_block(
            display_name=str(attachment["display_name"]),
            mime_type=str(attachment["mime_type"] or ""),
            provider_file_id=str(attachment["provider_file_id"]),
        )
        if index == len(attachments) - 1:
            block["cache_control"] = {"type": "ephemeral"}
        message_blocks.append(block)

    messages = list(next_payload.get("messages") or [])
    messages.insert(
        0,
        {
            "role": "user",
            "content": message_blocks,
        },
    )
    next_payload["messages"] = messages
    next_payload["betas"] = _merge_anthropic_betas(next_payload.get("betas"))
    return next_payload


def _merge_anthropic_betas(existing_value: object) -> list[str]:
    existing_betas = [
        str(item).strip()
        for item in (existing_value or [])
        if str(item).strip()
    ]
    merged = list(dict.fromkeys([*existing_betas, ANTHROPIC_FILES_BETA]))
    return merged


def build_anthropic_count_content_block(
    *,
    display_name: str,
    mime_type: str,
    encoded_file: str,
) -> dict[str, object]:
    if mime_type.startswith("image/"):
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": encoded_file,
            },
        }
    return {
        "type": "document",
        "title": display_name,
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": encoded_file,
        },
    }


def build_anthropic_file_reference_block(
    *,
    display_name: str,
    mime_type: str,
    provider_file_id: str,
) -> dict[str, object]:
    if mime_type.startswith("image/"):
        return {
            "type": "image",
            "source": {
                "type": "file",
                "file_id": provider_file_id,
            },
        }
    return {
        "type": "document",
        "title": display_name,
        "source": {
            "type": "file",
            "file_id": provider_file_id,
        },
    }
