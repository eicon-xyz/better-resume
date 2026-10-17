#!/usr/bin/env bash
# 凭据泄漏门禁：判定「会被提交的文件里出现了凭据形状的字面量」。
#
# 为什么存在（p15 F04 / pitfalls P09）：AGENTS.md 的「真机凭据只进 gitignored .env」只是一条人读规则，
# 规则写在文档里不会让任何事红；这里把它做成会红的检查——命中就非 0，不命中才 0。
#
# 用法：
#   bash scripts/verify_secrets.sh             扫仓库
#   bash scripts/verify_secrets.sh --selftest  内置假样本自检（坏样本必须命中、阴性样本必须放过）
#
# 退出码：0 干净；1 命中（点名 文件:行号）；2 用法或环境错。
#
# 扫描范围 = git ls-files --cached --others --exclude-standard，即「会被提交的文件」。
# .env（AGENTS.md 指定的唯一凭据通道）、var/、node_modules/、.cache/、.pnpm-store/、.venv/、data/
# 都由 .gitignore 排除，按定义不在范围里；票面另点名排除 docs/history_docs/（历史归档）与 *.zstd（打包产物）。
#
# 一份实现：PATTERNS 是唯一真源，自检与仓库扫描共用同一个 scan_to；命中行只打印「文件:行号 + [已打码]」，
# 门禁把凭据原文抄进 CI 日志等于把泄漏二次外泄。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# 文件清单是相对仓库根的路径（git ls-files 的输出），grep 必须在仓库根跑：否则从别的目录调用时
# 每个路径都解析不到，命中被 2>/dev/null 吞掉，门禁会静默假绿（已实测）。
cd "$ROOT"

# 唯一真源：每一条都写清抓什么、以及为什么不误伤本仓库既有文本。
PATTERNS=(
  # PEM 私钥块的头行。
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
  # OpenAI / DashScope / DeepSeek 形密钥（含 sk-ws- 前缀）：要求 sk- 之后至少 21 个 [A-Za-z0-9-] 并以字母数字收尾，
  # 于是打码文本 sk-ws-<已打码> 与 OpenSSH 的 sk-ecdsa-sha2-nistp256（恰好 20 个字符）都不够长。
  'sk-[A-Za-z0-9-]{20,}[A-Za-z0-9]'
  # 云厂商固定前缀令牌。
  'AKIA[0-9A-Z]{16}'
  'gh[pousr]_[A-Za-z0-9]{36}'
  'AIza[0-9A-Za-z_-]{35}'
  # 讯飞 app_id / api_secret：值必须是纯十六进制字面量且 >=8 位；名字写大小写两种（env 里是 XUNFEI_APP_ID）。
  # 空值（.env.example 只写变量名）、打码文本 <已打码>、标识符 settings.xunfei_app_id 都不命中。
  '([Aa][Pp][Pp][_-]?[Ii][Dd]|[Aa][Pp][Ii][_-]?[Ss][Ee][Cc][Rr][Ee][Tt])[[:space:]]*[:=][[:space:]]*["'"'"']?[0-9a-fA-F]{8,}'
)
# ponytail: 只认高置信度的凭据形状；「任意 *_KEY 名 + 长值」这类高熵规则会在
# API_KEY_ENV = "BR_DASHSCOPE_API_KEY" 这种合法文本上误伤（实测 4 处），等真出现被漏掉的形状再补一条。

# 一条 grep 拿全部模式：模式只有这一份，自检与仓库扫描都走 scan_to。
PATTERN_ARGS=()
for pattern in "${PATTERNS[@]}"; do PATTERN_ARGS+=(-e "$pattern"); done

