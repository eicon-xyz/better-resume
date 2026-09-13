"""ai_models registry + DeepSeek seeds (M1-T2)

Revision ID: 745c366ba82b
Revises: b349260daa14
Create Date: 2026-09-13

D12: the model registry lives in the database so switching models needs no redeploy.
Credentials are referenced by environment-variable name only — the key itself is never stored.

Seeds use the model ids actually offered by the account (deepseek-flash / deepseek-v4-pro;
both stream reasoning_content). D12's "DeepSeek-V3 / DeepSeek-R1" naming is the same intent
under the vendor's current names.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "745c366ba82b"
down_revision: str | None = "b349260daa14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYSTEM_PROMPT = "你是 better-resume 的 AI 助手。用中文回答，简洁、准确；不确定时明确说明。"


def upgrade() -> None:
    op.create_table(
        "ai_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("api_key_env", sa.String(length=64), nullable=False),
        sa.Column("max_tokens", sa.Integer(), server_default="2048", nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0.7", nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column(
            "supports_reasoning", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column(
            "extra",
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    ai_models = sa.table(
        "ai_models",
        sa.column("name", sa.String),
        sa.column("provider", sa.String),
        sa.column("base_url", sa.String),
        sa.column("model_id", sa.String),
        sa.column("api_key_env", sa.String),
        sa.column("max_tokens", sa.Integer),
        sa.column("temperature", sa.Float),
        sa.column("system_prompt", sa.Text),
        sa.column("supports_reasoning", sa.Boolean),
        sa.column("is_enabled", sa.Boolean),
        sa.column("priority", sa.Integer),
        sa.column("extra", postgresql.JSONB),
    )
    op.bulk_insert(
        ai_models,
        [
            {
                "name": "deepseek-flash",
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model_id": "deepseek-flash",
                "api_key_env": "BR_DEEPSEEK_API_KEY",
                "max_tokens": 2048,
                "temperature": 0.7,
                "system_prompt": _SYSTEM_PROMPT,
                "supports_reasoning": True,
                "is_enabled": True,
                "priority": 10,
                "extra": {"default": True},
            },
            {
                "name": "deepseek-v4-pro",
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model_id": "deepseek-v4-pro",
                "api_key_env": "BR_DEEPSEEK_API_KEY",
                "max_tokens": 4096,
                "temperature": 0.7,
                "system_prompt": _SYSTEM_PROMPT,
                "supports_reasoning": True,
                "is_enabled": True,
                "priority": 20,
                "extra": {},
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("ai_models")
