from __future__ import annotations

import asyncio
from copy import deepcopy
from os.path import basename

from app.config.providers.vertex import vertex_settings
from app.providers.vertex.client import build_vertex_client
from app.providers.vertex.count_tokens import VERTEX_ATTACHMENT_COUNT_MODEL_ID
from app.providers.vertex.models import list_vertex_models, resolve_vertex_model_runtime

_VERTEX_ATTACHMENT_CONTEXT_TEXT = (
    "The following files are attached to this chat history. "
    "Treat them as persistent reference context for every turn in this conversation."
)


def resolve_vertex_attachment_count_model() -> str:
    # Generic Vertex helper work should stay on the Flash tier unless explicitly overridden.
    preferred_public_model_id = VERTEX_ATTACHMENT_COUNT_MODEL_ID
    for model in list_vertex_models():
        if model.public_id == preferred_public_model_id and model.available:
            return model.public_id
    for model in list_vertex_models():
        if model.available:
            return model.public_id
    raise ValueError("no available vertex model for attachment token counting")


async def count_vertex_file_tokens(
    *,
    file_uri: str,
    mime_type: str,
) -> tuple[int, str]:
    public_model_id = resolve_vertex_attachment_count_model()
    runtime = resolve_vertex_model_runtime(public_model_id=public_model_id)
    contents = [
        {
            "role": "user",
            "parts": [build_vertex_file_reference_part(file_uri=file_uri, mime_type=mime_type)],
        }
    ]

    client = build_vertex_client(location=runtime.location)
    try:
        async with client.aio as aio_client:
            response = await aio_client.models.count_tokens(
                model=runtime.provider_model,
                contents=contents,
            )
        total_tokens = getattr(response, "total_tokens", None)
        if total_tokens is None:
            raise RuntimeError("vertex input token count did not return a token value")
        return int(total_tokens), public_model_id
    finally:
        client.close()


async def upload_vertex_file(
    *,
    stored_file_id: str,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> str:
    bucket_name = vertex_settings.attachment_gcs_bucket
    if not bucket_name:
        raise RuntimeError("VERTEX_AI_ATTACHMENT_GCS_BUCKET is not configured")

    storage_client = build_storage_client()
    object_name = build_vertex_attachment_object_name(
        stored_file_id=stored_file_id,
        display_name=display_name,
    )
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    await asyncio.to_thread(blob.upload_from_string, file_bytes, content_type=mime_type)
    return f"gs://{bucket_name}/{object_name}"


async def delete_vertex_file(*, file_uri: str) -> None:
    bucket_name, object_name = parse_gcs_uri(file_uri)
    storage_client = build_storage_client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    if not await asyncio.to_thread(blob.exists):
        return
    try:
        await asyncio.to_thread(blob.delete)
    except Exception as exc:
        if is_gcs_not_found_error(exc):
            return
        raise


async def vertex_file_exists(*, file_uri: str) -> bool:
    bucket_name, object_name = parse_gcs_uri(file_uri)
    storage_client = build_storage_client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    return bool(await asyncio.to_thread(blob.exists))


def is_gcs_not_found_error(exc: Exception) -> bool:
    try:
        from google.api_core.exceptions import NotFound
    except ImportError:
        return False
    return isinstance(exc, NotFound)


def inject_vertex_history_files(
    *,
    payload: dict[str, object],
    attachments: list[dict[str, object]],
) -> dict[str, object]:
    if not attachments:
        return payload

    next_payload = dict(payload)
    contents = deepcopy(list(next_payload.get("contents") or []))
    attachment_parts: list[dict[str, object]] = [
        {
            "text": _VERTEX_ATTACHMENT_CONTEXT_TEXT,
        }
    ]
    for attachment in attachments:
        display_name = str(attachment["display_name"])
        file_uri = str(attachment["provider_file_id"])
        mime_type = str(attachment["mime_type"] or "")
        attachment_parts.append({"text": f"Attachment: {display_name}"})
        attachment_parts.append(build_vertex_file_reference_part(file_uri=file_uri, mime_type=mime_type))

    contents.insert(
        0,
        {
            "role": "user",
            "parts": attachment_parts,
        },
    )
    next_payload["contents"] = contents
    next_payload["estimate_source"] = {
        **dict(next_payload.get("estimate_source") or {}),
        "contents": contents,
    }
    return next_payload


def build_vertex_file_reference_part(*, file_uri: str, mime_type: str) -> dict[str, object]:
    return {
        "fileData": {
            "fileUri": file_uri,
            "mimeType": mime_type,
        }
    }


def build_vertex_attachment_object_name(*, stored_file_id: str, display_name: str) -> str:
    prefix = vertex_settings.attachment_gcs_prefix.strip().strip("/")
    safe_name = basename(display_name).replace("\\", "_").replace("/", "_").strip() or "attachment"
    object_name = f"{stored_file_id}/{safe_name}"
    if prefix:
        return f"{prefix}/{object_name}"
    return object_name


def parse_gcs_uri(file_uri: str) -> tuple[str, str]:
    if not file_uri.startswith("gs://"):
        raise ValueError("vertex attachment URI must start with gs://")
    without_scheme = file_uri.removeprefix("gs://")
    bucket_name, separator, object_name = without_scheme.partition("/")
    if not bucket_name or not separator or not object_name:
        raise ValueError("vertex attachment URI must include bucket and object")
    return bucket_name, object_name


def build_storage_client():
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError("google-cloud-storage is not installed") from exc

    return storage.Client(project=vertex_settings.project or None)
