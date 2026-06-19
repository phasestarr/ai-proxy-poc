from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from os.path import basename
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import load_only, selectinload

from app.config.providers.vertex import vertex_settings
from app.db.postgres.models.chat_attachment import ChatHistoryFile, StoredFile, StoredFileProviderState
from app.db.postgres.session import SessionLocal
from app.providers.anthropic.attachments import ANTHROPIC_FILES_BETA
from app.providers.anthropic.client import build_anthropic_client
from app.providers.openai.client import build_openai_client
from app.providers.vertex.attachments import build_storage_client, delete_vertex_file
from app.services.chat.attachments.remote_files import mark_provider_state_not_uploaded

SUPPORTED_PROVIDERS = ("openai", "anthropic", "vertex_ai")
OPENAI_FILE_PURPOSES = ("user_data", "vision")
DEFAULT_REMOTE_PAGE_SIZE = 100
DEFAULT_SAMPLE_LIMIT = 100


@dataclass(slots=True)
class DbProviderStateRow:
    provider: str
    stored_file_id: str
    token_count: int | None
    token_count_status: str
    token_count_error: str | None
    provider_file_id: str | None
    remote_file_status: str
    remote_file_error: str | None
    count_model_id: str | None
    uploaded_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class DbHistoryFileRow:
    chat_history_file_id: str
    chat_history_id: str
    display_name: str
    mime_type: str
    byte_size: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class DbStoredFileRow:
    stored_file_id: str
    user_id: str
    sha256: str
    mime_type: str
    byte_size: int
    created_at: datetime
    updated_at: datetime
    history_ref_count: int
    active_history_ref_count: int
    history_refs: list[DbHistoryFileRow]
    provider_states: list[DbProviderStateRow]


@dataclass(slots=True)
class LocalBlobSummary:
    stored_file_id: str
    user_id: str
    byte_size: int
    created_at: datetime


