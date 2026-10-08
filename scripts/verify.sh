#!/usr/bin/env bash
# P2-T1: the single entry point for every verification layer.
#
# CI and local MUST call this script instead of re-typing commands (M6 P16: "local green,
# CI red" happened because the two drifted). Evidence lands in var/evidence/<utc>-<layer>/.
#
# Usage:
#   scripts/verify.sh --list
#   scripts/verify.sh --layer unit|contract|coverage|deploy|fault|soak|real|scripts|all \
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
coverage:
  api: (the same pytest command as unit: api — it writes coverage-api.json)
  all: cd apps/api && uv run python scripts/check_coverage_floors.py --json coverage-api.json
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
  api: cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py
  all: for f in scripts/*.sh; do bash -n "$f" || exit 1; done
  all: uv run --project apps/api python scripts/check_scripts.py   (both script dirs, SyntaxWarning = error)
  all: uv run --project apps/api python scripts/verify_audit_evidence.py --structural
       (byte-level checking stays the manual --strict close-out step, never a layer — D22)
all:
  = unit + contract + coverage + scripts
MAP
  exit 0
fi

case "$LAYER" in
  unit|contract|coverage|deploy|fault|soak|real|scripts|all) ;;
  "") echo "no --layer given; usage: verify.sh --layer unit|contract|coverage|deploy|fault|soak|real|scripts|all" >&2; exit 2 ;;
  *) echo "unknown layer: $LAYER (see --list)" >&2; exit 2 ;;
esac

case "$SCOPE" in
  api|web|all) ;;
  *) echo "unknown scope: $SCOPE (api|web|all)" >&2; exit 2 ;;
esac

declare -a cmds=()

add_api_unit() { cmds+=("cd apps/api && uv run pytest --cov=better_resume --cov-report=json:coverage-api.json --cov-report=term"); }
add_web_unit() { cmds+=("pnpm -C apps/web exec vitest run"); }
add_coverage() {
  # The floor check reads coverage-api.json, which add_api_unit() writes (the same pytest command
  # CI's coverage step runs first). So "all" adds the judgement, not a second full run.
  cmds+=("cd apps/api && uv run python scripts/check_coverage_floors.py --json coverage-api.json")
}
add_api_contract() {
  cmds+=("cd apps/api && uv run ruff check .")
  cmds+=("cd apps/api && uv run ruff format --check .")
  cmds+=("cd apps/api && uv run alembic upgrade head")
  cmds+=("cd apps/api && uv run alembic check")
  cmds+=("cd apps/api && uv run python scripts/export_openapi.py --check")
  cmds+=("cd apps/api && uv run python scripts/extract_api_index.py --check")
}
add_web_contract() {
  cmds+=("pnpm -C apps/web lint")
  cmds+=("pnpm -C apps/web typecheck")
  cmds+=("pnpm -C apps/web check:api")
}
add_scripts() {
  cmds+=("cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py")
  # The drill scripts above are tested by pytest; the shell scripts next to them were not
  # (retro 2026-10-06: a proof script that always exited 0 shipped through a green CI).
  cmds+=("for f in scripts/*.sh; do bash -n \"\$f\" || exit 1; done; echo 'shell syntax ok'")
  # Both script dirs, SyntaxWarning as an error. (A glob from apps/api cannot see the repo
  # scripts: ../scripts resolves to apps/scripts, so the first cut of this line checked
  # nothing at the root level.)
  cmds+=("uv run --project apps/api python scripts/check_scripts.py")
  # Audit data, CI level (D22): fields present + every citation points at a range that exists.
  # This level is stable under code drift. The byte-level check (--strict) deliberately stays a
  # manual close-out step: a pure line shift must not turn CI red (measured: 3 inserted lines
  # moved 4 citations to partial and --strict exits 1, --structural exits 0).
  cmds+=("uv run --project apps/api python scripts/verify_audit_evidence.py --structural")
}

case "$LAYER" in
  unit)
    if [[ "$SCOPE" != "web" ]]; then add_api_unit; fi
    if [[ "$SCOPE" != "api" ]]; then add_web_unit; fi
    ;;
  contract)
    if [[ "$SCOPE" != "web" ]]; then add_api_contract; fi
    if [[ "$SCOPE" != "api" ]]; then add_web_contract; fi
    ;;
  deploy)
    cmds+=("bash scripts/compose_smoke.sh")
    cmds+=("bash scripts/kill_instance_drill.sh")
    ;;
  fault)
    cmds+=("bash scripts/fault_injection_drill.sh")
    ;;
  coverage)
    # CI runs this as its own step, so it needs its own data: produce it, then judge it.
    add_api_unit
    add_coverage
    ;;
  soak)
    # P39: this runs with cwd=apps/api, so a relative `var/evidence/...` landed in
    # apps/api/var/evidence/ (which does not exist): the 60-minute soak finished, passed,
    # and then died writing its evidence. Point --json at the repo root, where the weekly
    # workflow collects var/evidence/ from.
    soak_json="${VERIFY_EVIDENCE_DIR:-var/evidence}/soak-60m.json"
    # Quoted: the checkout path can contain spaces ("/root/better resume"), and the command
    # goes through `bash -c`, which would otherwise split the path into two arguments.
    cmds+=("mkdir -p ${VERIFY_EVIDENCE_DIR:-var/evidence} && cd apps/api && uv run python -m scripts.fault_probe soak --base http://127.0.0.1:8080 --duration 3600 --wave-seconds 30 --requests 30 --concurrency 4 --json \"$ROOT/$soak_json\"")
    ;;
  real)
    # P2-T4: budget-guarded real-machine suite — stage-closure MANDATORY (Q5).
    # Order matters: budget math first (pure), then the credential preflight, then the
    # dry-run exit, and only for a real run the stack health check + execution.
    budget="${BR_REAL_CALL_BUDGET:-200}"
    evidence_root="${VERIFY_EVIDENCE_DIR:-var/evidence}"
    spent_file="$evidence_root/real_calls_spent.txt"
    spent=0
    if [[ -f "$spent_file" ]]; then spent="$(cat "$spent_file")"; fi
    declare -a real_steps=(
      "12|cd apps/api && uv run python -m scripts.real_model_smoke"
      "2|cd apps/api && uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/p1c-multi-sentence-16k.wav"
      "2|cd apps/api && uv run python scripts/media_smoke.py --qwen-asr-real --wav ../../data/audio/v3-sample-16k.wav"
      "1|cd apps/api && uv run python scripts/assembler_real_probe.py"
      "4|cd apps/api && uv run python scripts/v3_ws_probe.py --realtime"
    )
    total=0
    for step in "${real_steps[@]}"; do total=$((total + ${step%%|*})); done
    if (( spent + total > budget )); then
      echo "real layer would exceed the call budget: spent=$spent + est=$total > budget=$budget (raise BR_REAL_CALL_BUDGET or reset $spent_file)" >&2
      exit 2
    fi
    env_file="${VERIFY_ENV_FILE:-.env}"
    if [[ ! -f "$env_file" ]]; then
      echo "real layer needs $env_file with BR_DASHSCOPE_API_KEY / BR_MEDIA__ASR_URL / BR_MEDIA__ASR_WS_URL; refusing" >&2
      exit 2
    fi
    for var in BR_DASHSCOPE_API_KEY BR_MEDIA__ASR_URL BR_MEDIA__ASR_WS_URL; do
      grep -q "^${var}=" "$env_file" || {
        echo "real layer needs ${var} in $env_file; refusing" >&2
        exit 2
      }
    done
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "DRY RUN -- layer=real scope=all budget=$budget spent=$spent est=$total"
      for step in "${real_steps[@]}"; do echo "  \$ ${step#*|}"; done
      exit 0
    fi
    # P32: the real steps need the ignored fixture audio (data/ is gitignored by design, Q3).
    # Refuse here -- still before the stack check and before any vendor call -- so a missing or
    # drifted fixture never becomes a half-finished, already-paid-for run.
    fixture_dir="${VERIFY_FIXTURE_AUDIO_DIR:-data/audio}"
    case "$fixture_dir" in
      /*) fixture_abs="$fixture_dir" ;;
      *) fixture_abs="$ROOT/$fixture_dir" ;;
    esac
    for fixture in p1c-multi-sentence-16k.wav v3-sample-16k.wav; do
      if [[ ! -f "$fixture_abs/$fixture" ]]; then
        echo "real layer needs the fixture audio $fixture_abs/$fixture (data/ is gitignored: run 'uv run python scripts/make_fixture_audio.py --generate', or point VERIFY_FIXTURE_AUDIO_DIR at your copy); refusing" >&2
        exit 2
      fi
    done
    if ! (cd apps/api && uv run python scripts/make_fixture_audio.py --check --file "$fixture_abs/p1c-multi-sentence-16k.wav" >/dev/null); then
      echo "real layer fixture drifted: $fixture_abs/p1c-multi-sentence-16k.wav does not match PINNED_SHA256 (make_fixture_audio.py --check); refusing" >&2
      exit 2
    fi
    if ! curl -sf --max-time 5 http://127.0.0.1:8080/healthz >/dev/null; then
      echo "real layer needs the compose stack up (curl /healthz failed); refusing" >&2
      exit 2
    fi
    mkdir -p "$evidence_root"
    for step in "${real_steps[@]}"; do
      est="${step%%|*}"
      cmd="${step#*|}"
      echo "(est $est vendor calls) $cmd"
      step_log="$evidence_root/real-$(date -u +%H%M%S)-$((RANDOM % 1000)).log"
      if ! bash -c "$cmd" 2>&1 | tee "$step_log"; then
        echo "FAIL: $cmd (log: $step_log)" >&2
        exit 1
      fi
      spent=$((spent + est))
      echo "$spent" > "$spent_file"
    done
    echo "real layer done; spent=$spent / budget=$budget"
    ;;
  scripts)
    add_scripts
    ;;
  all)
    # P31 + P8-retro: the advertised local closure. Every fast layer joins through its own builder
    # so the label in --list cannot drift from what actually runs. The coverage floors used to sit
    # outside this list entirely — a broken floor was locally green and CI red.
    add_api_unit
    add_coverage
    add_web_unit
    add_api_contract
    add_web_contract
    add_scripts
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
