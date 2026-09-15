#!/usr/bin/env bash
# P2-T1: the single entry point for every verification layer.
#
# CI and local MUST call this script instead of re-typing commands (M6 P16: "local green,
# CI red" happened because the two drifted). Evidence lands in var/evidence/<utc>-<layer>/.
#
# Usage:
#   scripts/verify.sh --list
#   scripts/verify.sh --layer unit|contract|deploy|fault|soak|real|scripts|all \
#     [--scope api|web|all] [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

LAYER=""
SCOPE="all"
DRY_RUN=0
LIST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list)
      LIST=1
      shift
      ;;
    --layer)
      [[ $# -ge 2 ]] || { echo "missing value for --layer" >&2; exit 2; }
      LAYER="$2"
      shift 2
      ;;
    --scope)
      [[ $# -ge 2 ]] || { echo "missing value for --scope" >&2; exit 2; }
      SCOPE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      echo "unknown argument: $1 (see --list)" >&2
      exit 2
      ;;
  esac
done

if [[ $LIST -eq 1 ]]; then
  cat <<'MAP'
unit:
  api: cd apps/api && uv run pytest
  web: pnpm -C apps/web exec vitest run
contract:
  api: cd apps/api && uv run ruff check .
  api: cd apps/api && uv run ruff format --check .
  api: cd apps/api && uv run alembic upgrade head
  api: cd apps/api && uv run alembic check
  api: cd apps/api && uv run python scripts/export_openapi.py --check
  api: cd apps/api && uv run python scripts/extract_api_index.py --check
  web: pnpm -C apps/web lint
  web: pnpm -C apps/web typecheck
  web: pnpm -C apps/web check:api
deploy:
  all: bash scripts/compose_smoke.sh
  all: bash scripts/kill_instance_drill.sh
fault:
  all: bash scripts/fault_injection_drill.sh
soak:
  all: cd apps/api && uv run python -m scripts.fault_probe soak --duration 3600 --wave-seconds 30 --requests 30 --concurrency 4 --json var/evidence/soak-60m.json
real:
  all: (T4) budget-guarded real-machine suite; refuses until implemented
scripts:
  api: cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py
all:
  = unit + contract + scripts
MAP
  exit 0
fi

case "$LAYER" in
  unit|contract|deploy|fault|soak|real|scripts|all) ;;
  "") echo "no --layer given; usage: verify.sh --layer unit|contract|deploy|fault|soak|real|scripts|all" >&2; exit 2 ;;
  *) echo "unknown layer: $LAYER (see --list)" >&2; exit 2 ;;
esac

case "$SCOPE" in
  api|web|all) ;;
  *) echo "unknown scope: $SCOPE (api|web|all)" >&2; exit 2 ;;
esac

declare -a cmds=()

add_api_unit() { cmds+=("cd apps/api && uv run pytest"); }
add_web_unit() { cmds+=("pnpm -C apps/web exec vitest run"); }

case "$LAYER" in
  unit)
    if [[ "$SCOPE" != "web" ]]; then add_api_unit; fi
    if [[ "$SCOPE" != "api" ]]; then add_web_unit; fi
    ;;
  contract)
    if [[ "$SCOPE" != "web" ]]; then
      cmds+=("cd apps/api && uv run ruff check .")
      cmds+=("cd apps/api && uv run ruff format --check .")
      cmds+=("cd apps/api && uv run alembic upgrade head")
      cmds+=("cd apps/api && uv run alembic check")
      cmds+=("cd apps/api && uv run python scripts/export_openapi.py --check")
      cmds+=("cd apps/api && uv run python scripts/extract_api_index.py --check")
    fi
    if [[ "$SCOPE" != "api" ]]; then
      cmds+=("pnpm -C apps/web lint")
      cmds+=("pnpm -C apps/web typecheck")
      cmds+=("pnpm -C apps/web check:api")
    fi
    ;;
  deploy)
    cmds+=("bash scripts/compose_smoke.sh")
    cmds+=("bash scripts/kill_instance_drill.sh")
    ;;
  fault)
    cmds+=("bash scripts/fault_injection_drill.sh")
    ;;
  soak)
    cmds+=("cd apps/api && uv run python -m scripts.fault_probe soak --base http://127.0.0.1:8080 --duration 3600 --wave-seconds 30 --requests 30 --concurrency 4 --json var/evidence/soak-60m.json")
    ;;
  real)
    echo "real layer is not implemented yet (T4: budget-guarded real-machine suite)" >&2
    exit 2
    ;;
  scripts)
    cmds+=("cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py")
    ;;
  all)
    add_api_unit
    add_web_unit
    cmds+=("cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py")
    ;;
esac

if [[ ${#cmds[@]} -eq 0 ]]; then
  echo "nothing to run for layer=$LAYER scope=$SCOPE"
  exit 0
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "DRY RUN -- layer=$LAYER scope=$SCOPE"
  for cmd in "${cmds[@]}"; do
    echo "  \$ $cmd"
  done
  exit 0
fi

if printf '%s\n' "${cmds[@]}" | grep -q 'uv run' && ! command -v uv >/dev/null 2>&1; then
  echo "uv is missing (export PATH=\"$HOME/.local/bin:$PATH\")" >&2
  exit 2
fi
if printf '%s\n' "${cmds[@]}" | grep -q 'pnpm -C' && ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is missing" >&2
  exit 2
fi

run_dir="var/evidence/$(date -u +%Y%m%dT%H%M%SZ)-$LAYER"
mkdir -p "$run_dir"
{
  echo "layer=$LAYER scope=$SCOPE"
  for cmd in "${cmds[@]}"; do echo "\$ $cmd"; done
} > "$run_dir/commands.txt"

i=0
for cmd in "${cmds[@]}"; do
  i=$((i + 1))
  log="$run_dir/$(printf '%02d' "$i").log"
  echo "[$i/${#cmds[@]}] $cmd"
  if ! bash -c "$cmd" 2>&1 | tee "$log"; then
    echo "FAIL: $cmd (log: $log)" >&2
    exit 1
  fi
done
echo "ALL PASS ($i commands) -- evidence: $run_dir"