@dataclass(slots=True)
class RemoteProviderFile:
    provider: str
    file_id: str
    filename: str | None
    purpose: str | None
    mime_type: str | None
    bytes: int | None
    created_at: str | None
    updated_at: str | None
    bucket: str | None
    object_name: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect and clean provider-managed attachment files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_db_parser = subparsers.add_parser("list-db", help="List DB-tracked provider file refs.")
    list_db_parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default=None)

    list_db_blobs_parser = subparsers.add_parser(
        "list-db-blobs",
        help="List locally stored PostgreSQL attachment blobs and metadata without reading blob bytes.",
    )
    list_db_blobs_parser.add_argument("--user-id", default=None)
    list_db_blobs_parser.add_argument("--stored-file-id", default=None)
    list_db_blobs_parser.add_argument("--sha256", default=None)
    list_db_blobs_parser.add_argument("--filename", default=None)
    list_db_blobs_parser.add_argument("--limit", type=int, default=100)

    list_openai_parser = subparsers.add_parser("list-openai", help="List OpenAI attachment files.")
    list_openai_parser.add_argument("--limit", type=int, default=100)
    list_openai_parser.add_argument("--filename", default=None)

    list_anthropic_parser = subparsers.add_parser("list-anthropic", help="List Anthropic attachment files.")
    list_anthropic_parser.add_argument("--limit", type=int, default=100)
    list_anthropic_parser.add_argument("--filename", default=None)

    list_vertex_parser = subparsers.add_parser("list-vertex", help="List Vertex attachment objects from GCS.")
    list_vertex_parser.add_argument("--limit", type=int, default=100)
    list_vertex_parser.add_argument("--filename", default=None)
    list_vertex_parser.add_argument("--bucket", default=None)
    list_vertex_parser.add_argument("--prefix", default=None)

    inspect_consistency_parser = subparsers.add_parser(
        "inspect-consistency",
        help="Inspect local-vs-remote attachment consistency across providers.",
    )
    inspect_consistency_parser.add_argument(
        "--provider",
        choices=[*SUPPORTED_PROVIDERS, "all"],
        default="all",
    )
    inspect_consistency_parser.add_argument("--sample-limit", type=int, default=DEFAULT_SAMPLE_LIMIT)
    inspect_consistency_parser.add_argument("--bucket", default=None)
    inspect_consistency_parser.add_argument("--prefix", default=None)

    reconcile_consistency_parser = subparsers.add_parser(
        "reconcile-consistency",
        help="Plan or apply local-vs-remote attachment consistency cleanup.",
    )
    reconcile_consistency_parser.add_argument(
        "--provider",
        choices=[*SUPPORTED_PROVIDERS, "all"],
        default="all",
    )
    reconcile_consistency_parser.add_argument("--sample-limit", type=int, default=DEFAULT_SAMPLE_LIMIT)
    reconcile_consistency_parser.add_argument("--bucket", default=None)
    reconcile_consistency_parser.add_argument("--prefix", default=None)
    reconcile_consistency_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply DB ref clears and remote orphan deletes. Without this flag the command is a dry run.",
    )

    cleanup_parser = subparsers.add_parser(
        "cleanup-filename",
        help="Delete matching remote files and clear matching DB provider refs.",
    )
    cleanup_parser.add_argument("--filename", required=True)
    cleanup_parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "vertex_ai", "all"],
        default="all",
    )
    cleanup_parser.add_argument("--bucket", default=None)
    cleanup_parser.add_argument("--prefix", default=None)
    cleanup_parser.add_argument(
        "--skip-db-clear",
        action="store_true",
        help="Delete remote files only and leave DB provider refs unchanged.",
    )

    cleanup_file_id_parser = subparsers.add_parser(
        "cleanup-file-id",
        help="Delete one exact remote provider file id and clear matching DB provider refs.",
    )
    cleanup_file_id_parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, required=True)
    cleanup_file_id_parser.add_argument("--file-id", required=True)
    cleanup_file_id_parser.add_argument(
        "--skip-db-clear",
        action="store_true",
        help="Delete the remote file only and leave DB provider refs unchanged.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "list-db":
        print_json(
            [
                asdict(row)
                for row in list_db_provider_refs(provider=args.provider)
            ]
        )
        return
    if args.command == "list-db-blobs":
        print_json(
            [
                asdict(row)
                for row in list_db_blobs(
                    user_id=args.user_id,
                    stored_file_id=args.stored_file_id,
                    sha256=args.sha256,
                    filename=args.filename,
                    limit=args.limit,
                )
            ]
        )
        return
    if args.command == "list-openai":
        print_json(asyncio.run(list_openai_files(limit=args.limit, filename=args.filename)))
        return
    if args.command == "list-anthropic":
        print_json(asyncio.run(list_anthropic_files(limit=args.limit, filename=args.filename)))
        return
    if args.command == "list-vertex":
        print_json(
            asyncio.run(
                list_vertex_files(
                    limit=args.limit,
                    filename=args.filename,
                    bucket=args.bucket,
                    prefix=args.prefix,
                )
            )
        )
        return
    if args.command == "inspect-consistency":
        print_json(
            asyncio.run(
                inspect_consistency(
                    provider=args.provider,
                    sample_limit=args.sample_limit,
                    bucket=args.bucket,
                    prefix=args.prefix,
                )
            )
        )
        return
    if args.command == "reconcile-consistency":
        print_json(
            asyncio.run(
                reconcile_consistency(
                    provider=args.provider,
                    sample_limit=args.sample_limit,
                    bucket=args.bucket,
                    prefix=args.prefix,
                    apply=args.apply,
                )
            )
        )
        return
    if args.command == "cleanup-filename":
        print_json(
            asyncio.run(
                cleanup_filename(
                    filename=args.filename,
                    provider=args.provider,
                    bucket=args.bucket,
                    prefix=args.prefix,
                    clear_db=not args.skip_db_clear,
                )
            )
        )
        return
    if args.command == "cleanup-file-id":
        print_json(
            asyncio.run(
                cleanup_file_id(
                    provider=args.provider,
                    file_id=args.file_id,
                    clear_db=not args.skip_db_clear,
                )
            )
        )
        return
    raise SystemExit(f"unsupported command: {args.command}")


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=_json_default))


def list_db_provider_refs(*, provider: str | None) -> list[DbProviderStateRow]:
    with SessionLocal() as db:
        query = (
            select(StoredFileProviderState)
            .where(StoredFileProviderState.provider_file_id.is_not(None))
            .order_by(
                StoredFileProviderState.provider.asc(),
                StoredFileProviderState.uploaded_at.asc(),
                StoredFileProviderState.id.asc(),
            )
        )
        if provider is not None:
            query = query.where(StoredFileProviderState.provider == provider)

        return [_state_to_row(state) for state in db.execute(query).scalars().all()]


