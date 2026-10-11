"""generation notices

Revision ID: b8e1f4c2d9a3
Revises: a7c3e5b9d1f2
Create Date: 2026-10-11 11:40:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8e1f4c2d9a3"
down_revision: str | None = "a7c3e5b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column(
            "resume_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "interview_sessions",
        sa.Column(
            "degraded_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "degraded_reasons")
    op.drop_column("interview_sessions", "resume_warnings")
