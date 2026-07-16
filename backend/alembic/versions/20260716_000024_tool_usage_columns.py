"""Add normalized usage columns for newly cataloged hosted tools.

Revision ID: 20260716_000024
Revises: 20260715_000023
Create Date: 2026-07-16 00:00:24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260716_000024"
down_revision = "20260715_000023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_ledger_events", sa.Column("web_fetch_requests", sa.Integer(), nullable=True))
    op.add_column("usage_ledger_events", sa.Column("code_interpreter_requests", sa.Integer(), nullable=True))
    op.add_column("usage_ledger_events", sa.Column("shell_requests", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_ledger_events", "shell_requests")
    op.drop_column("usage_ledger_events", "code_interpreter_requests")
    op.drop_column("usage_ledger_events", "web_fetch_requests")
