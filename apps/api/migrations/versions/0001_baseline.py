"""baseline: revision chain anchor, no tables yet

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-13

M0 keeps session state in Redis and ships no ORM models, so this migration only anchors
the chain. First real tables arrive with M1/M2.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Intentionally empty: M0 has no tables."""


def downgrade() -> None:
    """Intentionally empty: M0 has no tables."""
