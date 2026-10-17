#!/usr/bin/env bash
# 远端 PR 状态只读可见：打印当前分支的 PR 状态（number / state / base / head），没有 PR 时打印「无 PR」。
# 本脚本对本地 git 与远端都只读：建 PR、合并 PR 永远是人的动作（AGENTS.md 硬规则 1）。
# 每次调用现读远端，不缓存不落盘——缓存下来的状态会与远端漂移，那正是本票要消灭的不可见。
#
# 用法：
#   bash scripts/pr_state.sh             打印当前分支的 PR 状态
#   bash scripts/pr_state.sh --selftest  内置样本自检（假 gh 覆盖：有 PR / 无 PR / 调用失败 / gh 缺失 / 不在仓库里）
#   bash scripts/pr_state.sh --help      本用法
# 环境变量 BR_PR_STATE_GH：gh 可执行文件路径，默认 PATH 里的 gh（自检与非常规安装用）。
#
# 退出码：0 读到状态（含「无 PR」）；1 gh 调用失败（未登录 / 网络 / 远端拒绝）；2 环境不满足（不在 git 仓库 / detached HEAD / 找不到 gh）。
# 「无 PR」与「gh 坏了」必须分得开：前者退出 0 且正文写「无 PR」，后者退出非 0 且点名原因。
# 口径出处：docs/tickets/p15-agent-friendly-architecture/T25-pr-state.md、recall-report.md [F18]。
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
GH_BIN="${BR_PR_STATE_GH:-gh}"
errf="" # 全局：EXIT trap 在函数返回后触发，引用局部变量会 unbound
selftest_tmp="" # 同上：cleanup 由 EXIT trap 触发，不能引用 selftest 的局部变量

fail() { # fail <原因> [退出码]；原因一律写 stderr
  printf "pr_state: %s\n" "$1" >&2
  exit "${2:-1}"
}

usage() {
  cat <<"EOF"
用法：
  bash scripts/pr_state.sh             打印当前分支的 PR 状态
  bash scripts/pr_state.sh --selftest  内置样本自检
环境变量 BR_PR_STATE_GH：gh 可执行文件路径，默认 PATH 里的 gh。
退出码：0 读到状态（含「无 PR」）；1 gh 调用失败；2 环境不满足（不在 git 仓库 / detached HEAD / 找不到 gh）。
EOF
}

# 唯一的远端读法：gh pr list 是 GET，本脚本里不存在任何远端写动作。
pr_line() { # pr_line <分支>；空输出 = 该分支没有 PR
  "$GH_BIN" pr list --head "$1" --state all \
    --json number,state,baseRefName,headRefName \
    --jq 'sort_by(.number) | last | select(.) | "number=\(.number) state=\(.state) base=\(.baseRefName) head=\(.headRefName)"'
}

status() {
  local branch out reason
  if ! command -v git >/dev/null 2>&1; then
    fail "git 不可用：找不到可执行文件 git（本脚本靠 git 确定当前分支）" 2
  fi
  if ! branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"; then
    fail "不在 git 仓库里，读不到当前分支" 2
  fi
  case "$branch" in
  "" | HEAD) fail "HEAD 处于 detached 状态，没有分支名可查 PR" 2 ;;
  esac
  if ! command -v "$GH_BIN" >/dev/null 2>&1; then
    fail "gh 不可用：找不到可执行文件 $GH_BIN（装 gh，或用 BR_PR_STATE_GH 指到它）" 2
  fi
  errf="$(mktemp)"
  trap 'rm -f "$errf"' EXIT
  if out="$(pr_line "$branch" 2>"$errf")"; then
    if [ -z "$out" ]; then
      printf "无 PR：分支 %s 在远端没有 PR\n" "$branch"
    else
      printf "%s\n" "$out"
    fi
    return 0
  fi
  reason="$(tr '\n' ' ' <"$errf")"
  fail "gh 调用失败（未登录 / 网络 / 远端拒绝）：${reason:-无输出}" 1
}

selftest() {
  local rc total fails hit out
  selftest_tmp="$(mktemp -d)"
  cleanup() { rm -rf "$selftest_tmp"; }
  trap cleanup EXIT

  fake_gh() { # fake_gh <路径>：从 stdin 读正文，装成可执行的假 gh
    cat >"$1"
    chmod +x "$1"
  }
  fake_gh "$selftest_tmp/gh-open" <<'FAKE'
#!/usr/bin/env bash
printf 'number=31 state=OPEN base=main head=p15-agent-friendly-architecture\n'
FAKE
  fake_gh "$selftest_tmp/gh-none" <<'FAKE'
#!/usr/bin/env bash
exit 0
FAKE
  fake_gh "$selftest_tmp/gh-fail" <<'FAKE'
#!/usr/bin/env bash
printf 'To get started with GitHub CLI, please run: gh auth login\n' >&2
exit 4
FAKE

  run_case() { # run_case <假 gh 路径> [工作目录]；结果落 out / rc
    if out="$(cd "${2:-.}" && BR_PR_STATE_GH="$1" bash "$SELF" 2>&1)"; then
      rc=0
    else
      rc=$?
    fi
  }
  expect() { # expect <描述> <期望> <实际>
    total=$((total + 1))
    if [ "$2" = "$3" ]; then
      printf "ok   %s：%s\n" "$1" "$3"
    else
      fails=$((fails + 1))
      printf "FAIL %s：期望 [%s] 实际 [%s]\n" "$1" "$2" "$3"
    fi
  }
  contains() { # contains <描述> <子串> <全文>
    hit=no
    case "$3" in *"$2"*) hit=yes ;; esac
    expect "$1" yes "$hit"
  }

  total=0
  fails=0

  run_case "$selftest_tmp/gh-open"
  expect "有 PR：退出码" "0" "$rc"
  expect "有 PR：正文" "number=31 state=OPEN base=main head=p15-agent-friendly-architecture" "$out"

  run_case "$selftest_tmp/gh-none"
  expect "无 PR：退出码" "0" "$rc"
  contains "无 PR：正文点名「无 PR」" "无 PR：" "$out"

  run_case "$selftest_tmp/gh-fail"
  expect "调用失败：退出码" "1" "$rc"
  contains "调用失败：点名 gh 未登录" "gh auth login" "$out"

  run_case "$selftest_tmp/缺这个文件"
  expect "gh 缺失：退出码" "2" "$rc"
  contains "gh 缺失：点名找不到可执行文件" "找不到可执行文件" "$out"

  # 临时目录落在某个 git 工作树内、或本机没有 git 时这条判定不成立，跳过并明说（不静默通过）
  if ! command -v git >/dev/null 2>&1 || git -C "$selftest_tmp" rev-parse --show-toplevel >/dev/null 2>&1; then
    printf "skip 不在 git 仓库：临时目录 %s 落在 git 工作树内或本机没有 git，跳过该断言\n" "$selftest_tmp"
  else
    run_case "$selftest_tmp/gh-none" "$selftest_tmp"
    expect "不在 git 仓库：退出码" "2" "$rc"
    contains "不在 git 仓库：点名原因" "不在 git 仓库里" "$out"
  fi

  printf "selftest: %s 项断言，失败 %s 项\n" "$total" "$fails"
  if [ "$fails" -ne 0 ]; then return 1; fi
  return 0
}

main() {
  case "${1:-}" in
  --selftest) selftest ;;
  -h | --help) usage ;;
  "") status ;;
  *)
    usage >&2
    return 2
    ;;
  esac
}

main "$@"