def list_db_blobs(
    *,
    user_id: str | None,
    stored_file_id: str | None,
    sha256: str | None,
    filename: str | None,
    limit: int,
) -> list[DbStoredFileRow]:
    with SessionLocal() as db:
        query = (
            select(StoredFile)
            .options(
                load_only(
                    StoredFile.id,
                    StoredFile.user_id,
                    StoredFile.sha256,
                    StoredFile.mime_type,
                    StoredFile.byte_size,
                    StoredFile.created_at,
                    StoredFile.updated_at,
                ),
                selectinload(StoredFile.provider_states).load_only(
                    StoredFileProviderState.provider,
                    StoredFileProviderState.stored_file_id,
                    StoredFileProviderState.token_count,
                    StoredFileProviderState.token_count_status,
                    StoredFileProviderState.token_count_error,
                    StoredFileProviderState.provider_file_id,
                    StoredFileProviderState.remote_file_status,
                    StoredFileProviderState.remote_file_error,
                    StoredFileProviderState.count_model_id,
                    StoredFileProviderState.uploaded_at,
                    StoredFileProviderState.last_used_at,
                    StoredFileProviderState.created_at,
                    StoredFileProviderState.updated_at,
                ),
                selectinload(StoredFile.history_files).load_only(
                    ChatHistoryFile.id,
                    ChatHistoryFile.chat_history_id,
                    ChatHistoryFile.display_name,
                    ChatHistoryFile.mime_type,
                    ChatHistoryFile.byte_size,
                    ChatHistoryFile.is_active,
                    ChatHistoryFile.created_at,
                    ChatHistoryFile.updated_at,
                ),
            )
            .order_by(StoredFile.created_at.desc(), StoredFile.id.asc())
        )

        if user_id is not None:
            query = query.where(StoredFile.user_id == user_id)
        if stored_file_id is not None:
            query = query.where(StoredFile.id == stored_file_id)
        if sha256 is not None:
            query = query.where(StoredFile.sha256 == sha256)
        if filename is not None:
            query = query.join(StoredFile.history_files).where(ChatHistoryFile.display_name == filename).distinct()

        rows = db.execute(query.limit(max(1, limit))).scalars().unique().all()
        result: list[DbStoredFileRow] = []
        for stored_file in rows:
            history_refs = sorted(
                [_history_file_to_row(history_file) for history_file in stored_file.history_files],
                key=lambda item: (item.created_at, item.chat_history_file_id),
            )
            provider_states = sorted(
                [_state_to_row(state) for state in stored_file.provider_states],
                key=lambda item: (item.provider, item.created_at, item.stored_file_id),
            )
            result.append(
                DbStoredFileRow(
                    stored_file_id=stored_file.id,
                    user_id=stored_file.user_id,
                    sha256=stored_file.sha256,
                    mime_type=stored_file.mime_type,
                    byte_size=stored_file.byte_size,
                    created_at=stored_file.created_at,
                    updated_at=stored_file.updated_at,
                    history_ref_count=len(history_refs),
                    active_history_ref_count=sum(1 for item in history_refs if item.is_active),
                    history_refs=history_refs,
                    provider_states=provider_states,
                )
            )
        return result


async def list_openai_files(*, limit: int, filename: str | None) -> list[dict[str, Any]]:
    items = await _collect_openai_files(max_items=max(1, limit), filename=filename)
    return [asdict(item) for item in items]


async def list_anthropic_files(*, limit: int, filename: str | None) -> list[dict[str, Any]]:
    items = await _collect_anthropic_files(max_items=max(1, limit), filename=filename)
    return [asdict(item) for item in items]


async def list_vertex_files(
    *,
    limit: int,
    filename: str | None,
    bucket: str | None,
    prefix: str | None,
) -> list[dict[str, Any]]:
    items = await _collect_vertex_files(
        max_items=max(1, limit),
        filename=filename,
        bucket=bucket,
        prefix=prefix,
    )
    return [asdict(item) for item in items]


async def inspect_consistency(
    *,
    provider: str,
    sample_limit: int,
    bucket: str | None,
    prefix: str | None,
) -> dict[str, Any]:
    state = await _collect_consistency_state(
        provider=provider,
        bucket=bucket,
        prefix=prefix,
    )
    return _build_consistency_payload(
        state=state,
        sample_limit=sample_limit,
    )


