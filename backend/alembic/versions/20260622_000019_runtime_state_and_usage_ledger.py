"""Add runtime deadlines, usage ledger, and attachment blob lifecycle.

Revision ID: 20260622_000019
Revises: 20260619_000018
Create Date: 2026-06-22 00:00:19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260622_000019"
down_revision = "20260619_000018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chat_messages", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_chat_messages_deadline_at", "chat_messages", ["deadline_at"], unique=False)
    op.execute(
        """
        UPDATE chat_messages
        SET deadline_at = updated_at
        WHERE role = 'assistant'
          AND status = 'streaming'
          AND deadline_at IS NULL
        """
    )

    op.add_column(
        "stored_files",
        sa.Column("lifecycle_state", sa.String(length=16), nullable=False, server_default="active"),
    )
    op.add_column("stored_files", sa.Column("delete_error", sa.Text(), nullable=True))
    op.add_column(
        "stored_files",
        sa.Column("delete_attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("stored_files", sa.Column("delete_last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stored_files", sa.Column("delete_next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_stored_files_lifecycle_state",
        "stored_files",
        "lifecycle_state IN ('active', 'pending_delete', 'delete_failed')",
    )
    op.create_index(
        "ix_stored_files_lifecycle_retry",
        "stored_files",
        ["lifecycle_state", "delete_next_attempt_at"],
        unique=False,
    )
    op.alter_column("stored_files", "lifecycle_state", server_default=None)
    op.alter_column("stored_files", "delete_attempt_count", server_default=None)

    op.create_table(
        "usage_ledger_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("auth_session_id", sa.String(length=36), nullable=True),
        sa.Column("chat_history_id_snapshot", sa.String(length=36), nullable=True),
        sa.Column("chat_message_id_snapshot", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("tool_ids", sa.JSON(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_code", sa.String(length=64), nullable=True),
        sa.Column("input_tokens_reported", sa.Integer(), nullable=True),
        sa.Column("output_tokens_reported", sa.Integer(), nullable=True),
        sa.Column("total_tokens_reported", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_write_input_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("tool_result_input_tokens", sa.Integer(), nullable=True),
        sa.Column("web_search_requests", sa.Integer(), nullable=True),
        sa.Column("file_search_requests", sa.Integer(), nullable=True),
        sa.Column("code_execution_requests", sa.Integer(), nullable=True),
        sa.Column("price_estimate", sa.JSON(), nullable=True),
        sa.Column("provider_raw_usage", sa.JSON(), nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(18, 9), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("pricing_version", sa.String(length=64), nullable=True),
        sa.Column("price_completeness", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('billable', 'adjustment')",
            name="ck_usage_ledger_events_status",
        ),
        sa.CheckConstraint(
            "source IN ('chat_completion', 'backfill', 'operator_adjustment')",
            name="ck_usage_ledger_events_source",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_ledger_events_user_id", "usage_ledger_events", ["user_id"], unique=False)
    op.create_index(
        "ix_usage_ledger_events_user_created",
        "usage_ledger_events",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_ledger_events_provider_created",
        "usage_ledger_events",
        ["provider", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_ledger_events_message",
        "usage_ledger_events",
        ["chat_message_id_snapshot"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO usage_ledger_events (
            id,
            user_id,
            chat_history_id_snapshot,
            chat_message_id_snapshot,
            provider,
            model_id,
            tool_ids,
            operation,
            source,
            status,
            result_code,
            input_tokens_reported,
            output_tokens_reported,
            total_tokens_reported,
            cached_input_tokens,
            cache_write_input_tokens,
            reasoning_tokens,
            tool_result_input_tokens,
            web_search_requests,
            file_search_requests,
            code_execution_requests,
            price_estimate,
            provider_raw_usage,
            total_cost_usd,
            currency,
            pricing_version,
            price_completeness,
            created_at
        )
        SELECT
            cm.id,
            ch.user_id,
            ch.id,
            cm.id,
            cm.provider,
            cm.model_id,
            COALESCE(cm.tool_ids, '[]'::json),
            'chat_completion',
            'backfill',
            'billable',
            cm.result_code,
            NULLIF(cm.usage->'normalized'->>'input_tokens_reported', '')::integer,
            NULLIF(cm.usage->'normalized'->>'output_tokens_reported', '')::integer,
            NULLIF(cm.usage->'normalized'->>'total_tokens_reported', '')::integer,
            NULLIF(cm.usage->'normalized'->>'cached_input_tokens', '')::integer,
            NULLIF(cm.usage->'normalized'->>'cache_write_input_tokens', '')::integer,
            NULLIF(cm.usage->'normalized'->>'reasoning_tokens', '')::integer,
            NULLIF(cm.usage->'normalized'->>'tool_result_input_tokens', '')::integer,
            NULLIF(cm.usage->'normalized'->>'web_search_requests', '')::integer,
            NULLIF(cm.usage->'normalized'->>'file_search_requests', '')::integer,
            NULLIF(cm.usage->'normalized'->>'code_execution_requests', '')::integer,
            cm.usage->'price_estimate',
            cm.usage->'provider_raw',
            (cm.usage->'price_estimate'->>'total_cost_usd')::numeric,
            COALESCE(cm.usage->'price_estimate'->>'currency', 'USD'),
            cm.usage->'price_estimate'->>'pricing_version',
            cm.usage->'price_estimate'->>'completeness',
            COALESCE(cm.completed_at, cm.updated_at, cm.created_at)
        FROM chat_messages cm
        JOIN chat_histories ch ON ch.id = cm.chat_history_id
        WHERE cm.role = 'assistant'
          AND cm.usage IS NOT NULL
          AND cm.usage->'price_estimate' IS NOT NULL
          AND cm.usage->'price_estimate'->>'total_cost_usd' IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_usage_ledger_events_message", table_name="usage_ledger_events")
    op.drop_index("ix_usage_ledger_events_provider_created", table_name="usage_ledger_events")
    op.drop_index("ix_usage_ledger_events_user_created", table_name="usage_ledger_events")
    op.drop_index("ix_usage_ledger_events_user_id", table_name="usage_ledger_events")
    op.drop_table("usage_ledger_events")

    op.drop_index("ix_stored_files_lifecycle_retry", table_name="stored_files")
    op.drop_constraint("ck_stored_files_lifecycle_state", "stored_files", type_="check")
    op.drop_column("stored_files", "delete_next_attempt_at")
    op.drop_column("stored_files", "delete_last_attempt_at")
    op.drop_column("stored_files", "delete_attempt_count")
    op.drop_column("stored_files", "delete_error")
    op.drop_column("stored_files", "lifecycle_state")

    op.drop_index("ix_chat_messages_deadline_at", table_name="chat_messages")
    op.drop_column("chat_messages", "deadline_at")
    op.drop_column("chat_messages", "first_response_at")
