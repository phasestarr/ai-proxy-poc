"""Add chat history tables.

Revision ID: 20260420_000005
Revises: 20260420_000004
Create Date: 2026-04-20 00:00:05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_000005"
down_revision = "20260420_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_histories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_histories_user_id", "chat_histories", ["user_id"], unique=False)
    op.create_index(
        "ix_chat_histories_user_updated",
        "chat_histories",
        ["user_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chat_history_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("excluded_from_context", sa.Boolean(), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("tool_ids", sa.JSON(), nullable=False),
        sa.Column("finish_reason", sa.String(length=255), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),
        sa.CheckConstraint("status IN ('done', 'streaming', 'error')", name="ck_chat_messages_status"),
        sa.ForeignKeyConstraint(["chat_history_id"], ["chat_histories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_history_id", "sequence", name="uq_chat_messages_history_sequence"),
    )
    op.create_index("ix_chat_messages_chat_history_id", "chat_messages", ["chat_history_id"], unique=False)
    op.create_index(
        "ix_chat_messages_history_sequence",
        "chat_messages",
        ["chat_history_id", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_history_sequence", table_name="chat_messages")
    op.drop_index("ix_chat_messages_chat_history_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_histories_user_updated", table_name="chat_histories")
    op.drop_index("ix_chat_histories_user_id", table_name="chat_histories")
    op.drop_table("chat_histories")
