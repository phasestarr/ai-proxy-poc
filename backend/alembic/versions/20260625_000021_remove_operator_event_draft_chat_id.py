"""Remove public draft chat ids from operator events.

Revision ID: 20260625_000021
Revises: 20260623_000020
Create Date: 2026-06-25 00:00:21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260625_000021"
down_revision = "20260623_000020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("operator_events")}
    if "ix_operator_events_draft_created" in indexes:
        op.drop_index("ix_operator_events_draft_created", table_name="operator_events")
    columns = {column["name"] for column in inspector.get_columns("operator_events")}
    if "draft_chat_id" in columns:
        op.drop_column("operator_events", "draft_chat_id")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("operator_events")}
    if "draft_chat_id" not in columns:
        op.add_column("operator_events", sa.Column("draft_chat_id", sa.String(length=36), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes("operator_events")}
    if "ix_operator_events_draft_created" not in indexes:
        op.create_index("ix_operator_events_draft_created", "operator_events", ["draft_chat_id", "created_at"], unique=False)
