"""Add token-fenced chat operations and persisted drafts.

Revision ID: 20260623_000020
Revises: 20260622_000019
Create Date: 2026-06-23 00:00:20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260623_000020"
down_revision = "20260622_000019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_histories",
        sa.Column("lifecycle_state", sa.String(length=16), nullable=False, server_default="active"),
    )
    op.add_column("chat_histories", sa.Column("active_operation_id", sa.String(length=36), nullable=True))
    op.add_column("chat_histories", sa.Column("active_operation_token", sa.String(length=64), nullable=True))
    op.create_check_constraint(
        "ck_chat_histories_lifecycle_state",
        "chat_histories",
        "lifecycle_state IN ('active', 'deleting')",
    )
    op.create_index("ix_chat_histories_active_operation", "chat_histories", ["active_operation_id"], unique=False)
    op.alter_column("chat_histories", "lifecycle_state", server_default=None)

    op.create_table(
        "chat_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=16), nullable=False),
        sa.Column("active_operation_id", sa.String(length=36), nullable=True),
        sa.Column("active_operation_token", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lifecycle_state IN ('active', 'expired')",
            name="ck_chat_drafts_lifecycle_state",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_drafts_active_operation", "chat_drafts", ["active_operation_id"], unique=False)
    op.create_index("ix_chat_drafts_expires", "chat_drafts", ["lifecycle_state", "expires_at"], unique=False)
    op.create_index("ix_chat_drafts_expires_at", "chat_drafts", ["expires_at"], unique=False)
    op.create_index("ix_chat_drafts_user_created", "chat_drafts", ["user_id", "created_at"], unique=False)
    op.create_index("ix_chat_drafts_user_id", "chat_drafts", ["user_id"], unique=False)

    op.create_table(
        "chat_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("auth_session_id", sa.String(length=36), nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=36), nullable=False),
        sa.Column("chat_history_id", sa.String(length=36), nullable=True),
        sa.Column("draft_id", sa.String(length=36), nullable=True),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("owner_token", sa.String(length=64), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_provider_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_provider_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_max_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scope_type IN ('history', 'draft')",
            name="ck_chat_operations_scope_type",
        ),
        sa.CheckConstraint(
            "operation_type IN ('send', 'attach_file', 'delete_file', 'toggle_file', 'delete_history')",
            name="ck_chat_operations_operation_type",
        ),
        sa.CheckConstraint(
            "state IN ('validating', 'provider_streaming', 'finalizing', 'succeeded', 'failed', 'timed_out', 'cancelled')",
            name="ck_chat_operations_state",
        ),
        sa.ForeignKeyConstraint(["auth_session_id"], ["auth_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chat_history_id"], ["chat_histories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["draft_id"], ["chat_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_operations_auth_session_id", "chat_operations", ["auth_session_id"], unique=False)
    op.create_index("ix_chat_operations_deadline", "chat_operations", ["state", "deadline_at"], unique=False)
    op.create_index("ix_chat_operations_deadline_at", "chat_operations", ["deadline_at"], unique=False)
    op.create_index("ix_chat_operations_draft_created", "chat_operations", ["draft_id", "created_at"], unique=False)
    op.create_index("ix_chat_operations_draft_id", "chat_operations", ["draft_id"], unique=False)
    op.create_index("ix_chat_operations_history_created", "chat_operations", ["chat_history_id", "created_at"], unique=False)
    op.create_index("ix_chat_operations_chat_history_id", "chat_operations", ["chat_history_id"], unique=False)
    op.create_index("ix_chat_operations_scope_state", "chat_operations", ["scope_type", "scope_id", "state"], unique=False)
    op.create_index("ix_chat_operations_user_id", "chat_operations", ["user_id"], unique=False)

    op.create_table(
        "chat_draft_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("stored_file_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["chat_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", "stored_file_id", name="uq_chat_draft_files_draft_stored_file"),
    )
    op.create_index("ix_chat_draft_files_draft_created", "chat_draft_files", ["draft_id", "created_at"], unique=False)
    op.create_index("ix_chat_draft_files_draft_id", "chat_draft_files", ["draft_id"], unique=False)
    op.create_index("ix_chat_draft_files_stored_file_id", "chat_draft_files", ["stored_file_id"], unique=False)
    op.create_index("ix_chat_draft_files_user_draft", "chat_draft_files", ["user_id", "draft_id"], unique=False)
    op.create_index("ix_chat_draft_files_user_id", "chat_draft_files", ["user_id"], unique=False)

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("chat_histories")
    }
    if "ck_chat_histories_busy_reason" in constraints:
        op.drop_constraint("ck_chat_histories_busy_reason", "chat_histories", type_="check")
    if "ck_chat_histories_interaction_state" in constraints:
        op.drop_constraint("ck_chat_histories_interaction_state", "chat_histories", type_="check")
    columns = {column["name"] for column in inspector.get_columns("chat_histories")}
    if "busy_reason" in columns:
        op.drop_column("chat_histories", "busy_reason")
    if "interaction_state" in columns:
        op.drop_column("chat_histories", "interaction_state")
    if "state_updated_at" in columns:
        op.drop_column("chat_histories", "state_updated_at")


def downgrade() -> None:
    op.add_column("chat_histories", sa.Column("state_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chat_histories", sa.Column("busy_reason", sa.String(length=32), nullable=True))
    op.add_column(
        "chat_histories",
        sa.Column("interaction_state", sa.String(length=16), nullable=False, server_default="ready"),
    )
    op.execute("UPDATE chat_histories SET state_updated_at = COALESCE(updated_at, created_at)")
    op.alter_column("chat_histories", "state_updated_at", nullable=False)
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

    op.drop_index("ix_chat_draft_files_user_id", table_name="chat_draft_files")
    op.drop_index("ix_chat_draft_files_user_draft", table_name="chat_draft_files")
    op.drop_index("ix_chat_draft_files_stored_file_id", table_name="chat_draft_files")
    op.drop_index("ix_chat_draft_files_draft_id", table_name="chat_draft_files")
    op.drop_index("ix_chat_draft_files_draft_created", table_name="chat_draft_files")
    op.drop_table("chat_draft_files")

    op.drop_index("ix_chat_operations_user_id", table_name="chat_operations")
    op.drop_index("ix_chat_operations_scope_state", table_name="chat_operations")
    op.drop_index("ix_chat_operations_chat_history_id", table_name="chat_operations")
    op.drop_index("ix_chat_operations_history_created", table_name="chat_operations")
    op.drop_index("ix_chat_operations_draft_id", table_name="chat_operations")
    op.drop_index("ix_chat_operations_draft_created", table_name="chat_operations")
    op.drop_index("ix_chat_operations_deadline_at", table_name="chat_operations")
    op.drop_index("ix_chat_operations_deadline", table_name="chat_operations")
    op.drop_index("ix_chat_operations_auth_session_id", table_name="chat_operations")
    op.drop_table("chat_operations")

    op.drop_index("ix_chat_drafts_user_id", table_name="chat_drafts")
    op.drop_index("ix_chat_drafts_user_created", table_name="chat_drafts")
    op.drop_index("ix_chat_drafts_expires_at", table_name="chat_drafts")
    op.drop_index("ix_chat_drafts_expires", table_name="chat_drafts")
    op.drop_index("ix_chat_drafts_active_operation", table_name="chat_drafts")
    op.drop_table("chat_drafts")

    op.drop_index("ix_chat_histories_active_operation", table_name="chat_histories")
    op.drop_constraint("ck_chat_histories_lifecycle_state", "chat_histories", type_="check")
    op.drop_column("chat_histories", "active_operation_token")
    op.drop_column("chat_histories", "active_operation_id")
    op.drop_column("chat_histories", "lifecycle_state")
