"""Split Microsoft and guest identities.

Revision ID: 20260420_000002
Revises: 20260420_000001
Create Date: 2026-04-20 00:00:02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_000002"
down_revision = "20260420_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("auth_identities", "ms_identities")
    op.execute("ALTER INDEX ix_auth_identities_user_id RENAME TO ix_ms_identities_user_id")
    op.execute(
        "ALTER INDEX ix_auth_identities_provider_subject RENAME TO ix_ms_identities_provider_subject"
    )
    op.execute(
        "ALTER TABLE ms_identities RENAME CONSTRAINT ck_auth_identities_provider TO ck_ms_identities_provider"
    )
    op.create_unique_constraint("uq_ms_identities_user_id", "ms_identities", ["user_id"])

    op.create_table(
        "guest_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider IN ('guest')", name="ck_guest_identities_provider"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address", name="uq_guest_identities_ip_address"),
        sa.UniqueConstraint("user_id", name="uq_guest_identities_user_id"),
    )
    op.create_index("ix_guest_identities_user_id", "guest_identities", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_guest_identities_user_id", table_name="guest_identities")
    op.drop_table("guest_identities")

    op.drop_constraint("uq_ms_identities_user_id", "ms_identities", type_="unique")
    op.execute(
        "ALTER TABLE ms_identities RENAME CONSTRAINT ck_ms_identities_provider TO ck_auth_identities_provider"
    )
    op.execute(
        "ALTER INDEX ix_ms_identities_provider_subject RENAME TO ix_auth_identities_provider_subject"
    )
    op.execute("ALTER INDEX ix_ms_identities_user_id RENAME TO ix_auth_identities_user_id")
    op.rename_table("ms_identities", "auth_identities")
