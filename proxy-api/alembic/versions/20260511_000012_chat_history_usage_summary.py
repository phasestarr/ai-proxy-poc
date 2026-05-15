"""Add chat history usage summary cache.

Revision ID: 20260511_000012
Revises: 20260508_000011
Create Date: 2026-05-11 00:00:12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_000012"
down_revision = "20260508_000011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_histories", sa.Column("usage_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_histories", "usage_summary")
