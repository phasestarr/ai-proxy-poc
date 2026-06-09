"""Add chat attachment storage tables.

Revision ID: 20260512_000014
Revises: 20260511_000013
Create Date: 2026-05-12 00:00:14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260512_000014"
down_revision = "20260511_000013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sha256", name="uq_stored_files_user_sha256"),
    )
    op.create_index("ix_stored_files_user_created", "stored_files", ["user_id", "created_at"], unique=False)
    op.create_index("ix_stored_files_user_id", "stored_files", ["user_id"], unique=False)

    op.create_table(
        "stored_file_provider_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("stored_file_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("token_count_status", sa.String(length=16), nullable=False),
        sa.Column("token_count_error", sa.Text(), nullable=True),
        sa.Column("provider_file_id", sa.String(length=255), nullable=True),
        sa.Column("remote_file_status", sa.String(length=16), nullable=False),
        sa.Column("remote_file_error", sa.Text(), nullable=True),
        sa.Column("count_model_id", sa.String(length=255), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'vertex_ai')",
            name="ck_stored_file_provider_states_provider",
        ),
        sa.CheckConstraint(
            "token_count_status IN ('ready', 'failed', 'unsupported')",
            name="ck_stored_file_provider_states_token_count_status",
        ),
        sa.CheckConstraint(
            "remote_file_status IN ('not_uploaded', 'ready', 'failed', 'unsupported')",
            name="ck_stored_file_provider_states_remote_file_status",
        ),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stored_file_id",
            "provider",
            name="uq_stored_file_provider_states_file_provider",
        ),
    )
    op.create_index(
        "ix_stored_file_provider_states_provider_status",
        "stored_file_provider_states",
        ["provider", "remote_file_status"],
        unique=False,
    )
    op.create_index(
        "ix_stored_file_provider_states_stored_file_id",
        "stored_file_provider_states",
        ["stored_file_id"],
        unique=False,
    )

    op.create_table(
        "chat_history_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("chat_history_id", sa.String(length=36), nullable=False),
        sa.Column("stored_file_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_history_id"], ["chat_histories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_history_files_history_created",
        "chat_history_files",
        ["chat_history_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_history_files_user_history",
        "chat_history_files",
        ["user_id", "chat_history_id"],
        unique=False,
    )
    op.create_index("ix_chat_history_files_chat_history_id", "chat_history_files", ["chat_history_id"], unique=False)
    op.create_index("ix_chat_history_files_stored_file_id", "chat_history_files", ["stored_file_id"], unique=False)
    op.create_index("ix_chat_history_files_user_id", "chat_history_files", ["user_id"], unique=False)

    op.create_table(
        "chat_message_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chat_message_id", sa.String(length=36), nullable=False),
        sa.Column("attachment_index", sa.Integer(), nullable=False),
        sa.Column("chat_history_file_id", sa.String(length=36), nullable=True),
        sa.Column("stored_file_id", sa.String(length=36), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_file_id", sa.String(length=255), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'vertex_ai')",
            name="ck_chat_message_attachments_provider",
        ),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chat_message_id",
            "attachment_index",
            name="uq_chat_message_attachments_message_index",
        ),
    )
    op.create_index(
        "ix_chat_message_attachments_message_index",
        "chat_message_attachments",
        ["chat_message_id", "attachment_index"],
        unique=False,
    )
    op.create_index(
        "ix_chat_message_attachments_chat_message_id",
        "chat_message_attachments",
        ["chat_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_message_attachments_chat_message_id", table_name="chat_message_attachments")
    op.drop_index("ix_chat_message_attachments_message_index", table_name="chat_message_attachments")
    op.drop_table("chat_message_attachments")

    op.drop_index("ix_chat_history_files_user_id", table_name="chat_history_files")
    op.drop_index("ix_chat_history_files_stored_file_id", table_name="chat_history_files")
    op.drop_index("ix_chat_history_files_chat_history_id", table_name="chat_history_files")
    op.drop_index("ix_chat_history_files_user_history", table_name="chat_history_files")
    op.drop_index("ix_chat_history_files_history_created", table_name="chat_history_files")
    op.drop_table("chat_history_files")

    op.drop_index(
        "ix_stored_file_provider_states_stored_file_id",
        table_name="stored_file_provider_states",
    )
    op.drop_index(
        "ix_stored_file_provider_states_provider_status",
        table_name="stored_file_provider_states",
    )
    op.drop_table("stored_file_provider_states")

    op.drop_index("ix_stored_files_user_id", table_name="stored_files")
    op.drop_index("ix_stored_files_user_created", table_name="stored_files")
    op.drop_table("stored_files")
