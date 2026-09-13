"""scene bindings (M5-T1)

Revision ID: 9f2c1a7b5d31
Revises: c28d77ba4f32
Create Date: 2026-09-14 05:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f2c1a7b5d31"
down_revision: str | None = "c28d77ba4f32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Default bindings keep M4 behaviour exactly: every scene runs on the local OpenAI-compatible
#: adapter until someone flips a row (that is the whole point of M5).
DEFAULT_BINDINGS = [
    ("chat", "openai_compat", "deepseek-flash"),
    ("question_extraction", "openai_compat", "deepseek-flash"),
    ("answer_evaluation", "openai_compat", "deepseek-flash"),
    ("follow_up", "openai_compat", "deepseek-flash"),
    ("report_summary", "openai_compat", "deepseek-flash"),
]


def upgrade() -> None:
    op.create_table(
        "llm_scene_bindings",
        sa.Column("scene", sa.String(length=32), nullable=False),
        sa.Column("adapter", sa.String(length=32), nullable=False),
        sa.Column("target_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("scene"),
    )
    bindings = sa.table(
        "llm_scene_bindings",
        sa.column("scene", sa.String),
        sa.column("adapter", sa.String),
        sa.column("target_ref", sa.String),
    )
    op.bulk_insert(
        bindings,
        [
            {"scene": scene, "adapter": adapter, "target_ref": target}
            for scene, adapter, target in DEFAULT_BINDINGS
        ],
    )


def downgrade() -> None:
    op.drop_table("llm_scene_bindings")
