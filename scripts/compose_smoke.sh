#!/usr/bin/env bash
# Start the real stack (nginx + 2x api + worker + postgres + redis) and walk the
# whole path through nginx. Every check prints PASS/FAIL; the exit code is 1 if any failed.
#
#   bash scripts/compose_smoke.sh
#
# The SSE check uses the `smoke` profile's fake vendor, so no vendor key and no vendor bill
# is involved. A real key in .env still flows into the api container for manual checks.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"

# P45/P15-8: buildx >= 0.37.2 enforces bake's entitlement consent gate even under
# --progress=rawjson (GHSA-gwr2-q96m-6682). compose.yaml asks for `network: host` (local WSL2
# proxy), and compose never grants it, so every build is refused before it starts
# ("additional privileges requested: pass \"--allow=network.host\""). compose v5.6.0 also
# dropped COMPOSE_BAKE, so the classic-path opt-out below is inert here; it stays pinned by
# tests/test_drill_prereqs.py for older compose releases. Builds therefore go straight to
# `buildx bake` with the grant stated explicitly (see the build step).
export COMPOSE_BAKE=false

# P35 follow-up: refuse loudly instead of dying inside `docker compose config` with 127.
# The other two drills already guard this way; this one was the odd one out.
if ! command -v docker >/dev/null 2>&1; then
  echo "需要 docker：本冒烟要起 nginx + api + worker + postgres + redis（未检测到 docker 命令）" >&2
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

# ---- 部署面隐式默认值的消费面（p15 建议 4 / P02） ----
# 期望值（缓存头、迁移标记、禁止 uid、实例数、WS 超时）只在 scripts/deploy_defaults.sh 声明一处；
# 这里按 id 读声明，再真跑该形态。声明缺字段 = 这条默认值没有断言 → 该条检查判红，不静默放行。
source "$REPO_ROOT/scripts/deploy_defaults.sh"

default_value() { # default_value <id> <field>: 读声明的期望值，读不到就把该条判红
  local id="$1" field="$2" record surface anchor args pair
  record="${BR_DEPLOY_DEFAULTS[$id]:-}"
  if [ -z "$record" ]; then
    printf '声明里没有默认值 %s（scripts/deploy_defaults.sh）\n' "$id" >&2
    return 1
  fi
  IFS='|' read -r surface anchor args <<<"$record"
  case "$field" in
    surface) [ -n "$surface" ] && printf '%s' "$surface" && return 0 ;;
    anchor) [ -n "$anchor" ] && printf '%s' "$anchor" && return 0 ;;
  esac
  local IFS=';'
  for pair in $args; do
    if [ "${pair%%=*}" = "$field" ] && [ -n "${pair#*=}" ]; then
      printf '%s' "${pair#*=}"
      return 0
    fi
  done
  printf '默认值 %s 的声明里缺少 %s\n' "$id" "$field" >&2
  return 1
}

default_declared_in() { # default_declared_in <id>: 声明位必须逐字留在它描述的文件里
  local id="$1" surface anchor
  surface="$(default_value "$id" surface)" || return 1
  anchor="$(default_value "$id" anchor)" || return 1
  printf '  声明位 %s: %s\n' "$surface" "$anchor"
  grep -qF -- "$anchor" "$surface"
}

judge() { # judge <label> <声明消费的判定...>: 红也继续跑完，FAIL 与摘要都要打出来
  local label="$1"; shift
  if "$@"; then check 0 "$label"; else check 1 "$label"; fi
}

default_cache_headers() { # spa-cache-headers: SPA 与 hashed asset 的响应头 == 声明值
  local path header asset_header control asset asset_control
  default_declared_in spa-cache-headers || return 1
  path="$(default_value spa-cache-headers index_path)" || return 1
  header="$(default_value spa-cache-headers index_header)" || return 1
  asset_header="$(default_value spa-cache-headers asset_header)" || return 1
  control="$(curl -fsSI "$BASE$path" | tr -d '\r' | grep -i '^cache-control:' || true)"
  printf '  GET %s -> %s（声明 %s）\n' "$path" "${control:-<无 Cache-Control>}" "$header"
  grep -qi -- "$header" <<<"$control" || return 1
  asset="$(curl -fsS "$BASE$path" | grep -oE 'assets/[A-Za-z0-9._-]+\.js' | head -1 || true)"
  if [ -z "$asset" ]; then
    printf '  %s 里找不到 hashed asset，/assets/ 的头无法判定\n' "$path"
    return 1
  fi
  asset_control="$(curl -fsSI "$BASE/$asset" | tr -d '\r' | grep -i '^cache-control:' || true)"
  printf '  GET %s -> %s（声明 %s）\n' "$asset" "${asset_control:-<无 Cache-Control>}" "$asset_header"
  grep -qi -- "$asset_header" <<<"$asset_control"
}

default_migrate_step() { # one-shot-migrate: 一次性迁移作业真跑一次，schema 必须停在 head
  local service exec_cmd marker output
  default_declared_in one-shot-migrate || return 1
  service="$(default_value one-shot-migrate service)" || return 1
  exec_cmd="$(default_value one-shot-migrate exec)" || return 1
  marker="$(default_value one-shot-migrate marker)" || return 1
  # exec 是「alembic current」这样的两段命令，按空格分词（值来自声明，不是外部输入）。
  output="$(docker compose run --rm -T "$service" $exec_cmd 2>&1 || true)"
  printf '%s\n' "$output" | sed 's/^/  /'
  grep -qF -- "$marker" <<<"$output"
}

