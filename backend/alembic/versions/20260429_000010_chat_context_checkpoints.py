"""Add chat context checkpoint table.

Revision ID: 20260429_000010
Revises: 20260429_000009
Create Date: 2026-04-29 00:00:10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_000010"
down_revision = "20260429_000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_context_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("chat_history_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("covered_through_sequence", sa.Integer(), nullable=True),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('building', 'ready', 'failed')",
            name="ck_chat_context_checkpoints_status",
        ),
        sa.ForeignKeyConstraint(["chat_history_id"], ["chat_histories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_history_id", name="uq_chat_context_checkpoints_chat_history_id"),
    )
    op.create_index(
        "ix_chat_context_checkpoints_chat_history_id",
        "chat_context_checkpoints",
        ["chat_history_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_context_checkpoints_user_id",
        "chat_context_checkpoints",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_context_checkpoints_user_status",
        "chat_context_checkpoints",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_context_checkpoints_user_status", table_name="chat_context_checkpoints")
    op.drop_index("ix_chat_context_checkpoints_user_id", table_name="chat_context_checkpoints")
    op.drop_index("ix_chat_context_checkpoints_chat_history_id", table_name="chat_context_checkpoints")
    op.drop_table("chat_context_checkpoints")
