"""Unify auth sessions to a single expiry timestamp.

Revision ID: 20260429_000009
Revises: 20260428_000008
Create Date: 2026-04-29 00:00:09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_000009"
down_revision = "20260428_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE auth_sessions
        SET expires_at = COALESCE(last_seen_at, created_at) + INTERVAL '6 hours'
        """
    )
    op.alter_column("auth_sessions", "expires_at", nullable=False)
    op.drop_column("auth_sessions", "idle_expires_at")
    op.drop_column("auth_sessions", "absolute_expires_at")


def downgrade() -> None:
    op.add_column("auth_sessions", sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auth_sessions", sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE auth_sessions
        SET idle_expires_at = expires_at,
            absolute_expires_at = expires_at
        """
    )
    op.alter_column("auth_sessions", "idle_expires_at", nullable=False)
    op.alter_column("auth_sessions", "absolute_expires_at", nullable=False)
    op.drop_column("auth_sessions", "expires_at")
