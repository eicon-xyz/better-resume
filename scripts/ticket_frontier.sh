#!/usr/bin/env bash
# 票据结构校验与 frontier 输出（只读票目录，不写票）。
# 用法：
#   bash scripts/ticket_frontier.sh <stage-dir>          打印 frontier 一行：T<N> <文件名> <标题>
#   bash scripts/ticket_frontier.sh --check <stage-dir>  结构校验：缺 Status / 阻塞指向不存在的票 / 同号重名
#   bash scripts/ticket_frontier.sh --selftest           内置样本自检
# 口径出处：docs/agents/issue-tracker.md（Status / Blocked by 语义、Wayfinding 的 Frontier 规则）。
set -euo pipefail

HEAD_LINES=20  # 「靠近顶部」的判定窗口：Status / Blocked by 只在这个行数内生效

is_ticket() {  # 票 = T<N>-<slug>.md；T<N>-EVIDENCE.md 是证据文件，不算票
  case "$(basename "$1")" in
    T[0-9]*-EVIDENCE.md) return 1 ;;
    T[0-9]*-*.md) return 0 ;;
    *) return 1 ;;
  esac
}

ticket_files() {  # 只认票文件；README、证据文件、报告都不是
  local dir="$1" f
  shopt -s nullglob
  for f in "$dir"/T[0-9]*-*.md; do
    if [[ -f "$f" ]] && is_ticket "$f"; then printf "%s\n" "$f"; fi
  done
  shopt -u nullglob
}

num_of() { basename "$1" | sed -E "s/^T([0-9]+)-.*$/\1/"; }

status_of() {  # 空输出 = 缺 Status 行
  head -n "$HEAD_LINES" "$1" | sed -nE "s/^Status:[[:space:]]*(.*)$/\1/p" | head -n 1
}

blockers_of() {  # 空输出 = 无阻塞
  local line
  line="$(head -n "$HEAD_LINES" "$1" | sed -nE "s/^Blocked by:[[:space:]]*(.*)$/\1/p" | head -n 1)"
  if [ -z "$line" ]; then return 0; fi
  printf "%s\n" "$line" | grep -oE "T[0-9]+" || true
}

title_of() {  # 取首个一级标题，去掉前缀的 T<N>
  local n
  n="$(num_of "$1")"
  sed -nE "s/^# +//p" "$1" | head -n 1 | sed -E "s/^T$n[[:space:]]+//"
}

is_closed() {  # 已结题的 Status：不再进 frontier、也不再阻塞别人
  case "$1" in
    resolved | wontfix) return 0 ;;
    *) return 1 ;;
  esac
}

find_ticket() {  # 按编号找票文件；多命中时多行输出，调用方取首行
  local dir="$1" n="$2" f
  shopt -s nullglob
  for f in "$dir"/T"$n"-*.md; do
    if [[ -f "$f" ]] && is_ticket "$f"; then printf "%s\n" "$f"; fi
  done
  shopt -u nullglob
}

sorted_tickets() {  # 编号升序（Frontier 的「编号最小者优先」）
  local dir="$1" f
  while IFS= read -r f; do
    printf "%s\t%s\n" "$(num_of "$f")" "$f"
  done < <(ticket_files "$dir") | sort -k1,1n -k2,2 | cut -f2-
}

blocked() {  # 退出 0 = 有阻塞
  local dir="$1" f="$2" b n bf st
  while IFS= read -r b; do
    if [ -z "$b" ]; then continue; fi
    n="${b#T}"
    bf="$(find_ticket "$dir" "$n" | head -n 1)"
    if [ -z "$bf" ]; then return 0; fi   # 指向不存在的票：无从判定其完成 → 视为阻塞（--check 另外点名）
    st="$(status_of "$bf")"
    if ! is_closed "$st"; then return 0; fi
  done < <(blockers_of "$f")
  return 1
}

frontier() {  # 未完成、无阻塞、未认领中编号最小的票；没有则静默退 0
  local dir="$1" f st
  if [ ! -d "$dir" ]; then printf "票目录不存在：%s\n" "$dir" >&2; return 2; fi
  while IFS= read -r f; do
    st="$(status_of "$f")"
    if is_closed "$st"; then continue; fi
    if [ "$st" = claimed ]; then continue; fi
    if blocked "$dir" "$f"; then continue; fi
    printf "T%s %s %s\n" "$(num_of "$f")" "$(basename "$f")" "$(title_of "$f")"
    return 0
  done < <(sorted_tickets "$dir")
}