async def reconcile_consistency(
    *,
    provider: str,
    sample_limit: int,
    bucket: str | None,
    prefix: str | None,
    apply: bool,
) -> dict[str, Any]:
    state = await _collect_consistency_state(
        provider=provider,
        bucket=bucket,
        prefix=prefix,
    )
    payload = _build_consistency_payload(
        state=state,
        sample_limit=sample_limit,
    )

    planned_db_clears = [
        {
            "provider": row.provider,
            "stored_file_id": row.stored_file_id,
            "provider_file_id": row.provider_file_id,
        }
        for row in state["db_refs_missing_remote"]
        if row.provider_file_id
    ]
    planned_remote_deletes = [
        asdict(item)
        for provider_name in state["providers"]
        for item in state["remote_files_missing_db_ref"][provider_name]
    ]

    applied_db_clears: list[dict[str, str]] = []
    applied_remote_deletes: list[dict[str, Any]] = []
    remote_delete_errors: list[dict[str, str]] = []

    if apply:
        provider_file_ids_by_provider: dict[str, set[str]] = defaultdict(set)
        for row in state["db_refs_missing_remote"]:
            if row.provider_file_id:
                provider_file_ids_by_provider[row.provider].add(row.provider_file_id)

        for provider_name, provider_file_ids in provider_file_ids_by_provider.items():
            applied_db_clears.extend(
                clear_db_provider_refs(
                    provider=provider_name,
                    provider_file_ids=provider_file_ids,
                )
            )

        for provider_name in state["providers"]:
            for item in state["remote_files_missing_db_ref"][provider_name]:
                try:
                    await delete_remote_provider_file(provider=provider_name, file_id=item.file_id)
                except Exception as exc:
                    remote_delete_errors.append(
                        {
                            "provider": provider_name,
                            "file_id": item.file_id,
                            "error": str(exc),
                        }
                    )
                    continue
                applied_remote_deletes.append(asdict(item))

    payload["reconcile"] = {
        "dry_run": not apply,
        "planned_db_ref_clears": planned_db_clears,
        "planned_remote_deletes": planned_remote_deletes,
        "applied_db_ref_clears": applied_db_clears,
        "applied_remote_deletes": applied_remote_deletes,
        "remote_delete_errors": remote_delete_errors,
    }
    return payload


async def cleanup_filename(
    *,
    filename: str,
    provider: str,
    bucket: str | None,
    prefix: str | None,
    clear_db: bool,
) -> dict[str, Any]:
    requested_providers = _resolve_requested_providers(provider)
    deleted_remote_files: list[dict[str, Any]] = []
    db_cleared_refs: list[dict[str, str]] = []

    for provider_name in requested_providers:
        remote_files = await _collect_remote_files(
            provider=provider_name,
            max_items=None,
            filename=filename,
            bucket=bucket,
            prefix=prefix,
        )
        for item in remote_files:
            await delete_remote_provider_file(provider=provider_name, file_id=item.file_id)
            deleted_remote_files.append(asdict(item))
        if clear_db:
            db_cleared_refs.extend(
                clear_db_provider_refs(
                    provider=provider_name,
                    provider_file_ids={item.file_id for item in remote_files},
                )
            )

    return {
        "filename": filename,
        "providers": requested_providers,
        "deleted_remote_files": deleted_remote_files,
        "cleared_db_refs": db_cleared_refs,
    }


async def cleanup_file_id(
    *,
    provider: str,
    file_id: str,
    clear_db: bool,
) -> dict[str, Any]:
    normalized_file_id = file_id.strip()
    if not normalized_file_id:
        raise ValueError("file id must not be blank")

    await delete_remote_provider_file(provider=provider, file_id=normalized_file_id)
    db_cleared_refs = (
        clear_db_provider_refs(provider=provider, provider_file_ids={normalized_file_id})
        if clear_db
        else []
    )
    return {
        "provider": provider,
        "file_id": normalized_file_id,
        "deleted_remote_file": {"provider": provider, "file_id": normalized_file_id},
        "cleared_db_refs": db_cleared_refs,
    }


async def delete_remote_provider_file(*, provider: str, file_id: str) -> None:
    if provider == "openai":
        client = build_openai_client()
        try:
            await client.files.delete(file_id)
        finally:
            await client.close()
        return

    if provider == "anthropic":
        client = build_anthropic_client()
        try:
            await client.beta.files.delete(
                file_id,
                betas=[ANTHROPIC_FILES_BETA],
            )
        finally:
            await client.close()
        return

    if provider == "vertex_ai":
        await delete_vertex_file(file_uri=file_id)
        return

    raise ValueError(f"unsupported provider: {provider}")


def clear_db_provider_refs(*, provider: str, provider_file_ids: set[str]) -> list[dict[str, str]]:
    if not provider_file_ids:
        return []

    cleared: list[dict[str, str]] = []
    with SessionLocal() as db:
        states = db.execute(
            select(StoredFileProviderState)
            .where(
                StoredFileProviderState.provider == provider,
                StoredFileProviderState.provider_file_id.in_(sorted(provider_file_ids)),
            )
            .order_by(StoredFileProviderState.id.asc())
        ).scalars().all()

        for state in states:
            if not state.provider_file_id:
                continue
            cleared.append(
                {
                    "provider": state.provider,
                    "stored_file_id": state.stored_file_id,
                    "provider_file_id": str(state.provider_file_id),
                }
            )
            mark_provider_state_not_uploaded(state)

        db.commit()
    return cleared


