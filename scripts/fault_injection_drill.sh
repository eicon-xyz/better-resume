#!/usr/bin/env bash
# V6: soak the stack, then break infrastructure on purpose and record what the client saw.
#
#   bash scripts/fault_injection_drill.sh [--quick]             # 5 个故障实验 + 浸泡
#   bash scripts/fault_injection_drill.sh --sentinel [--quick]  # P5：哨兵自动 failover
#
# Preconditions: docker (reachable daemon) and uv. Exit code 2 means "cannot run"; the drill
# refuses to pretend it ran. Every experiment prints its own evidence:
#   redis-pause    : Redis frozen for 20s -> request classes + time to first success
#   redis-restart  : sessions live in Redis -> the old cookie must really stop working
#   redis-partition: api<->redis network path cut for 20s -> semantics + self-heal (P1-D)
#   redis-failover : replica promoted while the master is down -> worker must survive (P1-D)
#   worker-crash   : a consumer dies holding a job -> XPENDING+XCLAIM must reclaim it
#   soak           : sampled waves over 20 min (--quick: 2 min) -> growth of keys/connections/memory
#
# --sentinel 是 P5 的自动 failover：起 compose 的 drill profile（主 + 副本 + 3 哨兵），应用
# 显式走哨兵（BR_REDIS_SENTINELS / BR_REDIS_MASTER_NAME），只 kill 主，**不人工 promotion**。
# 收尾动作挂在 EXIT trap（= finally）：原主拉回来 + 三个哨兵 SENTINEL RESET。单机 compose 上
# 容器重建会换 IP 而哨兵记着旧地址，所以彻底干净的重跑是 down -v（用法里也写了）。
set -euo pipefail

# P45: buildx >= 0.37.2 enforces bake's entitlement consent gate even under --progress=rawjson
# (GHSA-gwr2-q96m-6682). Compose builds through `buildx bake` and only ever grants
# fs.read / security.insecure -- never `network.host`, which compose.yaml requests for the
# local WSL2 proxy -- so the build is refused before it starts ("additional privileges
# requested: pass \"--allow=network.host\""). Nightly died here twice (2026-10-09/10).
# COMPOSE_BAKE=false uses the classic path, which hands the declared entitlements straight
# to the builder. Pinned by tests/test_drill_prereqs.py. An `export` is a bash builtin, so
# --help still works without docker.
export COMPOSE_BAKE=false

# 只用 bash 内建 echo：--help 必须在 docker/uv 检查之前就能工作，连 cat 都不能依赖。
usage() {
  echo '用法:'
  echo '  bash scripts/fault_injection_drill.sh [--quick]             # 5 个故障实验 + 浸泡'
  echo '  bash scripts/fault_injection_drill.sh --sentinel [--quick]  # P5：哨兵自动 failover'
  echo ''
  echo '选项:'
  echo '  --quick      浸泡从 20 分钟缩到 2 分钟（sentinel 模式忽略它）'
  echo '  --sentinel   只跑 P5 的自动 failover：docker compose --profile drill 起主 + 副本 + 3 哨兵，'
  echo '               应用走哨兵（脚本自己 export BR_REDIS_SENTINELS / BR_REDIS_MASTER_NAME），'
  echo '               kill 主之后等哨兵自己提升，并从 kill 那一瞬量应用的首次成功'
  echo '  -h, --help   显示本帮助（不需要 docker / uv）'
  echo ''
  echo '退出码: 0 通过 / 1 实验失败 / 2 跑不起来（缺 docker 或 uv）'
  echo ''
  echo '恢复拓扑: 单机 compose 上 redis 容器重建会换 IP，而哨兵仍记着旧目标；本脚本收尾会把原主'
  echo '          拉回来并让三个哨兵 SENTINEL RESET。要彻底干净地重跑：'
  echo '              docker compose --profile drill down -v'
}

QUICK=0
MODE="full"
while [ $# -gt 0 ]; do
  case "$1" in
    --quick) QUICK=1 ;;
    --sentinel) MODE="sentinel" ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

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
if [ "$QUICK" = 1 ]; then
  SOAK_SECONDS=120
fi

