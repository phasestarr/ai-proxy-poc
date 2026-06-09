"""Add chat interaction state and same-history file dedupe.

Revision ID: 20260512_000015
Revises: 20260512_000014
Create Date: 2026-05-12 00:00:15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260512_000015"
down_revision = "20260512_000014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_histories",
        sa.Column(
            "interaction_state",
            sa.String(length=16),
            nullable=False,
            server_default="ready",
        ),
    )
    op.add_column(
        "chat_histories",
        sa.Column("busy_reason", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "chat_histories",
        sa.Column(
            "state_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_check_constraint(
        "ck_chat_histories_interaction_state",
        "chat_histories",
        "interaction_state IN ('ready', 'validating', 'waiting')",
    )
    op.create_check_constraint(
        "ck_chat_histories_busy_reason",
        "chat_histories",
        "busy_reason IS NULL OR busy_reason IN ('send', 'attach_file', 'delete_file', 'delete_history')",
    )
    op.alter_column("chat_histories", "interaction_state", server_default=None)
    op.alter_column("chat_histories", "state_updated_at", server_default=None)

    op.execute(
        """
        DELETE FROM chat_history_files AS target
        USING (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY chat_history_id, stored_file_id
                        ORDER BY created_at ASC, id ASC
                    ) AS row_number
                FROM chat_history_files
            ) AS ranked
            WHERE ranked.row_number > 1
        ) AS duplicates
        WHERE target.id = duplicates.id
        """
    )
    op.create_unique_constraint(
        "uq_chat_history_files_history_stored_file",
        "chat_history_files",
        ["chat_history_id", "stored_file_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_chat_history_files_history_stored_file",
        "chat_history_files",
        type_="unique",
    )

    op.drop_constraint("ck_chat_histories_busy_reason", "chat_histories", type_="check")
    op.drop_constraint("ck_chat_histories_interaction_state", "chat_histories", type_="check")
    op.drop_column("chat_histories", "state_updated_at")
    op.drop_column("chat_histories", "busy_reason")
    op.drop_column("chat_histories", "interaction_state")