default_non_root() { # containers-non-root: 容器里的 uid 不许是声明里的那个
  local services forbidden svc uid blocked=0
  default_declared_in containers-non-root || return 1
  services="$(default_value containers-non-root services)" || return 1
  forbidden="$(default_value containers-non-root forbidden_uid)" || return 1
  local IFS=','
  for svc in $services; do
    uid="$(docker compose exec -T "$svc" id -u 2>/dev/null | tr -d '\r' || true)"
    printf '  %s uid=%s（禁止 %s）\n' "$svc" "${uid:-<读不到>}" "$forbidden"
    [ -n "$uid" ] && [ "$uid" != "$forbidden" ] || blocked=1
  done
  return "$blocked"
}

default_upstream_resolution() { # dynamic-upstream: 扩容后 nginx 必须看见 >= 声明的副本数
  local samples min_instances header instances seen
  default_declared_in dynamic-upstream || return 1
  samples="$(default_value dynamic-upstream samples)" || return 1
  min_instances="$(default_value dynamic-upstream min_instances)" || return 1
  header="$(default_value dynamic-upstream instance_header)" || return 1
  docker compose up -d --scale api=2 --wait --no-recreate || return 1
  instances="$(for _ in $(seq 1 "$samples"); do
    curl -fsS -D - -o /dev/null "$BASE/healthz" | tr -d '\r' | awk -v want="$header:" 'tolower($1) == want {print $2}'
  done | sort -u || true)"
  seen="$(printf '%s\n' "$instances" | grep -c . || true)"
  printf '  采样 %s 次，X-Instance-Id 命中 %s 个（声明 >= %s）: %s\n' \
    "$samples" "$seen" "$min_instances" "$(printf '%s' "$instances" | tr '\n' ' ')"
  [ "$seen" -ge "$min_instances" ]
}

default_ws_timeout() { # ws-idle-timeout: 运行中的 nginx 必须带着声明里的读超时
  local directive seconds effective
  default_declared_in ws-idle-timeout || return 1
  directive="$(default_value ws-idle-timeout directive)" || return 1
  seconds="$(default_value ws-idle-timeout seconds)" || return 1
  effective="$(docker compose exec -T nginx nginx -T 2>&1 | grep -F -- "$directive" | tr -d '\r' || true)"
  printf '  运行中的 nginx: %s\n' "${effective:-<配置里没有 $directive>}"
  grep -qF -- "$directive $seconds" <<<"$effective"
}

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


step "compose config is valid"
docker compose config --quiet
check $? "docker compose config"

step "build the stack images (bake with an explicit network.host grant)"
docker compose --profile smoke build --print | docker buildx bake --allow=network.host -f -

step "postgres + redis, then seed the smoke-fake model row"
docker compose up -d --wait postgres redis
# P35: on a cold volume (CI) ai_models does not exist yet — seeding before the one-shot
# migrate job dies with `relation "ai_models" does not exist`. The job is idempotent, and
# the later `up` runs it again harmlessly.
docker compose run --rm migrate
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

step "start the stack (nginx + api + worker + fake vendor; images built above)"
docker compose --profile smoke up -d --wait
check $? "docker compose up --wait"

step "declared default: one-shot-migrate"
judge "the one-shot migrate job leaves the schema at head" default_migrate_step

step "service status"
docker compose ps

step "SPA is served by nginx"
curl -fsS "$BASE/" | grep -q '<div id="root">'
check $? "GET / returns the built SPA"
# P29: index.html without cache policy = browsers run the PREVIOUS bundle after a deploy.
step "declared default: spa-cache-headers"
judge "SPA and hashed assets carry the declared Cache-Control" default_cache_headers

step "declared default: containers-non-root"
judge "api/worker run as the declared non-root uid" default_non_root

step "REST through nginx (session cookie + model registry)"
uv run --project apps/api python apps/api/scripts/deploy_probe.py rest --base "$BASE"
check $? "REST probe"

step "SSE through nginx (heartbeat + fake vendor chunks, not buffered)"
uv run --project apps/api python apps/api/scripts/deploy_probe.py sse --base "$BASE" --model smoke-fake
check $? "SSE probe"

step "WebSocket upgrade through nginx (/api/v1/media/transcribe)"
uv run --project apps/api python apps/api/scripts/deploy_probe.py ws --base "$BASE"
check $? "WS probe"

step "declared default: ws-idle-timeout"
judge "the running nginx carries the declared read timeout" default_ws_timeout

step "declared default: dynamic-upstream"
judge "nginx reached at least the declared number of api instances" default_upstream_resolution

step "worker health (Redis heartbeat) and job path"
docker compose ps worker
docker compose exec -T redis redis-cli --raw KEYS 'br:jobs:health' | grep -q br:jobs:health
check $? "worker heartbeat key exists"

step "shared rate limit: two replicas, one quota (D19)"
shared_quota_probe "$BASE" "shared quota"
check $? "a fresh identity's 7 requests release ~capacity (not 2x) with X-RateLimit-Scope: shared"

printf '\n== summary\n'
if [ "$FAILED" -eq 0 ]; then
  echo "ALL CHECKS PASSED (edge: $BASE; stop with: docker compose --profile smoke down -v)"
else
  echo "SOME CHECKS FAILED (see above)"
fi
exit "$FAILED"
