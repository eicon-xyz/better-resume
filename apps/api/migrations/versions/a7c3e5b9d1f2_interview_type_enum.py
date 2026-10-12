"""interview type enum

Revision ID: a7c3e5b9d1f2
Revises: f4d2a6b8c1e3
Create Date: 2026-10-11 11:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a7c3e5b9d1f2"
down_revision: str | None = "f4d2a6b8c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPE_CHECK = (
    "interview_type IS NULL OR interview_type IN ('auto', 'fundamentals', 'project', 'internship')"
)


def upgrade() -> None:
    # Free text never influenced generation, so every legacy value means "engine decides".
    op.execute(
        "UPDATE interview_sessions SET interview_type = 'auto' "
        "WHERE interview_type IS NOT NULL AND interview_type NOT IN "
        "('auto', 'fundamentals', 'project', 'internship')"
    )
    op.create_check_constraint(
        "ck_interview_sessions_interview_type", "interview_sessions", _TYPE_CHECK
    )


def downgrade() -> None:
    op.drop_constraint("ck_interview_sessions_interview_type", "interview_sessions", type_="check")
