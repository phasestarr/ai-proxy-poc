"""Add persisted chat message blocks.

Revision ID: 20260715_000023
Revises: 20260708_000022
Create Date: 2026-07-15 00:00:23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260715_000023"
down_revision = "20260708_000022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_message_blocks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chat_message_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("provider_block_id", sa.String(length=512), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("raw_events", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type IN ('thinking', 'tool')", name="ck_chat_message_blocks_type"),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_message_id", "sequence", name="uq_chat_message_blocks_message_sequence"),
        sa.UniqueConstraint(
            "chat_message_id",
            "type",
            "provider_block_id",
            name="uq_chat_message_blocks_message_provider_block",
        ),
    )
    op.create_index(
        "ix_chat_message_blocks_chat_message_id",
        "chat_message_blocks",
        ["chat_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_message_blocks_message_sequence",
        "chat_message_blocks",
        ["chat_message_id", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_message_blocks_message_sequence", table_name="chat_message_blocks")
    op.drop_index("ix_chat_message_blocks_chat_message_id", table_name="chat_message_blocks")
    op.drop_table("chat_message_blocks")
