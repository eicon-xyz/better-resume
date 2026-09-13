"""Scene binding table (M5): which adapter serves which business scene."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class SceneBindingRow(Base):
    """One row per scene; target_ref is a model name (openai_compat) or a flow id (xingyun)."""

    __tablename__ = "llm_scene_bindings"

    scene: Mapped[str] = mapped_column(String(32), primary_key=True)
    adapter: Mapped[str] = mapped_column(String(32), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
        onupdate=_utcnow,
    )