CLEANUP=()
cleanup() {
  local path
  if (( ${#CLEANUP[@]} > 0 )); then
    for path in "${CLEANUP[@]}"; do rm -rf -- "$path"; done
  fi
}
trap cleanup EXIT

# 命中行只留 文件:行号。代价：路径里若含冒号会错位，本仓库没有这种路径。
mask_hits() { awk -F: '{ print $1 ":" $2 ": [已打码]" }'; }

# scan_to <命中明细文件>：stdin 是 NUL 分隔的文件路径清单，命中写进明细文件（已打码）。
scan_to() {
  local sink="$1"
  : > "$sink"
  # -H：只有一个文件时 grep 默认不印文件名，而判定要求点名 文件:行号，故强制带名；
  # -r：空清单时不运行 grep；-I：跳过二进制；grep 无命中时 xargs 返回 123，这里兜底。
  xargs -0r grep -IHnE "${PATTERN_ARGS[@]}" 2>/dev/null | mask_hits > "$sink" || true
}

# repo_paths：票面范围，NUL 分隔（路径里的空格不会被拆开）。
repo_paths() {
  git -C "$ROOT" ls-files --cached --others --exclude-standard -z \
    | { grep -zvE '^docs/history_docs/|[.]zstd$' || true; }
}

# repo_scan <命中明细文件>：stdout 是读数行（repo=clean / repo=dirty），命中明细走 stderr。
repo_scan() {
  local sink="$1" list files hits
  command -v git >/dev/null 2>&1 || { echo 'FAIL: git 不在 PATH（扫描范围由 git ls-files 定义）' >&2; return 2; }
  git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1 || { echo "FAIL: $ROOT 不是 git 检出" >&2; return 2; }
  list="$(mktemp)"; CLEANUP+=("$list")
  repo_paths > "$list"
  files="$(grep -zc '' "$list" || true)"
  if (( files == 0 )); then
    echo 'FAIL: 扫描范围是 0 个文件——范围取的是 git 检出，环境不对时不许假绿' >&2
    return 2
  fi
  scan_to "$sink" < "$list"
  hits="$(wc -l < "$sink")"
  if (( hits > 0 )); then
    cat "$sink" >&2
    echo "repo=dirty ($hits hits in $files files: 见上 文件:行号，内容已打码)"
    return 1
  fi
  echo "repo=clean (0 hits in $files files)"
  return 0
}

# ---- --selftest 的内嵌样本：全部是编造值，且坏样本的值由 printf 现场生成，
# 脚本正文里不留凭据形状的字面量（否则门禁会命中自己）。每类被认的形状各一条：
# 删掉 PATTERNS 里任一条，1/3 就必须红。
write_bad_sample() {
  {
    echo '# selftest 假样本（编造值）'
    echo 'BR_DEEPSEEK_API_KEY='$(printf 'sk-%032d' 0)
    echo 'AWS_ACCESS_KEY_ID=AKIA'$(printf '%016d' 0)
    echo 'GITHUB_TOKEN=ghp_'$(printf '%036d' 0)
    echo 'GOOGLE_API_KEY=AIza'$(printf '%035d' 0)
    echo 'xf_app_id='$(printf '%016d' 0)
    echo 'XF_API_SECRET='$(printf '%032x' 0)
    # 带引号的值也要认（配置里是 xunfei_api_secret = "…" 的形状）
    echo 'xf_api_secret = "'$(printf '%016d' 0)'"'
    # 拆成两段：脚本正文里不出现 PEM 头那种连续字面量，否则门禁会命中自己
    echo '-----BEGIN' 'PRIVATE KEY-----'
  } > "$1"
}

write_good_sample() {
  cat > "$1" <<'SAMPLE'
BR_DASHSCOPE_API_KEY=
# BR_SMOKE_KEY=smoke-fake-key
BR_DATABASE_URL=postgresql+asyncpg://better_resume:better_resume@localhost:5432/better_resume
API-KEY:<已打码>
sk-ws-<已打码>
ark-<已打码>
APP_ID：<已打码>
sk-ecdsa-sha2-nistp256@openssh.com
xf_app_id = settings.xunfei_app_id
SAMPLE
}

selftest() {
  local dir sink hits rc repo_rc
  dir="$(mktemp -d)"; CLEANUP+=("$dir")
  mkdir -p "$dir/bad" "$dir/good"
  write_bad_sample "$dir/bad/sample.env"
  write_good_sample "$dir/good/sample.env"
  rc=0

  echo 'selftest 1/3: 坏样本每一行都必须命中（命中数 == 样本非注释行数）'
  sink="$(mktemp)"; CLEANUP+=("$sink")
  find "$dir/bad" -type f -print0 | scan_to "$sink"
  hits="$(wc -l < "$sink")"
  # 期望值从样本自己来：删掉/改坏 PATTERNS 里任一条，或样本行没被认出来，这里就不相等。
  expected="$(grep -c '^[^#]' "$dir/bad/sample.env" || true)"
  cat "$sink"
  if (( hits != expected )); then
    echo "bad=missed ($hits/$expected hits: 有模式被删或被改，或样本行没被认出来)" >&2
    rc=1
  else
    echo "bad=detected ($hits/$expected hits)"
  fi

  echo 'selftest 2/3: 阴性样本必须放过（空值 / 打码文本 / 标识符）'
  sink="$(mktemp)"; CLEANUP+=("$sink")
  find "$dir/good" -type f -print0 | scan_to "$sink"
  hits="$(wc -l < "$sink")"
  if (( hits > 0 )); then
    cat "$sink" >&2
    echo "good=flagged ($hits hits: 误伤本不该红的文本)" >&2
    rc=1
  else
    echo 'good=clean (0 hits)'
  fi

  echo 'selftest 3/3: 仓库当前必须干净'
  sink="$(mktemp)"; CLEANUP+=("$sink")
  repo_rc=0; repo_scan "$sink" || repo_rc=$?
  (( repo_rc == 0 )) || rc=1

  if (( rc != 0 )); then
    echo 'selftest=FAIL' >&2
    exit 1
  fi
  echo 'selftest=PASS'
}

usage() {
  awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "$0"
}

# repo_main <命中明细文件>：默认模式就是「扫仓库 + 以退出码判定」。
repo_main() {
  local sink="$1" rc
  rc=0; repo_scan "$sink" || rc=$?
  return "$rc"
}

main_sink="$(mktemp)"; CLEANUP+=("$main_sink")
case "${1:-}" in
  '') repo_main "$main_sink" ;;
  --selftest) selftest ;;
  -h|--help) usage; exit 0 ;;
  *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
esac
