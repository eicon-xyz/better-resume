#!/usr/bin/env bash
# 引证解析门禁：复核 markdown 里的「文件:行号」引证在仓库里真的存在（README 建议 9 / P09）。
#
# 用法：
#   bash scripts/verify_citations.sh <file.md> [file.md ...]
#   bash scripts/verify_citations.sh --selftest
#   bash scripts/verify_citations.sh [--root DIR] <file.md> ...
#
# 解析规则：
#   1. 引证 = 白名单扩展名的「<路径>:<行号>」，行号可写区间「<起>-<止>」；
#   2. 路径先在 --root（默认仓库根）下直配；直配不到时按 basename 兜底，全树唯一命中才算
#      成功——零命中判「文件不存在」，多命中判「短名歧义」：任选一个会让门禁替错误背书；
#   3. 行号必须落在 1..该文件行数 内；
#   4. 围栏代码块（行首允许缩进、以 ``` 或 ~~~ 切换状态）内的行整行不判——那里贴的是
#      门禁原始输出与样本，里面的「文件:行号」是引文不是引证；行内 code 不豁免
#      （行内引证是真引证）。
#
# 退出码：0 全部引证解析成功；1 有引证解析失败；2 用法或输入错误。
# --selftest 用临时树跑六个样本（好样本、不存在路径、行号越界、同名多文件、围栏内坏引证、
# 围栏外同款坏引证），证明门禁真的会判失败，而不是只打印结论。
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

# 引证 = 白名单扩展名的路径 + :行号[-(行号)]。前导字符类含 . 与 /，所以
# apps/web/src/api/schema.d.ts:42 整条被吃掉，而 127.0.0.1:5433（扩展名是数字）不会。
CITE_RE='[[:alnum:]_./-]+\.(py|ts|tsx|js|jsx|md|json|sh|yaml|yml|sql|css|html):[0-9]+(-[0-9]+)?'

# 整仓扫描跳过的目录：依赖与生成物——它们不是被引证的对象，而其中的同名 basename 会把
# 短名兜底误判成歧义（apps/web/coverage/base.css 与真正的 base.css 撞名，是否命中取决于
# 本机跑没跑过前端 coverage：索引不能是运行环境的隐式入参，P12）。
# ponytail: 这份目录名单是手维护的；要它自动跟随 .gitignore，就换成
#   git -C "$ROOT_DIR" ls-files --cached --others --exclude-standard（代价：--root 必须落在 git 工作树内）。
PRUNE=(-name .git -o -name node_modules -o -name .venv -o -name __pycache__
       -o -name .cache -o -name dist -o -name .ruff_cache -o -name .pytest_cache
       -o -name .mypy_cache -o -name coverage -o -name htmlcov)

WORK=""
ROOT_DIR=""
INDEX=""
BASEMAP=""

cleanup() {
  if [ -n "$WORK" ]; then rm -rf -- "$WORK"; fi
  return 0
}
trap cleanup EXIT

usage() {
  cat >&2 <<'USAGE'
用法：bash scripts/verify_citations.sh <file.md> [file.md ...]
      bash scripts/verify_citations.sh --selftest
      bash scripts/verify_citations.sh [--root DIR] <file.md> ...

复核 markdown 里的「文件:行号」引证：路径直配不到时按唯一 basename 兜底，行号必须在文件内；
围栏代码块内的行不判（贴出来的输出/样本），行内 code 照判。
退出码：0 全部解析成功；1 有引证解析失败；2 用法或输入错误。
USAGE
  exit 2
}

# 一次扫描建两个查表：全部文件（相对路径）与 basename 到相对路径。
build_index() {
  find "$ROOT_DIR" \( "${PRUNE[@]}" \) -prune -o -type f -printf '%P\n' > "$INDEX"
  awk -F/ '{print $NF "\t" $0}' "$INDEX" | LC_ALL=C sort > "$BASEMAP"
}

# 解析引证里的路径：成功打印相对路径；失败打印原因。
resolve() {
  local rel="$1" base
  if [ -f "$ROOT_DIR/$rel" ]; then
    printf '%s\n' "$rel"
    return 0
  fi
  base="${rel##*/}"
  local -a hits=()
  mapfile -t hits < <(awk -F'\t' -v b="$base" '$1 == b {print $2}' "$BASEMAP")
  if [ "${#hits[@]}" -eq 0 ]; then
    printf '文件不存在（整仓没有 basename 为 %s 的文件）' "$base"
    return 1
  fi
  if [ "${#hits[@]}" -gt 1 ]; then
    printf '短名 %s 歧义，命中 %d 个：%s' "$base" "${#hits[@]}" "${hits[*]}"
    return 1
  fi
  printf '%s\n' "${hits[0]}"
  return 0
}

