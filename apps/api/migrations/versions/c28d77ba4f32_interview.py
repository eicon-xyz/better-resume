"""interview domain tables (M2-T2)

Revision ID: c28d77ba4f32
Revises: 745c366ba82b
Create Date: 2026-09-13 19:35:55.380353

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c28d77ba4f32"
down_revision: str | None = "745c366ba82b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("interview_type", sa.String(length=64), nullable=True),
        sa.Column("resume_path", sa.String(length=512), nullable=True),
        sa.Column("resume_sha256", sa.String(length=64), nullable=True),
        sa.Column("resume_size", sa.Integer(), nullable=True),
        sa.Column("resume_score", sa.Float(), nullable=True),
        sa.Column("question_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ("
            "'draft', 'resume_uploading', 'ready', 'in_progress', 'finished', 'abandoned'"
            ")",
            name="ck_interview_sessions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_sessions_user_id_status",
        "interview_sessions",
        ["user_id", "status"],
        unique=False,
    )
    op.create_table(
        "interview_answers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("question_no", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "missing_points",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("follow_up_needed", sa.Boolean(), nullable=True),
        sa.Column("follow_up_reason", sa.String(length=48), nullable=True),
        sa.Column("rule_version", sa.String(length=16), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "request_id", name="uq_interview_answers_session_request"
        ),
    )
    op.create_index(
        "ix_interview_answers_session_id_question_no",
        "interview_answers",
        ["session_id", "question_no"],
        unique=False,
    )
    op.create_table(
        "interview_flow_state",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_question_no", sa.String(length=16), nullable=True),
        sa.Column("total_questions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("follow_up_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_follow_up", sa.Integer(), server_default="2", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('init', 'asking', 'evaluating', 'follow_up', 'completed')",
            name="ck_interview_flow_state_status",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("question_no", sa.String(length=16), nullable=False),
        sa.Column("topic_no", sa.Integer(), nullable=False),
        sa.Column("follow_up_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "focus_points",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "question_no", name="uq_interview_questions_session_no"),
    )
    op.create_index(
        "ix_interview_questions_session_id_topic_no",
        "interview_questions",
        ["session_id", "topic_no"],
        unique=False,
    )
    op.create_table(
        "interview_reports",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column(
            "dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "payload",
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
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )


def downgrade() -> None:
    op.drop_table("interview_reports")
    op.drop_index("ix_interview_questions_session_id_topic_no", table_name="interview_questions")
    op.drop_table("interview_questions")
    op.drop_table("interview_flow_state")
    op.drop_index("ix_interview_answers_session_id_question_no", table_name="interview_answers")
    op.drop_table("interview_answers")
    op.drop_index("ix_interview_sessions_user_id_status", table_name="interview_sessions")
    op.drop_table("interview_sessions")
