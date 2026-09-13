"""conversations + conversation_messages (M1-T1)

Revision ID: b349260daa14
Revises: 0001_baseline
Create Date: 2026-09-13

Conversation is the single owner of session messages (§12.2). Sequence allocation is
transactional (row lock + unique index), so no Redis sequence allocator is needed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b349260daa14"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("model_ref", sa.String(length=64), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('chat', 'interview')", name="ck_conversations_kind"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_user_id_updated_at",
        "conversations",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("client_message_id", sa.String(length=64), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')", name="ck_conversation_messages_role"
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "seq", name="uq_conversation_messages_conversation_id_seq"
        ),
    )
    op.create_index(
        "ix_conversation_messages_conversation_id_seq",
        "conversation_messages",
        ["conversation_id", "seq"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_messages_meta",
        "conversation_messages",
        ["meta"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"meta": "jsonb_path_ops"},
    )
    op.create_index(
        "uq_conversation_messages_client_message_id",
        "conversation_messages",
        ["conversation_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_conversation_messages_client_message_id",
        table_name="conversation_messages",
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_conversation_messages_meta",
        table_name="conversation_messages",
        postgresql_using="gin",
        postgresql_ops={"meta": "jsonb_path_ops"},
    )
    op.drop_index(
        "ix_conversation_messages_conversation_id_seq", table_name="conversation_messages"
    )
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_user_id_updated_at", table_name="conversations")
    op.drop_table("conversations")
