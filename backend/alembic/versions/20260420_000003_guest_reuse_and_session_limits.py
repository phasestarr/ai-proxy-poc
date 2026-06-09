"""Add guest reuse and session-limit metadata.

Revision ID: 20260420_000003
Revises: 20260420_000002
Create Date: 2026-04-20 00:00:03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_000003"
down_revision = "20260420_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("revoked_reason_code", sa.String(length=64), nullable=True))
    op.add_column("auth_sessions", sa.Column("superseded_by_session_id", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_auth_sessions_superseded_by_session_id",
        "auth_sessions",
        ["superseded_by_session_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_auth_sessions_superseded_by_session_id_auth_sessions",
        "auth_sessions",
        "auth_sessions",
        ["superseded_by_session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_auth_sessions_superseded_by_session_id_auth_sessions",
        "auth_sessions",
        type_="foreignkey",
    )
    op.drop_index("ix_auth_sessions_superseded_by_session_id", table_name="auth_sessions")
    op.drop_column("auth_sessions", "superseded_by_session_id")
    op.drop_column("auth_sessions", "revoked_reason_code")
