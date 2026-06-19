"""Replace request rejection audit with operator events and usage caps.

Revision ID: 20260619_000018
Revises: 20260601_000017
Create Date: 2026-06-19 00:00:18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260619_000018"
down_revision = "20260601_000017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operator_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("auth_session_id", sa.String(length=36), nullable=True),
        sa.Column("chat_history_id", sa.String(length=36), nullable=True),
        sa.Column("chat_message_id", sa.String(length=36), nullable=True),
        sa.Column("stored_file_id", sa.String(length=36), nullable=True),
        sa.Column("draft_chat_id", sa.String(length=36), nullable=True),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("operation", sa.String(length=64), nullable=True),
        sa.Column("result_code", sa.String(length=64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "severity IN ('debug', 'info', 'warning', 'error', 'critical')",
            name="ck_operator_events_severity",
        ),
        sa.ForeignKeyConstraint(["auth_session_id"], ["auth_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operator_events_auth_session_id", "operator_events", ["auth_session_id"], unique=False)
    op.create_index("ix_operator_events_history_created", "operator_events", ["chat_history_id", "created_at"], unique=False)
    op.create_index("ix_operator_events_result_created", "operator_events", ["result_code", "created_at"], unique=False)
    op.create_index("ix_operator_events_severity_created", "operator_events", ["severity", "created_at"], unique=False)
    op.create_index("ix_operator_events_type_created", "operator_events", ["event_type", "created_at"], unique=False)
    op.create_index("ix_operator_events_user_created", "operator_events", ["user_id", "created_at"], unique=False)
    op.create_index("ix_operator_events_user_id", "operator_events", ["user_id"], unique=False)

    op.create_table(
        "user_usage_caps",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("cap_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("baseline_estimated_price_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chat_request_rejections" in inspector.get_table_names():
        op.execute(
            """
            INSERT INTO operator_events (
                id,
                event_type,
                severity,
                user_id,
                auth_session_id,
                chat_history_id,
                draft_chat_id,
                model_id,
                provider,
                operation,
                result_code,
                http_status,
                retry_after_seconds,
                message,
                detail,
                metadata,
                created_at
            )
            SELECT
                id,
                'chat_request_rejected',
                CASE WHEN http_status >= 500 THEN 'error' ELSE 'warning' END,
                user_id,
                auth_session_id,
                chat_history_id,
                draft_chat_id,
                model_id,
                provider,
                'chat_completion',
                error_code,
                http_status,
                retry_after_seconds,
                error_code,
                detail,
                json_build_object('source_table', 'chat_request_rejections'),
                created_at
            FROM chat_request_rejections
            """
        )
        op.drop_index("ix_chat_request_rejections_user_created", table_name="chat_request_rejections")
        op.drop_index("ix_chat_request_rejections_history_created", table_name="chat_request_rejections")
        op.drop_index("ix_chat_request_rejections_draft_created", table_name="chat_request_rejections")
        op.drop_index("ix_chat_request_rejections_code_created", table_name="chat_request_rejections")
        op.drop_index("ix_chat_request_rejections_user_id", table_name="chat_request_rejections")
        op.drop_index("ix_chat_request_rejections_auth_session_id", table_name="chat_request_rejections")
        op.drop_table("chat_request_rejections")


def downgrade() -> None:
    op.create_table(
        "chat_request_rejections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("auth_session_id", sa.String(length=36), nullable=True),
        sa.Column("chat_history_id", sa.String(length=36), nullable=True),
        sa.Column("draft_chat_id", sa.String(length=36), nullable=True),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["auth_session_id"], ["auth_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_request_rejections_auth_session_id", "chat_request_rejections", ["auth_session_id"], unique=False)
    op.create_index("ix_chat_request_rejections_user_id", "chat_request_rejections", ["user_id"], unique=False)
    op.create_index("ix_chat_request_rejections_code_created", "chat_request_rejections", ["error_code", "created_at"], unique=False)
    op.create_index("ix_chat_request_rejections_draft_created", "chat_request_rejections", ["draft_chat_id", "created_at"], unique=False)
    op.create_index("ix_chat_request_rejections_history_created", "chat_request_rejections", ["chat_history_id", "created_at"], unique=False)
    op.create_index("ix_chat_request_rejections_user_created", "chat_request_rejections", ["user_id", "created_at"], unique=False)
    op.execute(
        """
        INSERT INTO chat_request_rejections (
            id,
            user_id,
            auth_session_id,
            chat_history_id,
            draft_chat_id,
            model_id,
            provider,
            error_code,
            http_status,
            retry_after_seconds,
            detail,
            created_at
        )
        SELECT
            id,
            user_id,
            auth_session_id,
            chat_history_id,
            draft_chat_id,
            model_id,
            provider,
            COALESCE(result_code, event_type),
            http_status,
            retry_after_seconds,
            detail,
            created_at
        FROM operator_events
        WHERE event_type = 'chat_request_rejected'
        """
    )

    op.drop_table("user_usage_caps")
    op.drop_index("ix_operator_events_user_id", table_name="operator_events")
    op.drop_index("ix_operator_events_user_created", table_name="operator_events")
    op.drop_index("ix_operator_events_type_created", table_name="operator_events")
    op.drop_index("ix_operator_events_severity_created", table_name="operator_events")
    op.drop_index("ix_operator_events_result_created", table_name="operator_events")
    op.drop_index("ix_operator_events_history_created", table_name="operator_events")
    op.drop_index("ix_operator_events_auth_session_id", table_name="operator_events")
    op.drop_table("operator_events")
