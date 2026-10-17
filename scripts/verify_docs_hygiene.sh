#!/usr/bin/env bash
# 历史叙事门禁：拦「文档与代码注释记录了 AI 修改史」的写法（AGENTS.md 硬规则 2）。
# 判定口径 = 收窄禁词集 + 围栏代码块/行内 code 豁免 + 脚本内按原文精确匹配的豁免清单。
# 用法：bash scripts/verify_docs_hygiene.sh [--selftest]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------------------
# 禁词集（收窄模式）：每条都是「回顾过去」的措辞，不是技术术语。
# 收窄原则：只要某说法在「模板措辞/引证/评审问题」里也有正常用法，就不进这张表。
# 加词前先跑 --selftest 与全量扫描：阳性样本必红、现树必须 0 命中。
# ---------------------------------------------------------------------------
PATTERNS=(
  # 改版前后的对比叙事（「之前是 X，现在改为 Y」）。描述现状不需要这个时间状语；
  # 「之前」单独出现不拦，只拦陈述旧值的「之前是」。
  '之前是'
  # 轮次叙事（手测第几轮通过、第几轮修）。重试/轮询写「重试」「轮询」，不会写成「第…轮」；
  # 「第 N 层 / 第 N 步」等量词不受影响。
  '第[[:space:]]*(N|[0-9]+)[[:space:]]*轮'
  # 弃用史。当前状态直接说「不再使用」或删掉该节；无技术术语需要写「已废弃」。
  '已废弃'
  # 踩坑史，只出现在复盘叙述里，没有技术语义。
  '曾经踩过'
  # 被取代的旧决策留痕。文档只写当前生效的决策，不告诉读者哪条作废。
  '已作废'
)

# ---------------------------------------------------------------------------
# 显式豁免清单：AGENTS.md 硬规则 2 原文用禁词举反例（教学引用）。
# 每条 = 相对路径 + 该行原文（去首尾空白后精确相等）。原文一改即失效、门禁转红；
# 不做整文件/整目录豁免（docs/history_docs/ 是唯一整目录排除，见 collect_main_files）。
# ---------------------------------------------------------------------------
EXEMPTIONS=(
  # 硬规则 2 本条：原文同时举「本次改动」「之前是…现在改为」两个反例。
  'AGENTS.md|2. **文档与代码注释只描述当前状态，不记录任何 AI 的修改历史。** 不写「本次改动」「之前是 X、现在改为 Y」'
  # 硬规则 2 续行：原文举「第 N 轮修复」「已废弃」「曾经踩过」三个反例。
  'AGENTS.md|   「第 N 轮修复」「已废弃」「曾经踩过」这类叙述；读者看到的应当是这个项目**现在**长什么样、为什么这样。'
  # 硬规则 2 末行：原文举「原方案 A 已作废」反例。
  'AGENTS.md|   - 被新决策取代的旧决策**不留痕迹**：文档只写当前生效的决策（如「决策 B」），不写「原方案 A 已作废」。'
)

# 围栏代码块处理：行首（允许缩进）为 ``` 或 ~~~ 的行切换围栏状态，围栏内整行不判
# （引证原文、示例文本可以合法出现禁词）。
# 行内 code 处理：非围栏行先剥掉 `...` 片段再判（行内引证同样合法）。
# 两条规则都由 --selftest 的阴性样本覆盖。

PAT_LINES=$(printf '%s\n' "${PATTERNS[@]}")
EXEMPT_LINES=$(printf '%s\n' "${EXEMPTIONS[@]}")

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

usage() {
  echo "用法：bash scripts/verify_docs_hygiene.sh [--selftest]" >&2
  exit 2
}

die() {
  echo "verify_docs_hygiene: $*" >&2
  exit 2
}

