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
REPO_ROOT="$PWD"

# P45: buildx >= 0.37.2 enforces bake's entitlement consent gate even under --progress=rawjson
# (GHSA-gwr2-q96m-6682). Compose builds through `buildx bake` and only ever grants
# fs.read / security.insecure -- never `network.host`, which compose.yaml requests for the
# local WSL2 proxy -- so the build is refused before it starts ("additional privileges
# requested: pass \"--allow=network.host\""). Nightly died here twice (2026-10-09/10).
# COMPOSE_BAKE=false uses the classic path, which hands the declared entitlements straight
# to the builder. Pinned by tests/test_drill_prereqs.py.
export COMPOSE_BAKE=false

if ! command -v docker >/dev/null 2>&1; then
  echo "需要 docker：本演练要起 nginx + 2x api + worker + postgres + redis（未检测到 docker 命令）" >&2
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
# The driver waits for the worker's queued summary; the fake vendor streams slowly enough
# that the api heartbeat is visible. Everything else keeps the project defaults.
export BR_SSE_HEARTBEAT_SECONDS="${BR_SSE_HEARTBEAT_SECONDS:-1}"

# P7/D19: 共享配额探针。用全新身份（新会话 → 新桶）连打同一个成本桶端点 7 次（> 2 × capacity）：
#   · 共享配额（Redis）→ 放行数 ≈ capacity（answer 2/s × burst 2 = 4），且每个响应 scope=shared；
#   · 每副本一份配额 → 放行数可到 2 × capacity，且 scope=instance、Redis 里没有 br:rl: 键。
# 这里**故意不调 rate**：探针与演练共用同一个桶，钉小 rate 会把演练自己的答题打成 429（实际踩过）。
shared_quota_probe() { # shared_quota_probe <base-url> <label> [capacity]
  local base="$1" label="$2" capacity="${3:-4}"
  local requests=7 jar user allowed=0 scopes="" status headers i=0
  jar="$(mktemp)"
  user="probe-$$-$(date +%s%N)"
  curl -sS -o /dev/null -c "$jar" -H 'content-type: application/json' \
    -d "{\"user_id\": \"$user\"}" "$base/api/v1/auth/session"
  while [ "$i" -lt "$requests" ]; do
    headers="$(curl -sS -D - -o /dev/null -b "$jar" -H 'content-type: application/json' \
      -d '{}' "$base/api/v1/interview/sessions/probe-missing/answers" | tr -d '\r')"
    status="$(printf '%s\n' "$headers" | awk 'NR==1 {print $2}')"
    scopes="$scopes$(printf '%s\n' "$headers" | awk 'tolower($1) == "x-ratelimit-scope:" {print $2; exit}') "
    if [ "$status" != "429" ]; then allowed=$((allowed + 1)); fi
    i=$((i + 1))
  done
  rm -f "$jar"
  local unique_scopes keys
  unique_scopes="$(printf '%s' "$scopes" | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ',')"
  keys="$(docker compose exec -T redis redis-cli --raw --scan --pattern 'br:rl:answer*' | tr -d '\r' | grep -c 'br:rl:' || true)"
  printf '%s: allowed=%s/%s (capacity=%s) scope=%s redis_keys=%s\n' \
    "$label" "$allowed" "$requests" "$capacity" "$unique_scopes" "$keys"
  [ "$allowed" -ge 1 ] && [ "$allowed" -le $((capacity + 1)) ] && \
    [ "$unique_scopes" = "shared," ] && [ "$keys" -ge 1 ]
}


POSTGRES_USER="${POSTGRES_USER:-better_resume}"
POSTGRES_DB="${POSTGRES_DB:-better_resume}"

echo "== stack up: postgres + redis, then the smoke-fake model row"
docker compose up -d --wait postgres redis
# P35: on a cold volume (CI) ai_models does not exist yet — seeding before the one-shot
# migrate job dies with `relation "ai_models" does not exist`. The job is idempotent, and
# the later `up` runs it again harmlessly.
docker compose run --rm --build migrate
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
uv run python -m scripts.kill_instance_drill --base "http://127.0.0.1:${NGINX_PORT}" "$@"
driver_status=$?
cd "$REPO_ROOT"

if [ "$driver_status" -ne 0 ]; then
  exit "$driver_status"
fi

# P7/D19: instance 被杀之后，幸存副本用的仍是**同一份**共享配额（不是各自为政的本地桶）。
echo "== shared rate limit still holds after the kill (one quota, not one per survivor)"
if shared_quota_probe "http://127.0.0.1:${NGINX_PORT}" "shared quota after kill"; then
  echo "PASS: survivor judged against the shared bucket"
else
  echo "FAIL: shared quota probe failed after the kill"
  exit 1
fi