async def _collect_remote_files(
    *,
    provider: str,
    max_items: int | None,
    filename: str | None,
    bucket: str | None,
    prefix: str | None,
) -> list[RemoteProviderFile]:
    if provider == "openai":
        return await _collect_openai_files(max_items=max_items, filename=filename)
    if provider == "anthropic":
        return await _collect_anthropic_files(max_items=max_items, filename=filename)
    if provider == "vertex_ai":
        return await _collect_vertex_files(
            max_items=max_items,
            filename=filename,
            bucket=bucket,
            prefix=prefix,
        )
    raise ValueError(f"unsupported provider: {provider}")


async def _collect_openai_files(
    *,
    max_items: int | None,
    filename: str | None,
) -> list[RemoteProviderFile]:
    client = build_openai_client()
    try:
        items: list[RemoteProviderFile] = []
        seen_file_ids: set[str] = set()
        page_size = _resolve_page_size(max_items)
        for purpose in OPENAI_FILE_PURPOSES:
            async for item in client.files.list(
                purpose=purpose,
                order="desc",
                limit=page_size,
            ):
                file_id = _optional_str(getattr(item, "id", None))
                if not file_id or file_id in seen_file_ids:
                    continue
                remote_item = RemoteProviderFile(
                    provider="openai",
                    file_id=file_id,
                    filename=_optional_str(getattr(item, "filename", None)),
                    purpose=_optional_str(getattr(item, "purpose", None)),
                    mime_type=_optional_str(getattr(item, "mime_type", None)),
                    bytes=_optional_int(getattr(item, "bytes", None)),
                    created_at=_format_openai_timestamp(getattr(item, "created_at", None)),
                    updated_at=None,
                    bucket=None,
                    object_name=None,
                )
                if filename and remote_item.filename != filename:
                    continue
                seen_file_ids.add(file_id)
                items.append(remote_item)
                if max_items is not None and len(items) >= max_items:
                    return items
        return items
    finally:
        await client.close()


async def _collect_anthropic_files(
    *,
    max_items: int | None,
    filename: str | None,
) -> list[RemoteProviderFile]:
    client = build_anthropic_client()
    try:
        items: list[RemoteProviderFile] = []
        async for item in client.beta.files.list(
            betas=[ANTHROPIC_FILES_BETA],
            limit=_resolve_page_size(max_items),
        ):
            remote_item = RemoteProviderFile(
                provider="anthropic",
                file_id=str(getattr(item, "id", "")),
                filename=_optional_str(getattr(item, "filename", None)),
                purpose=None,
                mime_type=_optional_str(getattr(item, "mime_type", None))
                or _optional_str(getattr(item, "content_type", None)),
                bytes=_optional_int(getattr(item, "size_bytes", None)),
                created_at=_optional_str(getattr(item, "created_at", None)),
                updated_at=_optional_str(getattr(item, "updated_at", None)),
                bucket=None,
                object_name=None,
            )
            if filename and remote_item.filename != filename:
                continue
            items.append(remote_item)
            if max_items is not None and len(items) >= max_items:
                return items
        return items
    finally:
        await client.close()


async def _collect_vertex_files(
    *,
    max_items: int | None,
    filename: str | None,
    bucket: str | None,
    prefix: str | None,
) -> list[RemoteProviderFile]:
    bucket_name, normalized_prefix = _resolve_vertex_scope(bucket=bucket, prefix=prefix)
    return await asyncio.to_thread(
        _collect_vertex_files_sync,
        bucket_name,
        normalized_prefix,
        max_items,
        filename,
    )


