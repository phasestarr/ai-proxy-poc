"""
Purpose:
- Run Alembic migrations for the backend PostgreSQL schema.

Responsibilities:
- Build an Alembic config rooted at the repository's `proxy-api` directory
- Apply all pending migrations before the app starts serving requests
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config.settings import settings
from app.db.postgres.session import engine

INITIAL_REVISION = "20260420_000001"
LEGACY_PRE_ALEMBIC_TABLES = {
    "users",
    "auth_identities",
    "auth_sessions",
    "auth_provider_sessions",
    "oauth_transactions",
}
CURRENT_MANAGED_TABLES = {
    "users",
    "ms_identities",
    "guest_identities",
    "auth_sessions",
    "auth_provider_sessions",
    "auth_conflict_tickets",
    "oauth_transactions",
    "chat_histories",
    "chat_messages",
}
PRE_CHAT_HISTORY_MANAGED_TABLES = CURRENT_MANAGED_TABLES - {"chat_histories", "chat_messages"}
PRE_CONFLICT_TICKET_MANAGED_TABLES = PRE_CHAT_HISTORY_MANAGED_TABLES - {"auth_conflict_tickets"}


def run_database_migrations() -> None:
    project_root = Path(__file__).resolve().parents[3]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)

    existing_tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in existing_tables:
        current_tables_present = CURRENT_MANAGED_TABLES.intersection(existing_tables)
        legacy_tables_present = LEGACY_PRE_ALEMBIC_TABLES.intersection(existing_tables)

        if CURRENT_MANAGED_TABLES.issubset(existing_tables):
            command.stamp(config, "head")
            return

        if PRE_CHAT_HISTORY_MANAGED_TABLES.issubset(existing_tables):
            command.stamp(config, "20260420_000004")
            command.upgrade(config, "head")
            return

        if PRE_CONFLICT_TICKET_MANAGED_TABLES.issubset(existing_tables):
            command.stamp(config, "20260420_000003")
            command.upgrade(config, "head")
            return

        if LEGACY_PRE_ALEMBIC_TABLES.issubset(existing_tables):
            command.stamp(config, INITIAL_REVISION)
            command.upgrade(config, "head")
            return

        if current_tables_present or legacy_tables_present:
            missing_current_tables = ", ".join(sorted(CURRENT_MANAGED_TABLES - existing_tables)) or "none"
            missing_legacy_tables = ", ".join(sorted(LEGACY_PRE_ALEMBIC_TABLES - existing_tables)) or "none"
            raise RuntimeError(
                "Cannot baseline a partially initialized PostgreSQL schema. "
                f"Missing current managed tables: {missing_current_tables}. "
                f"Missing legacy managed tables: {missing_legacy_tables}."
            )

    command.upgrade(config, "head")
