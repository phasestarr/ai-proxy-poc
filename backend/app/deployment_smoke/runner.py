from __future__ import annotations

import argparse
import asyncio
import base64
from collections.abc import Iterable
import uuid

from app.providers.anthropic.attachments import delete_anthropic_file, upload_anthropic_file
from app.providers.anthropic.count_tokens import ANTHROPIC_ATTACHMENT_COUNT_MODEL_ID
from app.providers.anthropic.provider import ANTHROPIC_PROVIDER_ID, list_anthropic_models
from app.providers.dispatcher import ensure_provider_ready, prepare_provider_chat_completion, stream_provider_chat_completion
from app.providers.openai.attachments import delete_openai_file, upload_openai_file
from app.providers.openai.count_tokens import OPENAI_ATTACHMENT_COUNT_MODEL_ID
from app.providers.openai.provider import OPENAI_PROVIDER_ID, list_openai_models
from app.providers.types import ProviderModelDefinition, ProviderRoute, ProviderStreamEvent
from app.providers.vertex.attachments import delete_vertex_file, upload_vertex_file
from app.providers.vertex.count_tokens import VERTEX_ATTACHMENT_COUNT_MODEL_ID
from app.providers.vertex.provider import VERTEX_PROVIDER_ID, list_vertex_models
from app.schemas.chat import ChatMessage

PROVIDERS = (ANTHROPIC_PROVIDER_ID, OPENAI_PROVIDER_ID, VERTEX_PROVIDER_ID)
TEXT_SMOKE_HELPER_MODELS = {
    ANTHROPIC_PROVIDER_ID: ANTHROPIC_ATTACHMENT_COUNT_MODEL_ID,
    OPENAI_PROVIDER_ID: OPENAI_ATTACHMENT_COUNT_MODEL_ID,
    VERTEX_PROVIDER_ID: VERTEX_ATTACHMENT_COUNT_MODEL_ID,
}
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run direct deployment smoke checks without product sessions.")
    parser.parse_args()

    run_smoke_check()
    print("deployment smoke check passed")


def run_smoke_check() -> None:
    asyncio.run(run_smoke_check_async())


async def run_smoke_check_async() -> None:
    selected_models = select_provider_models()
    for provider, model in selected_models.items():
        ensure_provider_ready(provider=provider)
        await run_text_smoke(provider=provider, model=model)

    for provider in PROVIDERS:
        await run_attachment_upload_delete_smoke(provider=provider)


def select_provider_models() -> dict[str, ProviderModelDefinition]:
    selected: dict[str, ProviderModelDefinition] = {}
    for provider in PROVIDERS:
        models = list(list_models_for_provider(provider))
        helper_model_id = TEXT_SMOKE_HELPER_MODELS[provider]
        match = next(
            (model for model in models if model.public_id == helper_model_id and model.available),
            None,
        )
        if match is None:
            raise RuntimeError(
                f"deployment smoke helper model {helper_model_id} is not available for provider {provider}"
            )
        selected[provider] = match
    return selected


def list_models_for_provider(provider: str) -> Iterable[ProviderModelDefinition]:
    if provider == ANTHROPIC_PROVIDER_ID:
        return list_anthropic_models()
    if provider == OPENAI_PROVIDER_ID:
        return list_openai_models()
    if provider == VERTEX_PROVIDER_ID:
        return list_vertex_models()
    raise RuntimeError(f"unsupported smoke provider: {provider}")


async def run_text_smoke(*, provider: str, model: ProviderModelDefinition) -> None:
    prepared_request = prepare_provider_chat_completion(
        route=ProviderRoute(model=model),
        messages=[
            ChatMessage(
                role="user",
                content=f"Reply with ok for {provider} deployment smoke.",
            )
        ],
    )
    chunks: list[ProviderStreamEvent] = []
    async for chunk in stream_provider_chat_completion(prepared_request=prepared_request):
        chunks.append(chunk)

    if not any(chunk.text_delta.strip() for chunk in chunks):
        raise RuntimeError(f"{provider} text smoke returned no visible text")


async def run_attachment_upload_delete_smoke(*, provider: str) -> None:
    provider_file_id: str | None = None
    display_name = "deployment-smoke.png"
    mime_type = "image/png"
    try:
        if provider == OPENAI_PROVIDER_ID:
            provider_file_id = await upload_openai_file(
                display_name=display_name,
                mime_type=mime_type,
                file_bytes=TINY_PNG,
            )
            return
        if provider == ANTHROPIC_PROVIDER_ID:
            provider_file_id = await upload_anthropic_file(
                display_name=display_name,
                mime_type=mime_type,
                file_bytes=TINY_PNG,
            )
            return
        if provider == VERTEX_PROVIDER_ID:
            provider_file_id = await upload_vertex_file(
                stored_file_id=f"deployment-smoke-{uuid.uuid4().hex}",
                display_name=display_name,
                mime_type=mime_type,
                file_bytes=TINY_PNG,
            )
            return
        raise RuntimeError(f"unsupported smoke provider: {provider}")
    finally:
        if provider_file_id:
            await delete_smoke_attachment(provider=provider, provider_file_id=provider_file_id)


async def delete_smoke_attachment(*, provider: str, provider_file_id: str) -> None:
    if provider == OPENAI_PROVIDER_ID:
        await delete_openai_file(provider_file_id=provider_file_id)
        return
    if provider == ANTHROPIC_PROVIDER_ID:
        await delete_anthropic_file(provider_file_id=provider_file_id)
        return
    if provider == VERTEX_PROVIDER_ID:
        await delete_vertex_file(file_uri=provider_file_id)
        return
    raise RuntimeError(f"unsupported smoke provider: {provider}")
