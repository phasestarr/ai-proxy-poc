"""Add chat history metadata and remembered-chat placeholder schema.

Revision ID: 20260428_000008
Revises: 20260427_000007
Create Date: 2026-04-28 00:00:08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_000008"
down_revision = "20260427_000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_histories", sa.Column("pin_order", sa.Integer(), nullable=True))
    op.create_index(
        "ix_chat_histories_user_pin_order",
        "chat_histories",
        ["user_id", "pin_order"],
        unique=False,
    )

    op.create_table(
        "chat_history_memories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("chat_history_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("source_last_message_sequence", sa.Integer(), nullable=True),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="ck_chat_history_memories_status",
        ),
        sa.ForeignKeyConstraint(["chat_history_id"], ["chat_histories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_history_id", name="uq_chat_history_memories_chat_history_id"),
    )
    op.create_index(
        "ix_chat_history_memories_chat_history_id",
        "chat_history_memories",
        ["chat_history_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_history_memories_user_id",
        "chat_history_memories",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_history_memories_user_status",
        "chat_history_memories",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_history_memories_user_status", table_name="chat_history_memories")
    op.drop_index("ix_chat_history_memories_user_id", table_name="chat_history_memories")
    op.drop_index("ix_chat_history_memories_chat_history_id", table_name="chat_history_memories")
    op.drop_table("chat_history_memories")
    op.drop_index("ix_chat_histories_user_pin_order", table_name="chat_histories")
    op.drop_column("chat_histories", "pin_order")