POSTGRES_USER="${POSTGRES_USER:-better_resume}"
POSTGRES_DB="${POSTGRES_DB:-better_resume}"
FAILED=0
step() { printf '\n== %s\n' "$1"; }
check() { if [ "$1" -eq 0 ]; then printf 'PASS: %s\n' "$2"; else printf 'FAIL: %s\n' "$2"; FAILED=1; fi; }

# 探针统一从 apps/api 跑（uv 工程在那里）；用子 shell，避免在脚本里 cd 来 cd 去。
run_probe() { ( cd "$REPO_ROOT/apps/api" && uv run python -m scripts.fault_probe "$@" ); }

# P5：哨兵自动 failover。应用侧必须显式拿到哨兵地址与主名——compose 无法按 profile 改 env。
run_sentinel_mode() {
  export BR_REDIS_SENTINELS="redis://redis-sentinel-1:26379,redis://redis-sentinel-2:26379,redis://redis-sentinel-3:26379"
  export BR_REDIS_MASTER_NAME="${BR_REDIS_MASTER_NAME:-br-master}"
  local recovery_timeout="${SENTINEL_RECOVERY_TIMEOUT:-90}"

  # 恢复动作挂 EXIT（= finally）：不管演练在哪一步挂掉，原主都要拉回来、哨兵都要重新发现。
  restore() {
    printf '\n== 收尾：原主拉回来 + 哨兵重新发现拓扑\n'
    docker compose up -d --wait redis || true
    for index in 1 2 3; do
      docker compose exec -T "redis-sentinel-${index}" \
        redis-cli -p 26379 sentinel reset "$BR_REDIS_MASTER_NAME" >/dev/null 2>&1 || true
    done
    printf '注意：单机 compose 上 redis 容器重建会换 IP，哨兵可能仍记着旧目标。\n'
    printf '      要彻底干净地重跑：docker compose --profile drill down -v，然后再跑本命令。\n'
  }
  trap restore EXIT

  step "sentinel 模式：drill profile 起栈（主 + 副本 + 3 哨兵），应用显式走哨兵"
  printf 'BR_REDIS_SENTINELS=%s\nBR_REDIS_MASTER_NAME=%s\n' "$BR_REDIS_SENTINELS" "$BR_REDIS_MASTER_NAME"
  local up_rc=0
  docker compose --profile drill up -d --build --wait --scale api=2 || up_rc=$?
  check "$up_rc" "docker compose --profile drill up -d --build --wait --scale api=2"
  if [ "$up_rc" -ne 0 ]; then
    printf '\n栈没起来，后面的实验没有意义（收尾动作仍会执行）。\n'
    return 1
  fi

  step "fault: redis-failover --auto（kill 主 → 哨兵自己提升 → 应用自愈）"
  local probe_rc=0
  run_probe fault --base "$BASE" --scenario redis-failover --auto \
    --master-name "$BR_REDIS_MASTER_NAME" --recovery-timeout "$recovery_timeout" || probe_rc=$?
  check "$probe_rc" "自动 failover：无人干预的提升 + 从 kill 起算的恢复 + worker 存活"

  printf '\n（sentinel 模式只跑这一个实验；另外四个故障实验与浸泡在默认模式下跑。）\n'
  return "$FAILED"
}

if [ "$MODE" = "sentinel" ]; then
  run_sentinel_mode
  exit "$?"
fi

step "stack up (nginx + 2x api + worker + fake vendor)"
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
docker compose --profile smoke up -d --build --wait --scale api=2
check $? "docker compose up --wait --scale api=2"

step "fault 1/5: redis-pause (20s)"
run_probe fault --base "$BASE" --scenario redis-pause --seconds 20
check $? "redis-pause window classified and recovery measured"

step "fault 2/5: redis-restart (sessions live in Redis)"
run_probe fault --base "$BASE" --scenario redis-restart --seconds 10
check $? "redis-restart: honesty about session loss"

step "fault 3/5: redis-partition (network cut, then restored)"
run_probe fault --scenario redis-partition --seconds 20
check $? "redis network partition: no wrong answers, self-heal measured"

step "fault 4/5: redis-failover (replica promoted, worker must survive)"
run_probe fault --scenario redis-failover --seconds 20
check $? "manual failover: recovery measured, worker survived, sessions intact"

step "fault 5/5: worker-crash (claim without ack -> reclaim)"
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
