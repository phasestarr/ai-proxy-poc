"""Simplify live chat operation state and remove product usage caches.

Revision ID: 20260708_000022
Revises: 20260625_000021
Create Date: 2026-07-08 00:00:22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260708_000022"
down_revision = "20260625_000021"
branch_labels = None
depends_on = None


LIVE_OPERATION_STATES = "('running', 'provider_streaming')"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _drop_index_if_exists(inspector, "chat_operations", "ix_chat_operations_scope_state")
    _drop_constraint_if_exists(inspector, "chat_operations", "ck_chat_operations_scope_type")
    _drop_constraint_if_exists(inspector, "chat_operations", "ck_chat_operations_operation_type")
    _drop_constraint_if_exists(inspector, "chat_operations", "ck_chat_operations_state")

    op.execute(
        """
        UPDATE chat_operations
        SET chat_history_id = scope_id
        WHERE scope_type = 'history'
          AND chat_history_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE chat_operations
        SET draft_id = scope_id
        WHERE scope_type = 'draft'
          AND draft_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE chat_operations
        SET state = CASE
            WHEN state IN ('validating', 'finalizing') THEN 'running'
            WHEN state = 'cancelled' THEN 'failed'
            ELSE state
        END
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                o.id,
                ROW_NUMBER() OVER (
                    PARTITION BY o.chat_history_id
                    ORDER BY
                        CASE WHEN h.active_operation_id = o.id THEN 0 ELSE 1 END,
                        o.updated_at DESC,
                        o.created_at DESC,
                        o.id DESC
                ) AS row_number
            FROM chat_operations o
            JOIN chat_histories h ON h.id = o.chat_history_id
            WHERE o.chat_history_id IS NOT NULL
              AND o.state IN ('running', 'provider_streaming')
        ),
        closed AS (
            UPDATE chat_operations o
            SET state = 'timed_out',
                result_code = COALESCE(o.result_code, 'duplicate_live_operation_recovered'),
                completed_at = COALESCE(o.completed_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            FROM ranked r
            WHERE o.id = r.id
              AND r.row_number > 1
            RETURNING o.id
        )
        UPDATE chat_histories h
        SET active_operation_id = NULL,
            active_operation_token = NULL,
            updated_at = CURRENT_TIMESTAMP
        FROM closed c
        WHERE h.active_operation_id = c.id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                o.id,
                ROW_NUMBER() OVER (
                    PARTITION BY o.draft_id
                    ORDER BY
                        CASE WHEN d.active_operation_id = o.id THEN 0 ELSE 1 END,
                        o.updated_at DESC,
                        o.created_at DESC,
                        o.id DESC
                ) AS row_number
            FROM chat_operations o
            JOIN chat_drafts d ON d.id = o.draft_id
            WHERE o.draft_id IS NOT NULL
              AND o.state IN ('running', 'provider_streaming')
        ),
        closed AS (
            UPDATE chat_operations o
            SET state = 'timed_out',
                result_code = COALESCE(o.result_code, 'duplicate_live_operation_recovered'),
                completed_at = COALESCE(o.completed_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            FROM ranked r
            WHERE o.id = r.id
              AND r.row_number > 1
            RETURNING o.id
        )
        UPDATE chat_drafts d
        SET active_operation_id = NULL,
            active_operation_token = NULL,
            updated_at = CURRENT_TIMESTAMP
        FROM closed c
        WHERE d.active_operation_id = c.id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                o.id,
                ROW_NUMBER() OVER (
                    PARTITION BY o.auth_session_id
                    ORDER BY
                        o.updated_at DESC,
                        o.created_at DESC,
                        o.id DESC
                ) AS row_number
            FROM chat_operations o
            WHERE o.auth_session_id IS NOT NULL
              AND o.draft_id IS NOT NULL
              AND o.operation_type = 'attach_file'
              AND o.state IN ('running', 'provider_streaming')
        ),
        closed AS (
            UPDATE chat_operations o
            SET state = 'timed_out',
                result_code = COALESCE(o.result_code, 'duplicate_live_session_draft_attach_recovered'),
                completed_at = COALESCE(o.completed_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            FROM ranked r
            WHERE o.id = r.id
              AND r.row_number > 1
            RETURNING o.id
        )
        UPDATE chat_drafts d
        SET active_operation_id = NULL,
            active_operation_token = NULL,
            updated_at = CURRENT_TIMESTAMP
        FROM closed c
        WHERE d.active_operation_id = c.id
        """
    )

    _drop_column_if_exists(inspector, "chat_operations", "scope_type")
    _drop_column_if_exists(inspector, "chat_operations", "scope_id")

    op.create_check_constraint(
        "ck_chat_operations_operation_type",
        "chat_operations",
        "operation_type IN ('send', 'attach_file', 'delete_file', 'toggle_file', 'delete_history', 'update_metadata')",
    )
    op.create_check_constraint(
        "ck_chat_operations_state",
        "chat_operations",
        "state IN ('running', 'provider_streaming', 'succeeded', 'failed', 'timed_out')",
    )
    op.create_check_constraint(
        "ck_chat_operations_exactly_one_scope",
        "chat_operations",
        "((chat_history_id IS NOT NULL AND draft_id IS NULL) OR (chat_history_id IS NULL AND draft_id IS NOT NULL))",
    )
    op.create_check_constraint(
        "ck_chat_operations_draft_attach_only",
        "chat_operations",
        "draft_id IS NULL OR operation_type = 'attach_file'",
    )
    op.create_index(
        "uq_chat_operations_live_history",
        "chat_operations",
        ["chat_history_id"],
        unique=True,
        postgresql_where=sa.text(f"chat_history_id IS NOT NULL AND state IN {LIVE_OPERATION_STATES}"),
    )
    op.create_index(
        "uq_chat_operations_live_draft",
        "chat_operations",
        ["draft_id"],
        unique=True,
        postgresql_where=sa.text(f"draft_id IS NOT NULL AND state IN {LIVE_OPERATION_STATES}"),
    )
    op.create_index(
        "uq_chat_operations_live_session_draft_attach",
        "chat_operations",
        ["auth_session_id"],
        unique=True,
        postgresql_where=sa.text(
            "auth_session_id IS NOT NULL AND draft_id IS NOT NULL "
            f"AND operation_type = 'attach_file' AND state IN {LIVE_OPERATION_STATES}"
        ),
    )

    _drop_column_if_exists(inspector, "chat_histories", "usage_summary")
    _drop_column_if_exists(inspector, "chat_messages", "usage")
    _drop_column_if_exists(inspector, "chat_history_memories", "usage")

    _drop_index_if_exists(inspector, "chat_context_checkpoints", "ix_chat_context_checkpoints_user_status")
    _drop_constraint_if_exists(inspector, "chat_context_checkpoints", "ck_chat_context_checkpoints_status")
    for column_name in ("usage", "error_detail", "requested_at", "status"):
        _drop_column_if_exists(inspector, "chat_context_checkpoints", column_name)

    op.execute("DELETE FROM stored_file_provider_states WHERE token_count IS NULL")
    _drop_index_if_exists(inspector, "stored_file_provider_states", "ix_stored_file_provider_states_provider_status")
    _drop_constraint_if_exists(
        inspector,
        "stored_file_provider_states",
        "ck_stored_file_provider_states_token_count_status",
    )
    _drop_constraint_if_exists(
        inspector,
        "stored_file_provider_states",
        "ck_stored_file_provider_states_remote_file_status",
    )
    for column_name in (
        "token_count_error",
        "token_count_status",
        "remote_file_error",
        "remote_file_status",
    ):
        _drop_column_if_exists(inspector, "stored_file_provider_states", column_name)
    op.alter_column("stored_file_provider_states", "token_count", nullable=False)
    op.create_index(
        "ix_stored_file_provider_states_provider_file",
        "stored_file_provider_states",
        ["provider", "provider_file_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stored_file_provider_states_provider_file", table_name="stored_file_provider_states")
    op.alter_column("stored_file_provider_states", "token_count", nullable=True)
    op.add_column(
        "stored_file_provider_states",
        sa.Column("remote_file_status", sa.String(length=16), nullable=False, server_default="not_uploaded"),
    )
    op.add_column("stored_file_provider_states", sa.Column("remote_file_error", sa.Text(), nullable=True))
    op.add_column(
        "stored_file_provider_states",
        sa.Column("token_count_status", sa.String(length=16), nullable=False, server_default="ready"),
    )
    op.add_column("stored_file_provider_states", sa.Column("token_count_error", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE stored_file_provider_states
        SET remote_file_status = CASE
            WHEN provider_file_id IS NULL THEN 'not_uploaded'
            ELSE 'ready'
        END
        """
    )
    op.alter_column("stored_file_provider_states", "remote_file_status", server_default=None)
    op.alter_column("stored_file_provider_states", "token_count_status", server_default=None)
    op.create_check_constraint(
        "ck_stored_file_provider_states_token_count_status",
        "stored_file_provider_states",
        "token_count_status IN ('ready', 'failed', 'unsupported')",
    )
    op.create_check_constraint(
        "ck_stored_file_provider_states_remote_file_status",
        "stored_file_provider_states",
        "remote_file_status IN ('not_uploaded', 'ready', 'failed', 'unsupported')",
    )
    op.create_index(
        "ix_stored_file_provider_states_provider_status",
        "stored_file_provider_states",
        ["provider", "remote_file_status"],
        unique=False,
    )

    op.add_column("chat_context_checkpoints", sa.Column("status", sa.String(length=16), nullable=False, server_default="ready"))
    op.add_column("chat_context_checkpoints", sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chat_context_checkpoints", sa.Column("error_detail", sa.Text(), nullable=True))
    op.add_column("chat_context_checkpoints", sa.Column("usage", sa.JSON(), nullable=True))
    op.alter_column("chat_context_checkpoints", "status", server_default=None)
    op.create_check_constraint(
        "ck_chat_context_checkpoints_status",
        "chat_context_checkpoints",
        "status IN ('building', 'ready', 'failed')",
    )
    op.create_index(
        "ix_chat_context_checkpoints_user_status",
        "chat_context_checkpoints",
        ["user_id", "status"],
        unique=False,
    )

    op.add_column("chat_history_memories", sa.Column("usage", sa.JSON(), nullable=True))
    op.add_column("chat_messages", sa.Column("usage", sa.JSON(), nullable=True))
    op.add_column("chat_histories", sa.Column("usage_summary", sa.JSON(), nullable=True))

    op.drop_index("uq_chat_operations_live_session_draft_attach", table_name="chat_operations")
    op.drop_index("uq_chat_operations_live_draft", table_name="chat_operations")
    op.drop_index("uq_chat_operations_live_history", table_name="chat_operations")
    op.drop_constraint("ck_chat_operations_draft_attach_only", "chat_operations", type_="check")
    op.drop_constraint("ck_chat_operations_exactly_one_scope", "chat_operations", type_="check")
    op.drop_constraint("ck_chat_operations_state", "chat_operations", type_="check")
    op.drop_constraint("ck_chat_operations_operation_type", "chat_operations", type_="check")

    op.add_column("chat_operations", sa.Column("scope_id", sa.String(length=36), nullable=True))
    op.add_column("chat_operations", sa.Column("scope_type", sa.String(length=16), nullable=True))
    op.execute(
        """
        UPDATE chat_operations
        SET scope_type = CASE WHEN chat_history_id IS NOT NULL THEN 'history' ELSE 'draft' END,
            scope_id = COALESCE(chat_history_id, draft_id),
            state = CASE WHEN state = 'running' THEN 'validating' ELSE state END,
            operation_type = CASE WHEN operation_type = 'update_metadata' THEN 'send' ELSE operation_type END
        """
    )
    op.alter_column("chat_operations", "scope_type", nullable=False)
    op.alter_column("chat_operations", "scope_id", nullable=False)
    op.create_check_constraint(
        "ck_chat_operations_scope_type",
        "chat_operations",
        "scope_type IN ('history', 'draft')",
    )
    op.create_check_constraint(
        "ck_chat_operations_operation_type",
        "chat_operations",
        "operation_type IN ('send', 'attach_file', 'delete_file', 'toggle_file', 'delete_history')",
    )
    op.create_check_constraint(
        "ck_chat_operations_state",
        "chat_operations",
        "state IN ('validating', 'provider_streaming', 'finalizing', 'succeeded', 'failed', 'timed_out', 'cancelled')",
    )
    op.create_index(
        "ix_chat_operations_scope_state",
        "chat_operations",
        ["scope_type", "scope_id", "state"],
        unique=False,
    )


def _drop_constraint_if_exists(inspector, table_name: str, constraint_name: str) -> None:
    constraints = {constraint["name"] for constraint in inspector.get_check_constraints(table_name)}
    if constraint_name in constraints:
        op.drop_constraint(constraint_name, table_name, type_="check")


def _drop_index_if_exists(inspector, table_name: str, index_name: str) -> None:
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in indexes:
        op.drop_index(index_name, table_name=table_name)


def _drop_column_if_exists(inspector, table_name: str, column_name: str) -> None:
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in columns:
        op.drop_column(table_name, column_name)