def _collect_vertex_files_sync(
    bucket_name: str,
    prefix: str,
    max_items: int | None,
    filename: str | None,
) -> list[RemoteProviderFile]:
    storage_client = build_storage_client()
    list_prefix = f"{prefix}/" if prefix else None
    iterator = storage_client.list_blobs(bucket_name, prefix=list_prefix)
    items: list[RemoteProviderFile] = []

    for blob in iterator:
        object_name = _optional_str(getattr(blob, "name", None))
        if not object_name:
            continue
        blob_filename = _optional_str(basename(object_name))
        if filename and blob_filename != filename:
            continue
        items.append(
            RemoteProviderFile(
                provider="vertex_ai",
                file_id=f"gs://{bucket_name}/{object_name}",
                filename=blob_filename,
                purpose="gcs_object",
                mime_type=_optional_str(getattr(blob, "content_type", None)),
                bytes=_optional_int(getattr(blob, "size", None)),
                created_at=_format_datetime(getattr(blob, "time_created", None)),
                updated_at=_format_datetime(getattr(blob, "updated", None)),
                bucket=bucket_name,
                object_name=object_name,
            )
        )
        if max_items is not None and len(items) >= max_items:
            break

    return items


async def _collect_consistency_state(
    *,
    provider: str,
    bucket: str | None,
    prefix: str | None,
) -> dict[str, Any]:
    providers = _resolve_requested_providers(provider)
    db_provider_states = list_all_db_provider_states(providers=providers)
    local_blob_summary = list_local_blob_summary()
    remote_files_by_provider = {
        provider_name: await _collect_remote_files(
            provider=provider_name,
            max_items=None,
            filename=None,
            bucket=bucket,
            prefix=prefix,
        )
        for provider_name in providers
    }

    db_provider_file_ids: dict[str, set[str]] = defaultdict(set)
    remote_file_ids: dict[str, set[str]] = defaultdict(set)
    duplicate_provider_file_ids: dict[str, dict[str, list[DbProviderStateRow]]] = defaultdict(lambda: defaultdict(list))
    db_refs_missing_remote: list[DbProviderStateRow] = []
    invalid_ready_without_file_id: list[DbProviderStateRow] = []
    invalid_file_id_with_nonready_status: list[DbProviderStateRow] = []

    for row in db_provider_states:
        if row.remote_file_status == "ready" and not row.provider_file_id:
            invalid_ready_without_file_id.append(row)
        if row.provider_file_id and row.remote_file_status != "ready":
            invalid_file_id_with_nonready_status.append(row)
        if row.provider_file_id:
            db_provider_file_ids[row.provider].add(row.provider_file_id)
            duplicate_provider_file_ids[row.provider][row.provider_file_id].append(row)

    for provider_name, remote_files in remote_files_by_provider.items():
        remote_file_ids[provider_name] = {item.file_id for item in remote_files}

    for row in db_provider_states:
        if row.provider_file_id and row.provider_file_id not in remote_file_ids[row.provider]:
            db_refs_missing_remote.append(row)

    remote_files_missing_db_ref: dict[str, list[RemoteProviderFile]] = {}
    for provider_name, remote_files in remote_files_by_provider.items():
        remote_files_missing_db_ref[provider_name] = [
            item
            for item in remote_files
            if item.file_id not in db_provider_file_ids[provider_name]
        ]

    duplicate_db_provider_file_ids = [
        {
            "provider": provider_name,
            "provider_file_id": provider_file_id,
            "rows": [asdict(row) for row in rows],
        }
        for provider_name, grouped in duplicate_provider_file_ids.items()
        for provider_file_id, rows in grouped.items()
        if provider_file_id and len(rows) > 1
    ]

    local_blob_count = len(local_blob_summary["all_blobs"])
    local_blob_total_bytes = sum(item.byte_size for item in local_blob_summary["all_blobs"])
    remote_counts = {provider_name: len(remote_files_by_provider[provider_name]) for provider_name in providers}
    remote_bytes = {
        provider_name: sum(item.bytes or 0 for item in remote_files_by_provider[provider_name])
        for provider_name in providers
    }
    tracked_ref_counts = {
        provider_name: sum(
            1
            for row in db_provider_states
            if row.provider == provider_name and row.provider_file_id is not None
        )
        for provider_name in providers
    }
    ready_ref_counts = {
        provider_name: sum(
            1
            for row in db_provider_states
            if row.provider == provider_name and row.provider_file_id is not None and row.remote_file_status == "ready"
        )
        for provider_name in providers
    }

    return {
        "providers": providers,
        "vertex_scope": {
            "bucket": _resolve_vertex_scope(bucket=bucket, prefix=prefix)[0] if "vertex_ai" in providers else None,
            "prefix": _resolve_vertex_scope(bucket=bucket, prefix=prefix)[1] if "vertex_ai" in providers else None,
        },
        "local_blob_count": local_blob_count,
        "local_blob_total_bytes": local_blob_total_bytes,
        "local_orphan_blobs": local_blob_summary["orphan_blobs"],
        "db_provider_states": db_provider_states,
        "remote_files_by_provider": remote_files_by_provider,
        "db_refs_missing_remote": db_refs_missing_remote,
        "remote_files_missing_db_ref": remote_files_missing_db_ref,
        "duplicate_db_provider_file_ids": duplicate_db_provider_file_ids,
        "invalid_ready_without_file_id": invalid_ready_without_file_id,
        "invalid_file_id_with_nonready_status": invalid_file_id_with_nonready_status,
        "tracked_ref_counts": tracked_ref_counts,
        "ready_ref_counts": ready_ref_counts,
        "remote_counts": remote_counts,
        "remote_bytes": remote_bytes,
    }


