"""Add auth conflict tickets.

Revision ID: 20260420_000004
Revises: 20260420_000003
Create Date: 2026-04-20 00:00:04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_000004"
down_revision = "20260420_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_conflict_tickets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("auth_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("payload_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("return_to", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requester_ip", sa.String(length=64), nullable=True),
        sa.Column("requester_user_agent", sa.Text(), nullable=True),
        sa.CheckConstraint("auth_type IN ('guest', 'microsoft')", name="ck_auth_conflict_tickets_auth_type"),
        sa.CheckConstraint("reason IN ('session_limit_reached')", name="ck_auth_conflict_tickets_reason"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_conflict_tickets_ticket_hash",
        "auth_conflict_tickets",
        ["ticket_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_conflict_tickets_user_auth_type",
        "auth_conflict_tickets",
        ["user_id", "auth_type"],
        unique=False,
    )
    op.create_index(
        "ix_auth_conflict_tickets_user_id",
        "auth_conflict_tickets",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_auth_conflict_tickets_user_id", table_name="auth_conflict_tickets")
    op.drop_index("ix_auth_conflict_tickets_user_auth_type", table_name="auth_conflict_tickets")
    op.drop_index("ix_auth_conflict_tickets_ticket_hash", table_name="auth_conflict_tickets")
    op.drop_table("auth_conflict_tickets")
