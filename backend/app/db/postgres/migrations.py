"""
Purpose:
- Run Alembic migrations for the backend PostgreSQL schema.

Responsibilities:
- Build an Alembic config rooted at the repository's `backend` directory
- Apply all pending migrations before the app starts serving requests
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config.settings import settings
from app.db.postgres.session import engine

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
    "chat_history_memories",
    "chat_context_checkpoints",
    "operator_events",
    "usage_ledger_events",
    "user_usage_caps",
    "stored_files",
    "stored_file_provider_states",
    "chat_history_files",
    "chat_message_attachments",
}


def run_database_migrations() -> None:
    project_root = Path(__file__).resolve().parents[3]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)

    existing_tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in existing_tables:
        current_tables_present = CURRENT_MANAGED_TABLES.intersection(existing_tables)

        if current_tables_present:
            missing_current_tables = ", ".join(sorted(CURRENT_MANAGED_TABLES - existing_tables)) or "none"
            raise RuntimeError(
                "PostgreSQL schema contains ai-proxy tables but has no Alembic version. "
                "Automatic legacy baselining is no longer supported. "
                f"Missing current managed tables: {missing_current_tables}."
            )

    command.upgrade(config, "head")

