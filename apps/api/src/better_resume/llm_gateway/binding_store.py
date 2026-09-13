"""Scene binding persistence + validation (no credentials in here, ever)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .binding_orm import SceneBindingRow
from .scenes import AdapterKind, LlmScene


class SceneBindingError(ValueError):
    """A binding that cannot be honoured (unknown adapter, empty target, ...)."""


@dataclass(frozen=True, slots=True)
class SceneBinding:
    scene: LlmScene
    adapter: AdapterKind
    target_ref: str


def validate_binding(
    scene: LlmScene | str, adapter: AdapterKind | str, target_ref: str
) -> SceneBinding:
    try:
        resolved_scene = LlmScene(str(scene))
    except ValueError as exc:
        raise SceneBindingError(f"unknown scene: {scene}") from exc
    try:
        resolved_adapter = AdapterKind(str(adapter))
    except ValueError as exc:
        raise SceneBindingError(
            f"unknown adapter {adapter!r}; expected one of {[kind.value for kind in AdapterKind]}"
        ) from exc
    if not target_ref or not target_ref.strip():
        raise SceneBindingError(f"scene {resolved_scene.value} needs a target_ref")
    return SceneBinding(
        scene=resolved_scene, adapter=resolved_adapter, target_ref=target_ref.strip()
    )


class SceneBindingStore:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_all(self) -> dict[LlmScene, SceneBinding]:
        rows = (await self._db.execute(select(SceneBindingRow))).scalars().all()
        bindings: dict[LlmScene, SceneBinding] = {}
        for row in rows:
            try:
                bindings[LlmScene(row.scene)] = validate_binding(
                    row.scene, row.adapter, row.target_ref
                )
            except SceneBindingError:  # a bad row must not take the whole listing down
                continue
        return bindings

    async def get(self, scene: LlmScene) -> SceneBinding | None:
        row = await self._db.get(SceneBindingRow, scene.value)
        if row is None:
            return None
        return validate_binding(row.scene, row.adapter, row.target_ref)

    async def upsert(self, scene: LlmScene, adapter: AdapterKind, target_ref: str) -> SceneBinding:
        binding = validate_binding(scene, adapter, target_ref)
        statement = (
            pg_insert(SceneBindingRow)
            .values(
                scene=binding.scene.value,
                adapter=binding.adapter.value,
                target_ref=binding.target_ref,
            )
            .on_conflict_do_update(
                index_elements=[SceneBindingRow.scene],
                set_={
                    "adapter": binding.adapter.value,
                    "target_ref": binding.target_ref,
                    "updated_at": datetime.now(UTC),
                },
            )
        )
        await self._db.execute(statement)
        return binding
