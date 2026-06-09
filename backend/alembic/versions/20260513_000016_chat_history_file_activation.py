"""Add activation state to chat history files.

Revision ID: 20260513_000016
Revises: 20260512_000015
Create Date: 2026-05-13 00:00:16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_000016"
down_revision = "20260512_000015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_history_files",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("chat_history_files", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_column("chat_history_files", "is_active")
