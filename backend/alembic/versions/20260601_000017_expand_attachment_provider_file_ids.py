"""Expand attachment provider file identifiers.

Revision ID: 20260601_000017
Revises: 20260513_000016
Create Date: 2026-06-01 00:00:17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260601_000017"
down_revision = "20260513_000016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "stored_file_provider_states",
        "provider_file_id",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "chat_message_attachments",
        "provider_file_id",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "chat_message_attachments",
        "provider_file_id",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "stored_file_provider_states",
        "provider_file_id",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
