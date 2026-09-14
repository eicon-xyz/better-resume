#!/usr/bin/env bash
# V6: soak the stack, then break infrastructure on purpose and record what the client saw.
#
#   bash scripts/fault_injection_drill.sh [--quick]
#
# Preconditions: docker (reachable daemon) and uv. Exit code 2 means "cannot run"; the drill
# refuses to pretend it ran. Every experiment prints its own evidence:
#   redis-pause    : Redis frozen for 20s -> request classes + time to first success
#   redis-restart  : sessions live in Redis -> the old cookie must really stop working
#   worker-crash   : a consumer dies holding a job -> XPENDING+XCLAIM must reclaim it
#   soak           : sampled waves over 20 min (--quick: 2 min) -> growth of keys/connections/memory
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "需要 docker：本演练要起栈、暂停/重启 Redis、kill worker" >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "需要可用的 docker daemon（docker info 失败）" >&2
  exit 2
fi

# uv is often installed into ~/.local/bin, which a fresh root shell does not have on PATH.
find_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  for candidate in "$HOME/.local/bin/uv" /root/.local/bin/uv /usr/local/bin/uv; do
    if [ -x "$candidate" ]; then
      export PATH="$(dirname "$candidate"):$PATH"
      echo "note: uv 不在 PATH，已临时使用 $candidate"
      return 0
    fi
  done
  return 1
}

if ! find_uv; then
  echo "需要 uv：请先 export PATH=\"$HOME/.local/bin:$PATH\"（或安装 uv 后重试）" >&2
  exit 2
fi

export NGINX_PORT="${NGINX_PORT:-8080}"
export BR_SMOKE_KEY="${BR_SMOKE_KEY:-smoke-fake-key}"
BASE="http://127.0.0.1:${NGINX_PORT}"
SOAK_SECONDS=1200
if [ "${1:-}" = "--quick" ]; then
  SOAK_SECONDS=120
fi

POSTGRES_USER="${POSTGRES_USER:-better_resume}"
POSTGRES_DB="${POSTGRES_DB:-better_resume}"
FAILED=0
step() { printf '\n== %s\n' "$1"; }
check() { if [ "$1" -eq 0 ]; then printf 'PASS: %s\n' "$2"; else printf 'FAIL: %s\n' "$2"; FAILED=1; fi; }

step "stack up (nginx + 2x api + worker + fake vendor)"
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
docker compose --profile smoke up -d --build --wait --scale api=2
check $? "docker compose up --wait --scale api=2"

cd apps/api
run_probe() { uv run python -m scripts.fault_probe "$@"; }

step "fault 1/3: redis-pause (20s)"
run_probe fault --base "$BASE" --scenario redis-pause --seconds 20
check $? "redis-pause window classified and recovery measured"

step "fault 2/3: redis-restart (sessions live in Redis)"
run_probe fault --base "$BASE" --scenario redis-restart --seconds 10
check $? "redis-restart: honesty about session loss"

step "fault 3/3: worker-crash (claim without ack -> reclaim)"
run_probe fault --base "$BASE" --scenario worker-crash --model smoke-fake --summary-timeout 180
check $? "crashed consumer's job reclaimed and finished"

step "soak (${SOAK_SECONDS}s, sampled waves)"
run_probe soak --base "$BASE" --duration "$SOAK_SECONDS" --wave-seconds 30 --requests 30 \
  --concurrency 4 --json /tmp/v6-soak.json
check $? "soak error rate stayed under 1%"

printf '\n== summary\n'
if [ "$FAILED" -eq 0 ]; then
  echo "ALL FAULT EXPERIMENTS PASSED (json: /tmp/v6-soak.json)"
else
  echo "SOME EXPERIMENTS FAILED (see above)"
fi
exit "$FAILED"