# 围栏代码块内的行整行不判。掩码成空行而不是删行：行号必须与原文一一对应，否则 FAIL
# 行会指错行。行首允许缩进，``` 与 ~~~ 都切换状态（与 verify_docs_hygiene.sh 同口径）。
mask_fences() {
  awk '
    /^[[:space:]]*(```|~~~)/ { infence = !infence; print ""; next }
    infence { print ""; next }
    { print }
  ' "$1"
}

# 跑一个样本，断言退出码与输出关键词；不符时打印原始输出。
case_expect() {
  local want="$1" file="$2" needle="$3" what="$4" out got
  set +e
  out="$(bash "$SELF" --root "$WORK" "$file" 2>&1)"
  got=$?
  set -e
  if [ "$got" -ne "$want" ]; then
    echo "FAIL 自检：$what —— 期望退出 $want，实得 $got"
    printf '%s\n' "$out" | sed 's/^/      /'
    return 1
  fi
  if ! printf '%s\n' "$out" | grep -qF -- "$needle"; then
    echo "FAIL 自检：$what —— 退出码 $got 正确，但输出里没有「$needle」"
    printf '%s\n' "$out" | sed 's/^/      /'
    return 1
  fi
  echo "PASS 自检：$what —— 退出 $got"
  return 0
}

run_selftest() {
  local tmp
  tmp="$(mktemp -d)"
  WORK="$tmp"
  mkdir -p "$tmp/pkg/left" "$tmp/pkg/right"
  printf 'l1\nl2\nl3\nl4\nl5\n' > "$tmp/pkg/left/only.py"
  printf 'x\n' > "$tmp/pkg/left/dup.py"
  printf 'x\n' > "$tmp/pkg/right/dup.py"
  printf '直配 pkg/left/only.py:3 与短名 only.py:5\n' > "$tmp/good.md"
  printf '引证 no/such/file.py:3\n' > "$tmp/bad-missing.md"
  printf '引证 pkg/left/only.py:99\n' > "$tmp/bad-range.md"
  printf '引证 dup.py:1\n' > "$tmp/bad-ambiguous.md"
  # 围栏豁免的两面：围栏内整行不判（好引证照判，故坏样本被跳过而不是整文件放行）；
  # 围栏闭合后同款坏引证仍要抓住——只放过围栏，不放过围栏外的同款。
  printf '直配 pkg/left/only.py:3\n\n```text\n引证 no/such/file.py:3\n```\n' > "$tmp/fenced-ok.md"
  printf '~~~text\n引证 no/such/file.py:3\n~~~\n引证 no/such/file.py:3\n' > "$tmp/unfenced-bad.md"

  local rc=0
  case_expect 0 "$tmp/good.md"          '解析成功 2 失败 0' '好样本（直配 + 唯一短名）' || rc=1
  case_expect 1 "$tmp/bad-missing.md"   '文件不存在'        '不存在的路径'             || rc=1
  case_expect 1 "$tmp/bad-range.md"     '越界'              '行号越界'                 || rc=1
  case_expect 1 "$tmp/bad-ambiguous.md" '歧义'              '同名多文件的短名'         || rc=1
  case_expect 0 "$tmp/fenced-ok.md"     '解析成功 1 失败 0'  '围栏内的坏引证放过'       || rc=1
  case_expect 1 "$tmp/unfenced-bad.md"  '文件不存在'        '围栏外同款坏引证抓住'     || rc=1

  if [ "$rc" -eq 0 ]; then
    echo '自检通过 6/6：好样本绿；不存在路径 / 行号越界 / 同名多文件三种坏样本都被判失败；围栏内放过、围栏外同款抓住'
  else
    echo '自检失败：门禁没有按预期判定已知坏输入' >&2
  fi
  return "$rc"
}

main() {
  local selftest=0
  local -a files=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --selftest) selftest=1; shift ;;
      --root)
        if [ $# -lt 2 ]; then usage; fi
        ROOT_DIR="$2"; shift 2 ;;
      -h|--help) usage ;;
      -*) echo "未知参数：$1" >&2; usage ;;
      *) files+=("$1"); shift ;;
    esac
  done

  if [ "$selftest" -eq 1 ]; then
    run_selftest
    return $?
  fi

  if [ "${#files[@]}" -eq 0 ]; then usage; fi
  if [ -z "$ROOT_DIR" ]; then
    ROOT_DIR="$(cd "$(dirname "$SELF")/.." && pwd)"
  fi
  if [ ! -d "$ROOT_DIR" ]; then
    echo "FAIL --root 不是目录：$ROOT_DIR" >&2
    return 2
  fi

  WORK="$(mktemp -d)"
  INDEX="$WORK/files.txt"
  BASEMAP="$WORK/basenames.tsv"
  build_index

  local total=0 ok=0 failed=0 direct=0 shortname=0
  local f hit lineno cite rel spec start end resolved resolved_lines
  for f in "${files[@]}"; do
    if [ ! -f "$f" ]; then
      echo "FAIL 输入不是文件：$f" >&2
      return 2
    fi
    while IFS= read -r hit; do
      lineno="${hit%%:*}"
      cite="${hit#*:}"
      rel="${cite%:*}"
      spec="${cite##*:}"
      start="${spec%%-*}"
      end="${spec#*-}"
      if [ "$end" = "$spec" ]; then end="$start"; fi
      total=$((total + 1))
      if ! resolved="$(resolve "$rel")"; then
        echo "FAIL $f:$lineno 引证「$cite」：$resolved"
        failed=$((failed + 1))
        continue
      fi
      resolved_lines="$(awk 'END {print NR + 0}' "$ROOT_DIR/$resolved")"
      if [ "$start" -lt 1 ] || [ "$end" -lt "$start" ] || [ "$end" -gt "$resolved_lines" ]; then
        echo "FAIL $f:$lineno 引证「$cite」：行号 $spec 越界（$resolved 共 $resolved_lines 行）"
        failed=$((failed + 1))
        continue
      fi
      ok=$((ok + 1))
      if [ "$resolved" = "$rel" ]; then
        direct=$((direct + 1))
      else
        shortname=$((shortname + 1))
      fi
    done < <(mask_fences "$f" | grep -noE -- "$CITE_RE" || true)
  done

  echo "引证 $total（直配 $direct，短名兜底 $shortname）解析成功 $ok 失败 $failed"
  if [ "$failed" -gt 0 ]; then
    return 1
  fi
  return 0
}

main "$@"
