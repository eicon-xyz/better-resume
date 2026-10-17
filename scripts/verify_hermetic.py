#!/usr/bin/env python3
"""测试 hermetic 门禁：用例把运行环境的隐式状态当输入读 -> 命中即红（p15 建议 11 环境半边 / P12）。

为什么存在：AGENTS.md 的「测试必须 hermetic——断言不依赖 shell 里的代理变量/PATH/DB 地址」只是一条
人读规则，P12 两次被干净 shell 抓出来（M6 验收、P32 干净 checkout）。这里把它做成会判定的检查。

判据（命中即红，退出码 1）：
  H1 读一个具体环境变量（os.environ[...] / os.environ.get(...) / os.getenv(...)），键名不是 BR_ 旋钮；
  H2 读 ambient 代理变量（键名含 proxy，或无键名地遍历 os.environ 取 *_proxy）；
  H3 PATH 走进用例：读环境里的 PATH，或 shutil.which(...) 没有 or 兜底（缺工具 -> 静默 skip）；
  H4 本机绝对路径 / home 展开（/root/、/home/<user>/、Path.home()、expanduser()）；
  H5 前端测试读构建期环境（process.env / import.meta.env）。

不判的形状（边界写清，避免假装覆盖）：
  - dict(os.environ) / for key in os.environ：把整份 ambient env 交给子进程、或枚举键名，是测试替身与
    环境清理的必要动作；本门禁判的是「把某个隐式值读出来当输入」的形态。
  - 相对路径（data/、var/）是否指向 gitignored 目录：静态判不出是读还是断言，故不判；fixture 用 tmp_path。
  - 真实 sleep / 真实时钟（建议 11 的时间半边）归 ai_resilience 的注入时钟原语，不在本门禁。
  - 只认双引号的键名（ruff format 已统一双引号；单引号形态的坏样本会在评审里被人看出来，不由本门禁兜）。

用法：
  python3 scripts/verify_hermetic.py             扫测试树
  python3 scripts/verify_hermetic.py --selftest  内置样本自检
退出码：0 干净；1 命中；2 用法或环境错。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TESTS = ROOT / "apps" / "api" / "tests"
WEB_SRC = ROOT / "apps" / "web" / "src"
WEB_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")

# ---- 判据表（唯一真源）----
KNOB_PREFIX = "BR_"
ENV_KEY_READS = (
    re.compile(r"os\.environ\[\s*\"([^\"]+)\""),
    re.compile(r"os\.environ\.get\(\s*\"([^\"]+)\""),
    re.compile(r"os\.getenv\(\s*\"([^\"]+)\""),
)
ANY_ENV_READ = re.compile(r"os\.(environ|getenv)")
PROXY = re.compile(r"proxy", re.IGNORECASE)
WHICH = re.compile(r"(?<![A-Za-z_.])shutil\.which\(")
WHICH_FALLBACK = re.compile(r" or ")
HOST_PATH = re.compile(r"/root/|/home/[a-z]|Path\.home\(\)|expanduser\(")
WEB_ENV = re.compile(r"process\.env|import\.meta\.env")

# 显式豁免清单：每条 = (相对路径, 该行原文去首尾空白)。原文一改即失效、门禁转红。
# 整目录/整文件豁免不存在：命中即红是默认，放过必须点名到行并写理由。
EXEMPTIONS: tuple[tuple[str, str], ...] = (
    (
        # H2：这一行正是 hermetic 防护本身——先清空 ambient 代理变量，再设一个畸形 NO_PROXY 给用例注入。
        "apps/api/tests/llm_gateway/test_openai_compat.py",
        "for name in [key for key in os.environ if key.lower().endswith(\"_proxy\")]:",
    ),
    (
        # H4：PATH 兜底常量（AGENTS.md 记载 uv 装在 ~/.local/bin）；主路径是 shutil.which，不参与断言。
        "apps/api/tests/test_real_layer.py",
        "UV = shutil.which(\"uv\") or \"/root/.local/bin/uv\"",
    ),
)


class ScanError(RuntimeError):
    """扫描根缺失 / 扫描集为空 / 文件读不了：一律非 0，不许静默绿灯。"""


def judgments(line: str) -> list[tuple[str, str]]:
    """判一行；返回 [(判据, 为什么)]，空列表表示这一行干净。"""
    found: list[tuple[str, str]] = []
    key = ""
    for pattern in ENV_KEY_READS:
        match = pattern.search(line)
        if match:
            key = match.group(1)
            break
    if key and not key.startswith(KNOB_PREFIX):
        if key == "PATH":
            found.append(("H3", "读 ambient PATH（" + key + "）"))
        elif PROXY.search(line) or PROXY.search(key):
            found.append(("H2", "读 ambient 代理变量（" + key + "）"))
        else:
            found.append(("H1", "读隐式环境变量（" + key + "）"))
    elif not key and ANY_ENV_READ.search(line) and PROXY.search(line):
        found.append(("H2", "遍历 ambient 代理变量（无键名地读环境）"))
    if WHICH.search(line) and not WHICH_FALLBACK.search(line):
        found.append(("H3", "shutil.which 无兜底：缺工具时用例只会静默 skip"))
    if HOST_PATH.search(line):
        found.append(("H4", "本机绝对路径 / home 展开"))
    if WEB_ENV.search(line):
        found.append(("H5", "读构建期环境（process.env / import.meta.env）"))
    return found


def collect() -> list[Path]:
    for directory in (API_TESTS, WEB_SRC):
        if not directory.is_dir():
            raise ScanError("扫描根缺失：" + str(directory) + "（拒绝静默缩小扫描集）")
    files = sorted(path for path in API_TESTS.rglob("*.py") if path.is_file())
    files += sorted(
        path
        for path in WEB_SRC.rglob("*")
        if path.is_file() and path.name.endswith(WEB_SUFFIXES)
    )
    if not files:
        raise ScanError("扫描集为空（拒绝静默绿灯）")
    return files


def scan(files: list[Path], root: Path) -> tuple[list[str], int]:
    """扫一批文件；返回 (HIT 明细行, 被豁免的命中数)。"""
    hits: list[str] = []
    exempted = 0
    resolved_root = root.resolve()
    for path in files:
        relative = path.resolve().relative_to(resolved_root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise ScanError("读不了 " + relative + "：" + str(exc)) from exc
        for number, line in enumerate(lines, start=1):
            stripped = line.strip()
            for rule, why in judgments(line):
                if (relative, stripped) in EXEMPTIONS:
                    exempted += 1
                    continue
                hits.append(
                    "HIT [" + rule + "] " + relative + ":" + str(number) + " " + why
                    + chr(10) + "    原文：" + stripped
                )
    return hits, exempted


def run_selftest() -> int:
    """已知坏样本必红、允许形状必绿、豁免按原文精确匹配、变一个字符即失效。"""
    work = Path(tempfile.mkdtemp(prefix="verify_hermetic_"))
    failures = 0
    checks = 0
    try:
        clean = work / "clean"
        mutated = work / "mutated"
        (clean / "apps" / "api" / "tests" / "llm_gateway").mkdir(parents=True)
        (mutated / "apps" / "api" / "tests").mkdir(parents=True)

        # 逐条断言「这一行只报这一条判据」：删掉/改坏任一判据，对应样本立刻 0 命中，自检失败。
        cases: list[tuple[str, str, set[str]]] = [
            ("H1", "TOKEN = os.getenv(\"DEEPSEEK_TOKEN\")", {"H1"}),
            ("H2 键名", "PROXY = os.environ[\"HTTPS_PROXY\"]", {"H2"}),
            ("H2 遍历", "for name in [key for key in os.environ if key.lower().endswith(\"_proxy\")]:", {"H2"}),
            ("H3 PATH", "BIN = os.environ[\"PATH\"]", {"H3"}),
            ("H3 which 无兜底", "DOCKER = shutil.which(\"docker\")", {"H3"}),
            ("H4 home", "CACHE = Path.home() / \".cache\"", {"H4"}),
            ("H5 构建期环境", "const base = process.env.VITE_API_BASE;", {"H5"}),
        ]
        for name, line, expected in cases:
            checks += 1
            got = {rule for rule, _ in judgments(line)}
            if got == expected:
                print("ok   [必红] " + name + "：命中 " + ",".join(sorted(got)))
            else:
                print(
                    "FAIL [必红] " + name + "：期望 " + ",".join(sorted(expected))
                    + "，实得 " + (",".join(sorted(got)) if got else "0 命中（判据被删或改坏）"),
                    file=sys.stderr,
                )
                failures += 1

        allowed = [
            "previous = os.environ.get(\"BR_DATABASE_URL\")  # BR_ 旋钮：AGENTS.md 指定的测试入参",
            "merged = dict(os.environ)  # 整份 ambient env 交给子进程",
            "BASH = shutil.which(\"bash\") or \"/bin/bash\"  # which 带兜底",
            "assert json_path.endswith(\"var/evidence/soak-60m.json\")  # 断言命令文本，不读本机文件",
            "env = {\"VERIFY_ENV_FILE\": \"/nonexistent/.env\"}  # 本机不存在的显式路径",
        ]
        checks += 1
        flagged = [line for line in allowed if judgments(line)]
        if not flagged:
            print("ok   [必绿] 允许形状 " + str(len(allowed)) + " 行：0 命中")
        else:
            print("FAIL [必绿] 允许形状被误伤：" + repr(flagged), file=sys.stderr)
            failures += 1

        exempt_files = sorted({relative for relative, _ in EXEMPTIONS})
        for relative in exempt_files:
            source = ROOT / relative
            if not source.is_file():
                print("FAIL [必绿] 豁免清单指的文件不存在：" + relative, file=sys.stderr)
                failures += 1
                continue
            target = clean / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        checks += 1
        clean_hits, clean_exempted = scan([clean / relative for relative in exempt_files], clean)
        if not clean_hits and clean_exempted == len(EXEMPTIONS):
            print("ok   [必绿] 豁免清单 " + str(len(EXEMPTIONS)) + " 条按原文精确命中并放过")
        else:
            print(
                "FAIL [必绿] 豁免：命中 " + str(len(clean_hits)) + " 处、豁免 " + str(clean_exempted)
                + " 处（应为 0 与 " + str(len(EXEMPTIONS)) + "）；豁免只认原文精确匹配",
                file=sys.stderr,
            )
            for hit in clean_hits:
                print("      " + hit, file=sys.stderr)
            failures += 1

        marker = "\"/root/.local/bin/uv\""
        mutated_relative = "apps/api/tests/test_real_layer.py"
        checks += 1
        source_text = (ROOT / mutated_relative).read_text(encoding="utf-8")
        if marker not in source_text:
            print("FAIL [必红] 变异样本锚点不在了：" + marker, file=sys.stderr)
            failures += 1
        else:
            mutated_text = source_text.replace(marker, "\"/root/.local/bin/uv2\"")
            mutated_file = mutated / mutated_relative
            mutated_file.write_text(mutated_text, encoding="utf-8")
            mutated_hits, _ = scan([mutated_file], mutated)
            if len(mutated_hits) == 1 and "[H4]" in mutated_hits[0]:
                print("ok   [必红] 豁免按原文匹配：改一个字符即失效（1 命中）")
            else:
                print(
                    "FAIL [必红] 改一个字符后豁免仍生效：命中 " + str(len(mutated_hits)) + " 处",
                    file=sys.stderr,
                )
                failures += 1
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("自检失败：" + str(failures) + " 个用例不符预期", file=sys.stderr)
        return 1
    print("自检通过：" + str(checks) + "/" + str(checks) + " 个用例符合预期")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="测试 hermetic 门禁（隐式环境依赖命中即红）")
    parser.add_argument("--selftest", action="store_true", help="内置样本自检")
    args = parser.parse_args(argv)
    if args.selftest:
        return run_selftest()
    try:
        files = collect()
        hits, exempted = scan(files, ROOT)
    except ScanError as exc:
        print("verify_hermetic: " + str(exc), file=sys.stderr)
        return 2
    if hits:
        for hit in hits:
            print(hit)
        print(
            "verify_hermetic: 命中 " + str(len(hits)) + " 处隐式环境依赖；判据见脚本顶部。",
            "确属必要请进 EXEMPTIONS（按原文精确匹配 + 写清为什么），不要放宽判据。",
            file=sys.stderr,
        )
        return 1
    print(
        "扫描 " + str(len(files)) + " 个测试文件，命中 0 处；豁免 " + str(exempted) + " 处（脚本内清单）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