# 扫描集：文档 + 源码注释。docs/history_docs/ 是历史归档，唯一允许的整目录排除。
collect_main_files() {
  (
    cd "$ROOT"
    find docs -path 'docs/history_docs' -prune -o -type f \( \
      -name '*.md' -o -name '*.html' -o -name '*.json' -o -name '*.yml' -o -name '*.yaml' \
      -o -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.css' \) -print
    find skills -type f \( -name '*.md' -o -name '*.html' -o -name '*.json' -o -name '*.yml' -o -name '*.yaml' \) -print
    for d in apps/api/src apps/api/tests apps/web/src; do
      if [ -d "$d" ]; then
        find "$d" -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.css' \) -print
      fi
    done
    printf '%s\n' AGENTS.md GLOSSARY.md CODING_STANDARDS.md
  ) | LC_ALL=C sort -u
}

# scan <root> <相对文件...>：结果写进 HITS / EXEMPTED / HIT_LINES。
scan() {
  local root="$1"; shift
  [ "$#" -gt 0 ] || die "扫描文件列表为空（拒绝静默绿灯）"
  local raw
  raw=$(cd "$root" && awk -v pats="$PAT_LINES" -v exems="$EXEMPT_LINES" '
BEGIN {
  np = split(pats, P, "\n")
  ne = split(exems, E, "\n")
  for (i = 1; i <= ne; i++) {
    if (E[i] == "") continue
    k = index(E[i], "|")
    txt = substr(E[i], k+1)
    sub(/^[[:space:]]+/, "", txt)
    sub(/[[:space:]]+$/, "", txt)
    EX[substr(E[i], 1, k-1) SUBSEP txt] = 1
  }
}
FNR == 1 { fence = 0 }
{
  trimmed = $0
  sub(/^[[:space:]]+/, "", trimmed)
  sub(/[[:space:]]+$/, "", trimmed)
  if ($0 ~ /^[[:space:]]*(```|~~~)/) { fence = !fence; next }
  if (fence) next
  line = $0
  while (match(line, /`[^`]*`/))
    line = substr(line, 1, RSTART-1) substr(line, RSTART+RLENGTH)
  for (i = 1; i <= np; i++) {
    if (P[i] == "") continue
    if (line ~ P[i]) {
      if ((FILENAME SUBSEP trimmed) in EX) { exempted++; continue }
      printf "HIT\t%s:%d: 命中「%s」→ %s\n", FILENAME, FNR, P[i], trimmed
      hits++
    }
  }
}
END {
  printf "EXEMPTED=%d\n", exempted
}' "$@")
  HIT_LINES=$(printf '%s\n' "$raw" | grep -v '^EXEMPTED=' || true)
  HITS=$(printf '%s\n' "$HIT_LINES" | grep -c . || true)
  EXEMPTED=$(printf '%s\n' "$raw" | sed -n 's/^EXEMPTED=//p')
  EXEMPTED=${EXEMPTED:-0}
}

selftest() {
  local pos="$WORK/pos" neg="$WORK/neg" clean="$WORK/clean" mutated="$WORK/mutated"
  local failures=0 total=0
  mkdir -p "$pos" "$neg" "$clean" "$mutated"

  # 阳性样本：原型 B 取自 84f622b 删除的真实历史叙事文字。
  printf '%s\n' \
    '**P1-A 浏览器手测已完成**（第 3 轮通过，2026-09-17）：…' \
    '| 第 1 轮 | 2026-09-15 | §1 步骤 1–4 …' > "$pos/84f622b.md"

  # 阳性样本：逐条禁词各一份，防某条被删/改坏后仍绿。
  printf '%s\n' 'X 之前是 Y，现在改为 Z。' > "$pos/before.md"
  printf '%s\n' '这条用例第 N 轮修复后仍然偶发。' > "$pos/round.md"
  printf '%s\n' '旧接口已废弃，迁移期两套并存。' > "$pos/deprecated.md"
  printf '%s\n' '这里曾经踩过一个时序坑。' > "$pos/pit.md"
  printf '%s\n' '方案 A 已作废，只保留生效的决策。' > "$pos/void.md"

  # 阴性样本：CODING_STANDARDS §6 的「不适用」模板措辞（「本次改动没有 X」）。
  printf '%s\n' '| 不适用 | **事实层面不涉及**：本次改动没有 X | 一句话说清为什么不涉及 |' > "$neg/template.md"

  # 阴性样本：围栏代码块里的引证（README 原型结论 B 贴出的坏文本就是这种形态）。
  {
    printf '%s\n' '```text'
    printf '%s\n' '**P1-A 浏览器手测已完成**（第 3 轮通过，2026-09-17）：…'
    printf '%s\n' '「第 N 轮修复」「已废弃」「曾经踩过」「已作废」「之前是 X」'
    printf '%s\n' '```'
  } > "$neg/fence.md"

  # 阴性样本：行内 code 里的引证。
  printf '%s\n' '教学引用：`第 3 轮`、`已废弃`、`曾经踩过`、`已作废`、`之前是 X`。' > "$neg/inline_code.md"

  # 豁免样本：真实 AGENTS.md 的三行规则原文（精确匹配 → 绿）；改一个字符即失效（→ 红）。
  cp "$ROOT/AGENTS.md" "$clean/AGENTS.md"
  sed 's/之前是/之前是（改）/' "$ROOT/AGENTS.md" > "$mutated/AGENTS.md"

  t_red() {
    local name="$1"; shift
    total=$((total+1))
    scan "$@"
    if [ "$HITS" -eq 0 ]; then
      echo "FAIL [必红] $name：0 命中，禁词集漏了这类写法" >&2
      failures=$((failures+1))
    else
      echo "ok   [必红] $name：命中 $HITS 处"
    fi
  }

  t_green() {
    local name="$1"; shift
    total=$((total+1))
    scan "$@"
    if [ "$HITS" -ne 0 ]; then
      printf '%s\n' "$HIT_LINES" >&2
      echo "FAIL [必绿] $name：命中 $HITS 处，误伤" >&2
      failures=$((failures+1))
    else
      echo "ok   [必绿] $name"
    fi
  }

  t_red   '84f622b 手测轮次样本' "$pos" 84f622b.md
  t_red   '禁词 之前是'          "$pos" before.md
  t_red   '禁词 第 N 轮'         "$pos" round.md
  t_red   '禁词 已废弃'          "$pos" deprecated.md
  t_red   '禁词 曾经踩过'        "$pos" pit.md
  t_red   '禁词 已作废'          "$pos" void.md
  t_green 'CODING_STANDARDS 不适用模板措辞' "$neg" template.md
  t_green '围栏代码块内引证'      "$neg" fence.md
  t_green '行内 code 内引证'      "$neg" inline_code.md

  total=$((total+1))
  scan "$clean" AGENTS.md
  if [ "$HITS" -eq 0 ] && [ "$EXEMPTED" -eq 5 ]; then
    echo "ok   [必绿] AGENTS.md 硬规则 2 三行原文按清单豁免（3 行共 5 个禁词命中）"
  else
    echo "FAIL [必绿] AGENTS.md 三行原文：命中 $HITS 处、豁免 $EXEMPTED 处（应为 0 与 5）" >&2
    failures=$((failures+1))
  fi

  t_red '豁免只认原文：改一个字符即失效' "$mutated" AGENTS.md

  if [ "$failures" -ne 0 ]; then
    echo "自检失败：$failures/$total 个用例不符预期" >&2
    exit 1
  fi
  echo "自检通过：$total/$total 个用例符合预期"
}

main() {
  local p
  for p in docs skills apps/api/src apps/api/tests apps/web/src AGENTS.md GLOSSARY.md CODING_STANDARDS.md; do
    [ -e "$ROOT/$p" ] || die "扫描根缺失：$p（拒绝静默缩小扫描集）"
  done
  local files=()
  mapfile -t files < <(collect_main_files)
  [ "${#files[@]}" -gt 0 ] || die "扫描集为空（拒绝静默绿灯）"
  scan "$ROOT" "${files[@]}"
  if [ "$HITS" -gt 0 ]; then
    printf '%s\n' "$HIT_LINES"
    echo "verify_docs_hygiene: 命中 $HITS 处历史叙事。禁词集见脚本顶部；确属教学引用请进脚本内豁免清单（按原文精确匹配 + 理由）。" >&2
    exit 1
  fi
  echo "扫描 ${#files[@]} 个文件，命中 0 处；豁免 $EXEMPTED 处命中（脚本内清单）。"
}

case "${1:-}" in
  '') main ;;
  --selftest) selftest ;;
  *) usage ;;
esac
