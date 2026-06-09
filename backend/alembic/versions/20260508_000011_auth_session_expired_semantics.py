"""Unify auth session terminal state semantics around expiry.

Revision ID: 20260508_000011
Revises: 20260429_000010
Create Date: 2026-05-08 00:00:11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260508_000011"
down_revision = "20260429_000010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("auth_sessions", "revoked_at", new_column_name="expired_at")
    op.alter_column("auth_sessions", "revoked_reason_code", new_column_name="expired_reason_code")
    op.alter_column("auth_sessions", "revoke_reason", new_column_name="expired_reason")

    op.execute(
        """
        UPDATE auth_sessions
        SET state = 'expired'
        WHERE state = 'revoked'
        """
    )

    op.drop_constraint("ck_auth_sessions_state", "auth_sessions", type_="check")
    op.create_check_constraint(
        "ck_auth_sessions_state",
        "auth_sessions",
        "state IN ('active', 'expired')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_auth_sessions_state", "auth_sessions", type_="check")
    op.create_check_constraint(
        "ck_auth_sessions_state",
        "auth_sessions",
        "state IN ('active', 'revoked', 'expired')",
    )

    op.execute(
        """
        UPDATE auth_sessions
        SET state = 'revoked'
        WHERE state = 'expired' AND expired_reason_code = 'evicted_by_session_limit'
        """
    )

    op.alter_column("auth_sessions", "expired_reason", new_column_name="revoke_reason")
    op.alter_column("auth_sessions", "expired_reason_code", new_column_name="revoked_reason_code")
    op.alter_column("auth_sessions", "expired_at", new_column_name="revoked_at")
