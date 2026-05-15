from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db.postgres.models.chat_attachment import StoredFileProviderState
from app.db.postgres.session import SessionLocal
from app.providers.anthropic.attachments import ANTHROPIC_FILES_BETA
from app.providers.anthropic.client import build_anthropic_client
from app.providers.openai.client import build_openai_client


@dataclass(slots=True)
class DbProviderRef:
    provider: str
    stored_file_id: str
    provider_file_id: str
    remote_file_status: str
    uploaded_at: datetime | None
    last_used_at: datetime | None


@dataclass(slots=True)
class RemoteProviderFile:
    provider: str
    file_id: str
    filename: str | None
    purpose: str | None
    bytes: int | None
    created_at: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect and clean provider-managed attachment files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_db_parser = subparsers.add_parser("list-db", help="List DB-tracked provider file refs.")
    list_db_parser.add_argument("--provider", choices=["openai", "anthropic"], default=None)

    list_openai_parser = subparsers.add_parser("list-openai", help="List OpenAI user_data and vision files.")
    list_openai_parser.add_argument("--limit", type=int, default=100)
    list_openai_parser.add_argument("--filename", default=None)

    list_anthropic_parser = subparsers.add_parser("list-anthropic", help="List Anthropic managed files.")
    list_anthropic_parser.add_argument("--limit", type=int, default=100)
    list_anthropic_parser.add_argument("--filename", default=None)

    cleanup_parser = subparsers.add_parser(
        "cleanup-filename",
        help="Delete matching remote files and clear matching DB provider refs.",
    )
    cleanup_parser.add_argument("--filename", required=True)
    cleanup_parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "all"],
        default="all",
    )
    cleanup_parser.add_argument(
        "--skip-db-clear",
        action="store_true",
        help="Delete remote files only and leave DB provider refs unchanged.",
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
    if args.command == "list-openai":
        print_json(asyncio.run(list_openai_files(limit=args.limit, filename=args.filename)))
        return
    if args.command == "list-anthropic":
        print_json(asyncio.run(list_anthropic_files(limit=args.limit, filename=args.filename)))
        return
    if args.command == "cleanup-filename":
        print_json(
            asyncio.run(
                cleanup_filename(
                    filename=args.filename,
                    provider=args.provider,
                    clear_db=not args.skip_db_clear,
                )
            )
        )
        return
    raise SystemExit(f"unsupported command: {args.command}")


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=_json_default))


def list_db_provider_refs(*, provider: str | None) -> list[DbProviderRef]:
    with SessionLocal() as db:
        query = (
            select(
                StoredFileProviderState.provider,
                StoredFileProviderState.stored_file_id,
                StoredFileProviderState.provider_file_id,
                StoredFileProviderState.remote_file_status,
                StoredFileProviderState.uploaded_at,
                StoredFileProviderState.last_used_at,
            )
            .where(StoredFileProviderState.provider_file_id.is_not(None))
            .order_by(
                StoredFileProviderState.provider.asc(),
                StoredFileProviderState.uploaded_at.asc(),
                StoredFileProviderState.id.asc(),
            )
        )
        if provider is not None:
            query = query.where(StoredFileProviderState.provider == provider)

        return [
            DbProviderRef(
                provider=row.provider,
                stored_file_id=row.stored_file_id,
                provider_file_id=row.provider_file_id,
                remote_file_status=row.remote_file_status,
                uploaded_at=row.uploaded_at,
                last_used_at=row.last_used_at,
            )
            for row in db.execute(query).all()
        ]


async def list_openai_files(*, limit: int, filename: str | None) -> list[dict[str, Any]]:
    client = build_openai_client()
    try:
        items: list[RemoteProviderFile] = []
        for purpose in ("user_data", "vision"):
            page = await client.files.list(
                purpose=purpose,
                order="desc",
                limit=max(1, min(limit, 10_000)),
            )
            items.extend(
                RemoteProviderFile(
                    provider="openai",
                    file_id=str(getattr(item, "id", "")),
                    filename=_optional_str(getattr(item, "filename", None)),
                    purpose=_optional_str(getattr(item, "purpose", None)),
                    bytes=_optional_int(getattr(item, "bytes", None)),
                    created_at=_format_openai_timestamp(getattr(item, "created_at", None)),
                )
                for item in getattr(page, "data", [])
            )
    finally:
        await client.close()

    if filename:
        items = [item for item in items if item.filename == filename]
    return [asdict(item) for item in items]


async def list_anthropic_files(*, limit: int, filename: str | None) -> list[dict[str, Any]]:
    client = build_anthropic_client()
    try:
        page = await client.beta.files.list(
            betas=[ANTHROPIC_FILES_BETA],
            limit=max(1, min(limit, 1_000)),
        )
        items = [
            RemoteProviderFile(
                provider="anthropic",
                file_id=str(getattr(item, "id", "")),
                filename=_optional_str(getattr(item, "filename", None)),
                purpose=None,
                bytes=_optional_int(getattr(item, "size_bytes", None)),
                created_at=_optional_str(getattr(item, "created_at", None)),
            )
            for item in getattr(page, "data", [])
        ]
    finally:
        await client.close()

    if filename:
        items = [item for item in items if item.filename == filename]
    return [asdict(item) for item in items]


async def cleanup_filename(
    *,
    filename: str,
    provider: str,
    clear_db: bool,
) -> dict[str, Any]:
    requested_providers = ["openai", "anthropic"] if provider == "all" else [provider]
    deleted_remote_files: list[dict[str, str]] = []
    db_cleared_refs: list[dict[str, str]] = []

    if "openai" in requested_providers:
        openai_files = await list_openai_files(limit=10_000, filename=filename)
        if openai_files:
            client = build_openai_client()
            try:
                for item in openai_files:
                    await client.files.delete(item["file_id"])
                    deleted_remote_files.append(
                        {"provider": "openai", "file_id": item["file_id"], "filename": filename}
                    )
            finally:
                await client.close()
        if clear_db:
            db_cleared_refs.extend(clear_db_provider_refs(provider="openai", provider_file_ids={item["file_id"] for item in openai_files}))

    if "anthropic" in requested_providers:
        anthropic_files = await list_anthropic_files(limit=1_000, filename=filename)
        if anthropic_files:
            client = build_anthropic_client()
            try:
                for item in anthropic_files:
                    await client.beta.files.delete(
                        item["file_id"],
                        betas=[ANTHROPIC_FILES_BETA],
                    )
                    deleted_remote_files.append(
                        {"provider": "anthropic", "file_id": item["file_id"], "filename": filename}
                    )
            finally:
                await client.close()
        if clear_db:
            db_cleared_refs.extend(clear_db_provider_refs(provider="anthropic", provider_file_ids={item["file_id"] for item in anthropic_files}))

    return {
        "filename": filename,
        "providers": requested_providers,
        "deleted_remote_files": deleted_remote_files,
        "cleared_db_refs": db_cleared_refs,
    }


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
            cleared.append(
                {
                    "provider": state.provider,
                    "stored_file_id": state.stored_file_id,
                    "provider_file_id": str(state.provider_file_id),
                }
            )
            state.provider_file_id = None
            state.remote_file_status = "not_uploaded"
            state.remote_file_error = None
            state.uploaded_at = None

        db.commit()
    return cleared


def _format_openai_timestamp(value: object) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value)).isoformat()
    except (TypeError, ValueError, OSError):
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