check_tree() {  # 三类结构错任一出现 → 退 1 并点名文件
  local dir="$1" rc=0 count=0
  local -A seen=()
  local f n s b bf
  if [ ! -d "$dir" ]; then printf "票目录不存在：%s\n" "$dir" >&2; return 2; fi
  while IFS= read -r f; do  # 同号重名
    n="$(num_of "$f")"
    count=$((count + 1))
    if [ -n "${seen[$n]:-}" ]; then
      printf "%s: 同号重名：与 %s 同为 T%s\n" "$f" "$(basename "${seen[$n]}")" "$n" >&2
      rc=1
    else
      seen[$n]="$f"
    fi
  done < <(ticket_files "$dir")
  while IFS= read -r f; do  # 缺 Status 行 / Blocked by 悬空
    s="$(status_of "$f")"
    if [ -z "$s" ]; then
      printf "%s: 缺 Status 行\n" "$f" >&2
      rc=1
    fi
    while IFS= read -r b; do
      if [ -z "$b" ]; then continue; fi
      bf="$(find_ticket "$dir" "${b#T}" | head -n 1)"
      if [ -z "$bf" ]; then
        printf "%s: Blocked by 指向不存在的票 %s\n" "$f" "$b" >&2
        rc=1
      fi
    done < <(blockers_of "$f")
  done < <(sorted_tickets "$dir")
  if [ "$rc" -eq 0 ]; then printf "OK %s：结构校验通过（%s 张票）\n" "$dir" "$count"; fi
  return "$rc"
}

selftest_tmp=""  # 全局：EXIT trap 在 selftest 返回后触发，引用局部变量会 unbound

selftest() {  # 1 棵合法树 + 3 棵非法树，读数与预期逐条比对
  local total=0 fails=0 rc=0 hit=no d
  selftest_tmp="$(mktemp -d)"
  cleanup() { if [ -n "$selftest_tmp" ]; then rm -rf "$selftest_tmp"; fi; }
  trap cleanup EXIT
  for d in legal bad-status bad-blocker bad-dup; do mkdir -p "$selftest_tmp/$d"; done

  printf "# T1 一号票\nStatus: resolved\nBlocked by: 无\n" > "$selftest_tmp/legal/T1-done.md"
  printf "# T2 二号票\nStatus: claimed\nBlocked by: 无\n" > "$selftest_tmp/legal/T2-claimed.md"
  printf "# T3 三号票\nStatus: ready-for-agent\nBlocked by: T4\n" > "$selftest_tmp/legal/T3-waiting.md"
  printf "# T4 四号票\nStatus: ready-for-agent\nBlocked by: 无\n" > "$selftest_tmp/legal/T4-free.md"
  printf "# T1 未分类票\nBlocked by: 无\n" > "$selftest_tmp/bad-status/T1-nostatus.md"
  printf "# T2 二号票\nStatus: ready-for-agent\nBlocked by: 无\n" > "$selftest_tmp/bad-status/T2-ok.md"
  printf "# T1 悬空阻塞\nStatus: ready-for-agent\nBlocked by: T99\n" > "$selftest_tmp/bad-blocker/T1-orphan.md"
  printf "# T7 甲\nStatus: ready-for-agent\nBlocked by: 无\n" > "$selftest_tmp/bad-dup/T7-a.md"
  printf "# T7 乙\nStatus: ready-for-agent\nBlocked by: 无\n" > "$selftest_tmp/bad-dup/T7-b.md"

  expect() {  # expect <描述> <期望> <实际>
    total=$((total + 1))
    if [ "$2" = "$3" ]; then
      printf "ok   %s：%s\n" "$1" "$3"
    else
      fails=$((fails + 1))
      printf "FAIL %s：期望 [%s] 实际 [%s]\n" "$1" "$2" "$3"
    fi
  }

  expect "frontier：跳过 resolved / claimed / 被未结题票阻塞，取 T4" "T4 T4-free.md 四号票" "$(frontier "$selftest_tmp/legal")"

  if check_tree "$selftest_tmp/legal" >/dev/null 2>&1; then rc=0; else rc=$?; fi
  expect "check：合法树退出码" "0" "$rc"

  if check_tree "$selftest_tmp/bad-status" >/dev/null 2>"$selftest_tmp/e-status"; then rc=0; else rc=$?; fi
  expect "check：缺 Status 行退出码" "1" "$rc"
  hit=no; if grep -qF "T1-nostatus.md" "$selftest_tmp/e-status" && grep -qF "缺 Status 行" "$selftest_tmp/e-status"; then hit=yes; fi
  expect "check：缺 Status 行点名文件与原因" "yes" "$hit"

  if check_tree "$selftest_tmp/bad-blocker" >/dev/null 2>"$selftest_tmp/e-blocker"; then rc=0; else rc=$?; fi
  expect "check：Blocked by 悬空退出码" "1" "$rc"
  hit=no; if grep -qF "T1-orphan.md" "$selftest_tmp/e-blocker" && grep -qF "T99" "$selftest_tmp/e-blocker"; then hit=yes; fi
  expect "check：Blocked by 悬空点名文件与票号" "yes" "$hit"

  if check_tree "$selftest_tmp/bad-dup" >/dev/null 2>"$selftest_tmp/e-dup"; then rc=0; else rc=$?; fi
  expect "check：同号重名退出码" "1" "$rc"
  hit=no; if grep -qF "T7-a.md" "$selftest_tmp/e-dup" && grep -qF "T7-b.md" "$selftest_tmp/e-dup"; then hit=yes; fi
  expect "check：同号重名点名两个文件" "yes" "$hit"

  printf "selftest: %s 项断言，失败 %s 项\n" "$total" "$fails"
  if [ "$fails" -ne 0 ]; then return 1; fi
  return 0
}

usage() {
  cat <<"EOF"
用法：
  bash scripts/ticket_frontier.sh <stage-dir>          打印 frontier 一行：T<N> <文件名> <标题>
  bash scripts/ticket_frontier.sh --check <stage-dir>  结构校验，红则非 0
  bash scripts/ticket_frontier.sh --selftest           内置样本自检
规则出处：docs/agents/issue-tracker.md
EOF
}

main() {
  case "${1:-}" in
    --selftest) selftest ;;
    --check)
      if [ "$#" -lt 2 ]; then usage >&2; return 2; fi
      check_tree "$2"
      ;;
    -h | --help) usage ;;
    "") usage >&2; return 2 ;;
    *) frontier "$1" ;;
  esac
}

main "$@"
