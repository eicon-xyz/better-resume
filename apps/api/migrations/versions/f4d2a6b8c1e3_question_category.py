"""question category

Revision ID: f4d2a6b8c1e3
Revises: 9f2c1a7b5d31
Create Date: 2026-10-11 11:05:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4d2a6b8c1e3"
down_revision: str | None = "9f2c1a7b5d31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORY_CHECK = "category IS NULL OR category IN ('fundamentals', 'project', 'internship')"


def upgrade() -> None:
    op.add_column("interview_questions", sa.Column("category", sa.String(length=24), nullable=True))
    op.create_check_constraint(
        "ck_interview_questions_category", "interview_questions", _CATEGORY_CHECK
    )


def downgrade() -> None:
    op.drop_constraint("ck_interview_questions_category", "interview_questions", type_="check")
    op.drop_column("interview_questions", "category")