def list_all_db_provider_states(*, providers: list[str]) -> list[DbProviderStateRow]:
    with SessionLocal() as db:
        states = db.execute(
            select(StoredFileProviderState)
            .where(StoredFileProviderState.provider.in_(providers))
            .order_by(
                StoredFileProviderState.provider.asc(),
                StoredFileProviderState.created_at.asc(),
                StoredFileProviderState.id.asc(),
            )
        ).scalars().all()
        return [_state_to_row(state) for state in states]


def list_local_blob_summary() -> dict[str, list[LocalBlobSummary]]:
    with SessionLocal() as db:
        stored_files = db.execute(
            select(StoredFile)
            .options(
                load_only(
                    StoredFile.id,
                    StoredFile.user_id,
                    StoredFile.byte_size,
                    StoredFile.created_at,
                ),
                selectinload(StoredFile.history_files).load_only(ChatHistoryFile.id),
            )
            .order_by(StoredFile.created_at.asc(), StoredFile.id.asc())
        ).scalars().unique().all()

        all_blobs = [
            LocalBlobSummary(
                stored_file_id=stored_file.id,
                user_id=stored_file.user_id,
                byte_size=stored_file.byte_size,
                created_at=stored_file.created_at,
            )
            for stored_file in stored_files
        ]
        orphan_blobs = [
            LocalBlobSummary(
                stored_file_id=stored_file.id,
                user_id=stored_file.user_id,
                byte_size=stored_file.byte_size,
                created_at=stored_file.created_at,
            )
            for stored_file in stored_files
            if not stored_file.history_files
        ]
        return {
            "all_blobs": all_blobs,
            "orphan_blobs": orphan_blobs,
        }


def _build_consistency_payload(
    *,
    state: dict[str, Any],
    sample_limit: int,
) -> dict[str, Any]:
    limit = max(1, sample_limit)
    providers = state["providers"]
    remote_counts = state["remote_counts"]
    tracked_ref_counts = state["tracked_ref_counts"]
    ready_ref_counts = state["ready_ref_counts"]
    remote_bytes = state["remote_bytes"]

    count_mismatch_warning = None
    if len(providers) > 1 and len({remote_counts[provider_name] for provider_name in providers}) > 1:
        count_mismatch_warning = {
            "message": "Remote file counts differ across providers.",
            "remote_counts": remote_counts,
            "tracked_db_ref_counts": tracked_ref_counts,
            "ready_db_ref_counts": ready_ref_counts,
        }

    remote_vs_local_warning = {
        provider_name: {
            "remote_count": remote_counts[provider_name],
            "local_blob_count": state["local_blob_count"],
            "remote_exceeds_local_blob_count": remote_counts[provider_name] > state["local_blob_count"],
        }
        for provider_name in providers
    }

    return {
        "scope": {
            "providers": providers,
            "vertex_bucket": state["vertex_scope"]["bucket"],
            "vertex_prefix": state["vertex_scope"]["prefix"],
            "remote_storage_is_assumed_product_owned": True,
        },
        "local_db": {
            "stored_blob_count": state["local_blob_count"],
            "stored_blob_total_bytes": state["local_blob_total_bytes"],
            "orphan_blob_count": len(state["local_orphan_blobs"]),
            "orphan_blob_samples": [asdict(item) for item in state["local_orphan_blobs"][:limit]],
        },
        "db_provider_refs": {
            provider_name: {
                "provider_state_count": sum(
                    1 for row in state["db_provider_states"] if row.provider == provider_name
                ),
                "tracked_remote_ref_count": tracked_ref_counts[provider_name],
                "ready_remote_ref_count": ready_ref_counts[provider_name],
                "remote_status_counts": _count_remote_statuses(
                    state["db_provider_states"],
                    provider=provider_name,
                ),
                "token_count_status_counts": _count_token_statuses(
                    state["db_provider_states"],
                    provider=provider_name,
                ),
            }
            for provider_name in providers
        },
        "remote_storage": {
            provider_name: {
                "file_count": remote_counts[provider_name],
                "total_bytes": remote_bytes[provider_name],
                "file_samples": [
                    asdict(item)
                    for item in state["remote_files_by_provider"][provider_name][:limit]
                ],
            }
            for provider_name in providers
        },
        "problems": {
            "db_refs_missing_remote_count": len(state["db_refs_missing_remote"]),
            "db_refs_missing_remote": [asdict(item) for item in state["db_refs_missing_remote"][:limit]],
            "remote_files_missing_db_ref_count": sum(
                len(items) for items in state["remote_files_missing_db_ref"].values()
            ),
            "remote_files_missing_db_ref": {
                provider_name: [asdict(item) for item in items[:limit]]
                for provider_name, items in state["remote_files_missing_db_ref"].items()
            },
            "duplicate_db_provider_file_id_count": len(state["duplicate_db_provider_file_ids"]),
            "duplicate_db_provider_file_ids": state["duplicate_db_provider_file_ids"][:limit],
            "invalid_ready_without_file_id_count": len(state["invalid_ready_without_file_id"]),
            "invalid_ready_without_file_id": [
                asdict(item)
                for item in state["invalid_ready_without_file_id"][:limit]
            ],
            "invalid_file_id_with_nonready_status_count": len(state["invalid_file_id_with_nonready_status"]),
            "invalid_file_id_with_nonready_status": [
                asdict(item)
                for item in state["invalid_file_id_with_nonready_status"][:limit]
            ],
            "provider_count_mismatch_warning": count_mismatch_warning,
            "remote_exceeds_local_blob_warning": remote_vs_local_warning,
        },
        "notes": [
            "Remote file counts larger than local stored blob count are a strong signal of remote orphan files.",
            "Cross-provider remote count mismatches are worth inspecting, but the current runtime refreshes last_used_at only for the provider used on send, so unequal provider counts are not automatic corruption.",
            "reconcile-consistency --apply clears DB refs whose remote file is gone and deletes remote files that have no DB ref.",
        ],
    }


