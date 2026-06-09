"""Add chat request rejection audit table.

Revision ID: 20260511_000013
Revises: 20260511_000012
Create Date: 2026-05-11 00:00:13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_000013"
down_revision = "20260511_000012"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.create_index(
        "ix_chat_request_rejections_auth_session_id",
        "chat_request_rejections",
        ["auth_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_request_rejections_user_id",
        "chat_request_rejections",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_request_rejections_code_created",
        "chat_request_rejections",
        ["error_code", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_request_rejections_draft_created",
        "chat_request_rejections",
        ["draft_chat_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_request_rejections_history_created",
        "chat_request_rejections",
        ["chat_history_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_request_rejections_user_created",
        "chat_request_rejections",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_request_rejections_user_created", table_name="chat_request_rejections")
    op.drop_index("ix_chat_request_rejections_history_created", table_name="chat_request_rejections")
    op.drop_index("ix_chat_request_rejections_draft_created", table_name="chat_request_rejections")
    op.drop_index("ix_chat_request_rejections_code_created", table_name="chat_request_rejections")
    op.drop_index("ix_chat_request_rejections_user_id", table_name="chat_request_rejections")
    op.drop_index("ix_chat_request_rejections_auth_session_id", table_name="chat_request_rejections")
    op.drop_table("chat_request_rejections")
