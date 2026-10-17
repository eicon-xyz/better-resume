#!/usr/bin/env bash
# 写入路径越界门禁：判定改动文件是否落在票头「唯一写入路径:」行的字面声明内。
#
# 出处：p15 README 建议 12 的工具半边 + docs/agents/subagents.md §8.2 五栏交接包。
# 「执行方只许写这一个文件或目录」在派活时只是约定，越界没有任何东西会红；这里把它做成判定。
#
# 用法：
#   bash scripts/verify_write_scope.sh --check <票文件>        票：改动 vs 该票声明（逐文件判定）
#   bash scripts/verify_write_scope.sh --check <阶段目录>      阶段：改动 vs 该目录各票声明的并集
#   bash scripts/verify_write_scope.sh --check <票文件|阶段目录> --paths-from <清单文件>
#   bash scripts/verify_write_scope.sh --selftest              内嵌好票/坏票样本自检
#
# 退出码：0 全部落在声明内；1 越界（点名文件与声明）；2 用法或环境错。
# 「票头没有可解析的声明」判 2，不许静默判 0（D22：只打印结论不判定的脚本算缺陷）。
#
# 声明解析只认票头 HEAD_LINES 行内的「唯一写入路径:」行，取该行里反引号包裹的字面 token
# （目录可带尾斜杠）。不做猜测、不做短名补全：行里的字面 token 就是全部声明。代价是 T21 那类
# 把补充说明写进括号的票，括号内的字面 token 也会算进声明——它只会放宽允许集，不掩盖越界。
#
# 改动清单默认取工作区真实 diff（git diff HEAD 的已跟踪改动 + 未跟踪文件）。工作区常同时躺着
# 多个阶段的在飞改动，所以「这一轮有没有越界」要配 --paths-from 传本轮清单；票面文件的 sha256
# 基线是派活流程动作（§8.7），本工具只判 diff 越界。
#
# 阶段目录模式的判定是并集覆盖：改动文件落在目录里任意一张票的声明内即算合规，读数给出每张票
# 覆盖了几个文件。它看不出「本轮的票写了别人票的范围」——那条要用单票模式配 --paths-from 判。
#
# 豁免（case 明确点名，不做模糊排除）：*-EVIDENCE.md（票据两段自述，§8.3 不算写入路径）、
# 被检查阶段目录里的票文件 T<N>-*.md 与 PROBLEMS.md（阶段规格与台账，是输入不是写入产物）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SELF="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
cd "$ROOT"

HEAD_LINES=20
BT="$(printf '\x60')"
MODE=""
CHECK=""
PATHS_FROM=""
STAGE_DIR=""

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

usage() { awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, "", $0); print }' "$0"; }
die() { echo "verify_write_scope: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK="${2:-}"; MODE=check; shift 2 ;;
    --paths-from) PATHS_FROM="${2:-}"; shift 2 ;;
    --selftest) MODE=selftest; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ---- 声明解析：票头 HEAD_LINES 行内的那一行 + 该行里反引号包裹的字面 token ----
decl_line() { head -n "$HEAD_LINES" "$1" | grep -m1 '^唯一写入路径' || true; }

tokens_of() { awk -v bt="$BT" '{ n = split($0, seg, bt); for (i = 2; i <= n; i += 2) if (seg[i] != "") print seg[i] }'; }

declared_entries() {  # stdout：该票声明的字面 token；解析不出来返回 2
  local ticket="$1" line tokens
  line="$(decl_line "$ticket")"
  if [ -z "$line" ]; then
    echo "FAIL：$ticket 票头 $HEAD_LINES 行内没有「唯一写入路径:」行，解析不出来（不猜）" >&2
    return 2
  fi
  tokens="$(printf '%s\n' "$line" | tokens_of)"
  if [ -z "$tokens" ]; then
    echo "FAIL：$ticket 的「唯一写入路径:」行里没有反引号包裹的字面路径" >&2
    return 2
  fi
  printf '%s\n' "$tokens"
}

