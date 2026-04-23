"""Initial PostgreSQL schema.

Revision ID: 20260420_000001
Revises:
Create Date: 2026-04-20 00:00:01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=255), nullable=False),
        sa.Column("nonce", sa.String(length=255), nullable=False),
        sa.Column("pkce_verifier_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("return_to", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requester_ip", sa.String(length=64), nullable=True),
        sa.Column("requester_user_agent", sa.Text(), nullable=True),
        sa.CheckConstraint("provider IN ('microsoft')", name="ck_oauth_transactions_provider"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oauth_transactions_state",
        "oauth_transactions",
        ["state"],
        unique=True,
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("account_type IN ('guest', 'human')", name="ck_users_account_type"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "auth_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("home_account_id", sa.String(length=255), nullable=True),
        sa.Column("preferred_username", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider IN ('microsoft')", name="ck_auth_identities_provider"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"], unique=False)
    op.create_index(
        "ix_auth_identities_provider_subject",
        "auth_identities",
        ["provider", "tenant_id", "subject"],
        unique=True,
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_key_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("auth_type", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("persistent", sa.Boolean(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=255), nullable=True),
        sa.Column("created_ip", sa.String(length=64), nullable=True),
        sa.Column("created_user_agent", sa.Text(), nullable=True),
        sa.Column("last_ip", sa.String(length=64), nullable=True),
        sa.Column("last_user_agent", sa.Text(), nullable=True),
        sa.CheckConstraint("auth_type IN ('guest', 'microsoft')", name="ck_auth_sessions_auth_type"),
        sa.CheckConstraint("state IN ('active', 'revoked', 'expired')", name="ck_auth_sessions_state"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_index("ix_auth_sessions_user_state", "auth_sessions", ["user_id", "state"], unique=False)
    op.create_index(
        "ix_auth_sessions_session_key_hash",
        "auth_sessions",
        ["session_key_hash"],
        unique=True,
    )

    op.create_table(
        "auth_provider_sessions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("token_cache_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("token_cache_version", sa.Integer(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("home_account_id", sa.String(length=255), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refresh_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider IN ('microsoft')", name="ck_auth_provider_sessions_provider"),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )


def downgrade() -> None:
    op.drop_table("auth_provider_sessions")
    op.drop_index("ix_auth_sessions_session_key_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_state", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_auth_identities_provider_subject", table_name="auth_identities")
    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_table("auth_identities")
    op.drop_table("users")
    op.drop_index("ix_oauth_transactions_state", table_name="oauth_transactions")
    op.drop_table("oauth_transactions")
