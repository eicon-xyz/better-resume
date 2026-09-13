#!/usr/bin/env bash
# M6-T5: start the real stack (nginx + 2x api + worker + postgres + redis) and walk the
# whole path through nginx. Every check prints PASS/FAIL; the exit code is 1 if any failed.
#
#   bash scripts/compose_smoke.sh
#
# The SSE check uses the `smoke` profile's fake vendor, so no vendor key and no vendor bill
# is involved. A real key in .env still flows into the api container for manual checks.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"

BASE="http://127.0.0.1:${NGINX_PORT:-8080}"
export NGINX_PORT="${NGINX_PORT:-8080}"
export BR_SMOKE_KEY="${BR_SMOKE_KEY:-smoke-fake-key}"
# Fast heartbeats: the SSE check wants to see the API's keep-alive frame before the fake
# vendor's first chunk arrives (it waits 2s).
export BR_SSE_HEARTBEAT_SECONDS="${BR_SSE_HEARTBEAT_SECONDS:-1}"

POSTGRES_USER="${POSTGRES_USER:-better_resume}"
POSTGRES_DB="${POSTGRES_DB:-better_resume}"
FAILED=0

step() { printf '\n== %s\n' "$1"; }
check() { # check <exit-code> <label>
  if [ "$1" -eq 0 ]; then printf 'PASS: %s\n' "$2"; else printf 'FAIL: %s\n' "$2"; FAILED=1; fi
}

step "compose config is valid"
docker compose config --quiet
check $? "docker compose config"

step "postgres + redis, then seed the smoke-fake model row"
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
check $? "smoke-fake model row"

step "build and start the stack (nginx + api + worker + fake vendor)"
docker compose --profile smoke up -d --build --wait
check $? "docker compose up --wait"

step "service status"
docker compose ps

step "SPA is served by nginx"
curl -fsS "$BASE/" | grep -q '<div id="root">'
check $? "GET / returns the built SPA"

step "api containers do not run as root"
for service in api worker; do
  uid="$(docker compose exec -T "$service" id -u | tr -d '\r')"
  [ "$uid" != "0" ] && [ -n "$uid" ]
  check $? "$service runs as uid $uid (non-root)"
done

step "REST through nginx (session cookie + model registry)"
uv run --project apps/api python apps/api/scripts/deploy_probe.py rest --base "$BASE"
check $? "REST probe"

step "SSE through nginx (heartbeat + fake vendor chunks, not buffered)"
uv run --project apps/api python apps/api/scripts/deploy_probe.py sse --base "$BASE" --model smoke-fake
check $? "SSE probe"

step "WebSocket upgrade through nginx (/api/v1/media/transcribe)"
uv run --project apps/api python apps/api/scripts/deploy_probe.py ws --base "$BASE"
check $? "WS probe"

step "two api instances: nginx must round-robin"
docker compose up -d --scale api=2 --wait --no-recreate
check $? "scale api=2"
instances="$(for _ in $(seq 1 12); do
  curl -fsS -D - -o /dev/null "$BASE/healthz" | tr -d '\r' | awk 'tolower($1) == "x-instance-id:" {print $2}'
done | sort -u)"
printf 'instances seen: %s\n' "$(echo "$instances" | tr '\n' ' ')"
[ "$(echo "$instances" | grep -c .)" -ge 2 ]
check $? "nginx reached at least two api instances"

step "worker health (Redis heartbeat) and job path"
docker compose ps worker
docker compose exec -T redis redis-cli --raw KEYS 'br:jobs:health' | grep -q br:jobs:health
check $? "worker heartbeat key exists"

printf '\n== summary\n'
if [ "$FAILED" -eq 0 ]; then
  echo "ALL CHECKS PASSED (edge: $BASE; stop with: docker compose --profile smoke down -v)"
else
  echo "SOME CHECKS FAILED (see above)"
fi
exit "$FAILED"