# 声明条目 vs 路径：目录按路径段前缀比较（scripts/ 覆盖 scripts/a.sh，不覆盖 scripts_extra/a.sh），
# 文件按精确相等比较（AGENTS.md 不覆盖 AGENTS.md.bak）。
in_scope() {
  local e="$1" p="$2"
  e="${e%/}"
  [ -n "$e" ] || return 1
  [[ "$p" == "$e" || "$p" == "$e"/* ]]
}

covered_by_entries() {  # covered_by_entries <路径> <条目文件>
  local p="$1" e
  while IFS= read -r e; do
    [ -n "$e" ] || continue
    if in_scope "$e" "$p"; then return 0; fi
  done < "$2"
  return 1
}

exempt_path() {  # 0 = 豁免
  local p="$1"
  case "$p" in
    *-EVIDENCE.md) return 0 ;;
  esac
  if [ -n "$STAGE_DIR" ]; then
    case "$p" in
      "$STAGE_DIR"/T[0-9]*-*.md | "$STAGE_DIR"/PROBLEMS.md) return 0 ;;
    esac
  fi
  return 1
}

collect_paths() {  # stdout：每行一个相对仓库根的改动路径
  if [ -n "$PATHS_FROM" ]; then
    [ -f "$PATHS_FROM" ] || die "--paths-from 不是文件：$PATHS_FROM"
    tr '\0' '\n' < "$PATHS_FROM" | sed 's|^\./||'
    return 0
  fi
  command -v git >/dev/null 2>&1 || die "git 不在 PATH（默认改动清单由 git 取）"
  git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1 || die "$ROOT 不是 git 检出"
  git -C "$ROOT" diff --name-only --no-renames -z HEAD > "$WORK/tracked.z" || die "git diff HEAD 失败"
  git -C "$ROOT" ls-files --others --exclude-standard -z > "$WORK/untracked.z" || die "git ls-files 失败"
  cat "$WORK/tracked.z" "$WORK/untracked.z" | tr '\0' '\n' | sed 's|^\./||'
}

load_paths() {  # 归一化到 $WORK/paths.txt
  collect_paths | sed '/^$/d' | LC_ALL=C sort -u > "$WORK/paths.txt"
}

check_ticket() {  # 0 全在声明内；1 越界；2 解析不出声明
  local ticket="$1" line entries="$WORK/entries.txt" p n_total=0 n_in=0 n_out=0 exempt=0
  declared_entries "$ticket" > "$entries" || return 2
  line="$(decl_line "$ticket")"
  echo "票：$ticket"
  echo "声明行原文：$line"
  echo "声明字面条目：$(paste -sd' ' "$entries")"
  while IFS= read -r p; do
    n_total=$((n_total + 1))
    if exempt_path "$p"; then exempt=$((exempt + 1)); continue; fi
    if covered_by_entries "$p" "$entries"; then
      n_in=$((n_in + 1))
    else
      n_out=$((n_out + 1))
      printf '越界：%s（不在这张票的声明内：%s）\n' "$p" "$(paste -sd' ' "$entries")" >&2
    fi
  done < "$WORK/paths.txt"
  printf '读数：改动 %s 个文件 → 声明内 %s，越界 %s，豁免 %s\n' "$n_total" "$n_in" "$n_out" "$exempt"
  if [ "$n_out" -gt 0 ]; then
    echo "FAIL：$ticket 越界 $n_out 个文件" >&2
    return 1
  fi
  echo "OK：改动全部落在该票声明内"
  return 0
}

ticket_files() {  # 阶段目录里的票文件；证据文件不算票
  local dir="$1" f
  shopt -s nullglob
  for f in "$dir"/T[0-9]*-*.md; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in
      T[0-9]*-EVIDENCE.md) continue ;;
    esac
    printf '%s\n' "$f"
  done
  shopt -u nullglob
}

check_stage() {  # 并集覆盖判定
  local dir="$1" tickets="$WORK/tickets.txt" pairs="$WORK/pairs.txt" cover="$WORK/cover.txt"
  ticket_files "$dir" > "$tickets"
  if [ ! -s "$tickets" ]; then
    echo "FAIL：$dir 下没有票文件（T<N>-*.md），拒绝空扫描假绿" >&2
    return 2
  fi
  echo "阶段目录：$dir（$(wc -l < "$tickets") 张票）"
  : > "$pairs"
  local t e p hit n n_total=0 n_in=0 n_out=0 exempt=0
  while IFS= read -r t; do
    declared_entries "$t" > "$WORK/one.txt" || return 2
    while IFS= read -r e; do
      [ -n "$e" ] || continue
      printf '%s\t%s\n' "$t" "$e" >> "$pairs"
    done < "$WORK/one.txt"
  done < "$tickets"
  : > "$cover"
  while IFS= read -r p; do
    n_total=$((n_total + 1))
    if exempt_path "$p"; then exempt=$((exempt + 1)); continue; fi
    hit="$WORK/hit.txt"; : > "$hit"
    while IFS=$'\t' read -r t e; do
      if in_scope "$e" "$p"; then printf '%s\n' "$t" >> "$hit"; fi
    done < "$pairs"
    if [ -s "$hit" ]; then
      n_in=$((n_in + 1))
      cat "$hit" >> "$cover"
    else
      n_out=$((n_out + 1))
      printf '越界：%s（不属于 %s 里任何一张票的声明）\n' "$p" "$dir" >&2
    fi
  done < "$WORK/paths.txt"
  echo "每张票覆盖的改动文件数："
  while IFS= read -r t; do
    n="$(grep -Fxc "$t" "$cover" || true)"
    printf '  %s：%s\n' "$t" "${n:-0}"
  done < "$tickets"
  printf '读数：改动 %s 个文件 → 被声明覆盖 %s，越界 %s，豁免 %s\n' "$n_total" "$n_in" "$n_out" "$exempt"
  if [ "$n_out" -gt 0 ]; then
    echo "FAIL：$n_out 个改动文件不属于 $dir 任何一张票的声明" >&2
    return 1
  fi
  echo "OK：改动全部落在 $dir 各票声明的并集内"
  return 0
}

normalize_dir() {  # 统一成与改动清单同一套写法（相对仓库根 / 或原样的绝对路径）
  local d="$1"
  case "$d" in
    ./*) d="${d#./}" ;;
  esac
  case "$d" in
    "$ROOT"/*) d="${d#"$ROOT"/}" ;;
  esac
  printf '%s\n' "${d%/}"
}

selftest() {
  local d="$WORK/selftest" total=0 fails=0 rc=0
  mkdir -p "$d/good" "$d/bad" "$d/edge" "$d/stage-ok" "$d/stage-bad" "$d/undeclared"

  printf '# T1 好票\nStatus: ready-for-agent\n唯一写入路径: %sscripts/%s\n' "$BT" "$BT" > "$d/good/T1-ok.md"
  printf '%s\n' 'scripts/a.sh' 'scripts/sub/b.py' > "$d/paths-ok.txt"

  printf '# T2 坏票\nStatus: ready-for-agent\n唯一写入路径: %sscripts/%s\n' "$BT" "$BT" > "$d/bad/T2-bad.md"
  printf '%s\n' 'scripts/a.sh' 'apps/api/x.py' > "$d/paths-bad.txt"

  printf '# T3 边界票\nStatus: ready-for-agent\n唯一写入路径: %sscripts/%s 与 %sAGENTS.md%s\n' "$BT" "$BT" "$BT" "$BT" > "$d/edge/T3-edge.md"
  printf '%s\n' 'scripts_extra/a.sh' > "$d/paths-prefix.txt"
  printf '%s\n' 'AGENTS.md' > "$d/paths-file-ok.txt"
  printf '%s\n' 'AGENTS.md.bak' > "$d/paths-file-bad.txt"

  printf '# T4 豁免票\nStatus: ready-for-agent\n唯一写入路径: %sscripts/%s\n' "$BT" "$BT" > "$d/edge/T4-exempt.md"
  printf '%s\n' "$d/edge/T9-EVIDENCE.md" "$d/edge/PROBLEMS.md" "$d/edge/T4-exempt.md" 'scripts/a.sh' > "$d/paths-exempt.txt"

  printf '# T5 没写声明的票\nStatus: ready-for-agent\n' > "$d/undeclared/T5-undeclared.md"

  printf '# T6 甲\nStatus: ready-for-agent\n唯一写入路径: %sscripts/%s\n' "$BT" "$BT" > "$d/stage-ok/T6-a.md"
  printf '# T7 乙\nStatus: ready-for-agent\n唯一写入路径: %sapps/api/%s\n' "$BT" "$BT" > "$d/stage-ok/T7-b.md"
  cp "$d/stage-ok/T6-a.md" "$d/stage-bad/T6-a.md"
  cp "$d/stage-ok/T7-b.md" "$d/stage-bad/T7-b.md"
  printf '%s\n' 'scripts/a.sh' 'apps/api/x.py' "$d/stage-ok/T6-EVIDENCE.md" > "$d/paths-stage-ok.txt"
  printf '%s\n' 'scripts/a.sh' 'docs/DECISIONS.md' > "$d/paths-stage-bad.txt"

  expect_run() {  # expect_run <描述> <期望退出码> <期望stdout子串> <期望stderr子串> <参数...>
    local desc="$1" want="$2" want_out="$3" want_err="$4" got=0 out err
    shift 4
    total=$((total + 1))
    if out="$(bash "$SELF" "$@" 2> "$WORK/err.txt")"; then got=0; else got=$?; fi
    err="$(cat "$WORK/err.txt")"
    if [ "$got" -ne "$want" ]; then
      printf 'FAIL %s：期望退出码 %s，实际 %s\n' "$desc" "$want" "$got" >&2
      printf '%s\n%s\n' "$out" "$err" >&2
      fails=$((fails + 1))
      return 0
    fi
    if [ -n "$want_out" ] && ! printf '%s\n' "$out" | grep -qF -- "$want_out"; then
      printf 'FAIL %s：stdout 里没有「%s」\n' "$desc" "$want_out" >&2
      printf '%s\n' "$out" >&2
      fails=$((fails + 1))
      return 0
    fi
    if [ -n "$want_err" ] && ! printf '%s\n' "$err" | grep -qF -- "$want_err"; then
      printf 'FAIL %s：stderr 里没有「%s」\n' "$desc" "$want_err" >&2
      printf '%s\n' "$err" >&2
      fails=$((fails + 1))
      return 0
    fi
    printf 'ok   %s\n' "$desc"
  }

  expect_run '好票（改动全在声明内）绿' 0 '读数：改动 2 个文件 → 声明内 2，越界 0，豁免 0' '' \
    --check "$d/good/T1-ok.md" --paths-from "$d/paths-ok.txt"
  expect_run '坏票（越界一个文件）红并点名文件与声明' 1 '读数：改动 2 个文件 → 声明内 1，越界 1，豁免 0' \
    '越界：apps/api/x.py（不在这张票的声明内：scripts/）' \
    --check "$d/bad/T2-bad.md" --paths-from "$d/paths-bad.txt"
  expect_run '目录前缀不吃同级同名（scripts/ 不覆盖 scripts_extra/）' 1 '' '越界：scripts_extra/a.sh' \
    --check "$d/edge/T3-edge.md" --paths-from "$d/paths-prefix.txt"
  expect_run '文件声明精确匹配（AGENTS.md）' 0 '读数：改动 1 个文件 → 声明内 1，越界 0，豁免 0' '' \
    --check "$d/edge/T3-edge.md" --paths-from "$d/paths-file-ok.txt"
  expect_run '文件声明不吃同名后缀（AGENTS.md.bak）' 1 '' '越界：AGENTS.md.bak' \
    --check "$d/edge/T3-edge.md" --paths-from "$d/paths-file-bad.txt"
  expect_run '豁免：票据自述 / 阶段票文件 / 台账不判' 0 '读数：改动 4 个文件 → 声明内 1，越界 0，豁免 3' '' \
    --check "$d/edge/T4-exempt.md" --paths-from "$d/paths-exempt.txt"
  expect_run '票头没有声明行 → 判 2（不静默绿）' 2 '' '没有「唯一写入路径:」行' \
    --check "$d/undeclared/T5-undeclared.md" --paths-from "$d/paths-ok.txt"
  expect_run '阶段模式：并集覆盖全部改动 → 绿' 0 '读数：改动 3 个文件 → 被声明覆盖 2，越界 0，豁免 1' '' \
    --check "$d/stage-ok" --paths-from "$d/paths-stage-ok.txt"
  expect_run '阶段模式：谁都不声明的文件 → 红并点名' 1 '' '越界：docs/DECISIONS.md' \
    --check "$d/stage-bad" --paths-from "$d/paths-stage-bad.txt"

  if [ "$fails" -ne 0 ]; then
    printf 'selftest=FAIL（%s/%s 个用例不符预期）\n' "$fails" "$total" >&2
    exit 1
  fi
  printf 'selftest=PASS（%s/%s 个用例符合预期）\n' "$total" "$total"
}

main() {
  case "$MODE" in
    selftest) selftest ;;
    check)
      [ -n "$CHECK" ] || { usage >&2; exit 2; }
      if [ -d "$CHECK" ]; then
        STAGE_DIR="$(normalize_dir "$CHECK")"
        load_paths
        check_stage "$STAGE_DIR"
      elif [ -f "$CHECK" ]; then
        STAGE_DIR="$(normalize_dir "$(dirname "$CHECK")")"
        load_paths
        check_ticket "$CHECK"
      else
        die "--check 的目标既不是票文件也不是目录：$CHECK"
      fi
      ;;
    *) usage >&2; exit 2 ;;
  esac
}

main "$@"