def _count_remote_statuses(rows: list[DbProviderStateRow], *, provider: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.provider == provider:
            counts[row.remote_file_status] += 1
    return dict(sorted(counts.items()))


def _count_token_statuses(rows: list[DbProviderStateRow], *, provider: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.provider == provider:
            counts[row.token_count_status] += 1
    return dict(sorted(counts.items()))


def _state_to_row(state: StoredFileProviderState) -> DbProviderStateRow:
    return DbProviderStateRow(
        provider=state.provider,
        stored_file_id=state.stored_file_id,
        token_count=state.token_count,
        token_count_status=state.token_count_status,
        token_count_error=state.token_count_error,
        provider_file_id=state.provider_file_id,
        remote_file_status=state.remote_file_status,
        remote_file_error=state.remote_file_error,
        count_model_id=state.count_model_id,
        uploaded_at=state.uploaded_at,
        last_used_at=state.last_used_at,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def _history_file_to_row(history_file: ChatHistoryFile) -> DbHistoryFileRow:
    return DbHistoryFileRow(
        chat_history_file_id=history_file.id,
        chat_history_id=history_file.chat_history_id,
        display_name=history_file.display_name,
        mime_type=history_file.mime_type,
        byte_size=history_file.byte_size,
        is_active=history_file.is_active,
        created_at=history_file.created_at,
        updated_at=history_file.updated_at,
    )


def _resolve_requested_providers(provider: str) -> list[str]:
    if provider == "all":
        return list(SUPPORTED_PROVIDERS)
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    return [provider]


def _resolve_page_size(max_items: int | None) -> int:
    if max_items is None:
        return DEFAULT_REMOTE_PAGE_SIZE
    return max(1, min(max_items, DEFAULT_REMOTE_PAGE_SIZE))


def _resolve_vertex_scope(*, bucket: str | None, prefix: str | None) -> tuple[str, str]:
    bucket_name = _optional_str(bucket) or _optional_str(vertex_settings.attachment_gcs_bucket)
    if not bucket_name:
        raise RuntimeError("VERTEX_AI_ATTACHMENT_GCS_BUCKET is not configured")

    resolved_prefix = prefix if prefix is not None else vertex_settings.attachment_gcs_prefix
    return bucket_name, resolved_prefix.strip().strip("/")


def _format_openai_timestamp(value: object) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value)).isoformat()
    except (TypeError, ValueError, OSError):
        return _optional_str(value)


def _format_datetime(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return _optional_str(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    main()
