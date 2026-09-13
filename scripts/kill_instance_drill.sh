#!/usr/bin/env bash
# M6-T8: kill the api instance that is serving an interview and finish it on the survivor.
#
#   bash scripts/kill_instance_drill.sh
#
# Preconditions: docker (with a reachable daemon) and uv. Exit code 2 means "cannot run":
# the drill refuses to pretend it ran. The stack is brought up here, deliberately with two
# api replicas; every assertion lives in apps/api/scripts/kill_instance_drill.py so the
# output is the evidence.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "需要 docker：本演练要起 nginx + 2x api + worker + postgres + redis（未检测到 docker 命令）" >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "需要可用的 docker daemon（docker info 失败）" >&2
  exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "需要 uv：driver 通过 uv run --project apps/api 运行" >&2
  exit 2
fi

export NGINX_PORT="${NGINX_PORT:-8080}"
export BR_SMOKE_KEY="${BR_SMOKE_KEY:-smoke-fake-key}"
# The driver waits for the worker's queued summary; the fake vendor streams slowly enough
# that the api heartbeat is visible. Everything else keeps the project defaults.
export BR_SSE_HEARTBEAT_SECONDS="${BR_SSE_HEARTBEAT_SECONDS:-1}"

POSTGRES_USER="${POSTGRES_USER:-better_resume}"
POSTGRES_DB="${POSTGRES_DB:-better_resume}"

echo "== stack up: postgres + redis, then the smoke-fake model row"
docker compose up -d --wait postgres redis
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
INSERT INTO ai_models (name, provider, base_url, model_id, api_key_env, max_tokens,
                       temperature, is_enabled, priority, extra)
VALUES ('smoke-fake', 'openai_compat', 'http://fake-llm:8081/v1', 'smoke-fake',
        'BR_SMOKE_KEY', 512, 0.0, true, 200, '{}'::jsonb)
ON CONFLICT (name) DO UPDATE
   SET base_url = EXCLUDED.base_url, api_key_env = EXCLUDED.api_key_env,
       is_enabled = true, updated_at = now();
SQL

echo "== nginx + 2x api + worker + fake vendor (schema is migrated by the migrate job)"
docker compose --profile smoke up -d --build --wait --scale api=2
docker compose ps

echo "== interview across two instances, kill the serving one, finish on the survivor"
cd apps/api
exec uv run python -m scripts.kill_instance_drill --base "http://127.0.0.1:${NGINX_PORT}" "$@"
