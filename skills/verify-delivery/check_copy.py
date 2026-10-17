#!/usr/bin/env python3
"""交付文案的机械判据（verify-delivery 技能的 helper）。

为什么存在：交付文案的返工（F08/F10/F16）过去只在对话里逐条口头打回——没有可引用的口径，
每个窗口都要重新被纠正一遍。这份 helper 把能机械判的部分钉住，判据表就是唯一真源，
skills/verify-delivery/SKILL.md 只写怎么用、不抄第二份。

用法：
  python3 skills/verify-delivery/check_copy.py <文件>                      默认 --kind cv
  python3 skills/verify-delivery/check_copy.py <文件> --kind changelog
  python3 skills/verify-delivery/check_copy.py --selftest
退出码：0 全部合规；1 命中（点名 行号 + 判据 + 原文）；2 用法错。

判据：
  C1 中文（F10）：一行里 >=3 个西文词且不在 ALLOWED_TERMS -> 写成中文句子，专业名词保留原文；
      只判 cv：改动说明里的路径与命令是合法的西文。
  C2 AI 味（F08）：命中 FLAVOR_WORDS（空口号 / 程度堆砌）-> 改写成具体动作；
  C3 括号（F08）：全角括号注释 -> 把解释写成第二句；
  C4 量化无数字（F08）：命中 QUANT_WORDS 但整行没有数字 -> 有数据摆数据，没有不凑；
  C5 缺手段（F08）：交付条目没有动作动词 -> 说清「用什么解决了什么问题」；
  G1 改动说明（F16）：缺 改动 / 影响面 / 未验证 / 证据 四栏；
  G2 引证（F16）：改动栏没有「文件:行号」引证。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---- 判据表（唯一真源）----
# AI 味词表：空口号与程度堆砌，它们不携带信息。加词必须同时能在 --selftest 里被认出来。
FLAVOR_WORDS = (
    "赋能",
    "助力",
    "极致",
    "一站式",
    "全方位",
    "多维度",
    "闭环",
    "生态",
    "无缝",
    "引领",
    "拥抱",
    "打造",
    "深耕",
    "加持",
    "焕新",
    "强强联合",
    "智能化",
    "显著提升",
    "大幅提升",
    "极大提升",
    "完美解决",
)
# 专业名词白名单：这些词保留原文，不算「西文成句」。
ALLOWED_TERMS = {
    "api",
    "ci",
    "llm",
    "asr",
    "tts",
    "sse",
    "ws",
    "http",
    "https",
    "json",
    "html",
    "css",
    "sql",
    "yaml",
    "toml",
    "openapi",
    "redis",
    "postgres",
    "postgresql",
    "docker",
    "compose",
    "nginx",
    "github",
    "pr",
    "uuid",
    "ttl",
    "react",
    "vite",
    "fastapi",
    "python",
    "typescript",
    "pytest",
    "ruff",
    "eslint",
    "vitest",
    "mock",
    "db",
    "url",
    "id",
    "jwt",
    "cookie",
    "session",
    "stream",
    "queue",
    "worker",
    "p95",
    "p99",
}
QUANT_WORDS = ("提升", "提高", "优化", "降低", "减少", "缩短", "加速", "提速")
MEANS_VERBS = (
    "引入",
    "接入",
    "改写",
    "重写",
    "重构",
    "拆分",
    "抽出",
    "替换",
    "设计",
    "实现",
    "修正",
    "改成",
    "降级",
    "合并",
    "加上",
    "落成",
)
FIELDS = (
    ("改动", "改动："),
    ("影响面", "影响面："),
    ("未验证", "未验证："),
    ("证据", "证据："),
)
KINDS = ("cv", "changelog")

ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]*")
CITATION = re.compile(
    r"[A-Za-z0-9_./-]+\.(py|ts|tsx|js|jsx|md|json|sh|yaml|yml|sql|css|html|toml):[0-9]+(-[0-9]+)?"
)
DIGIT = re.compile(r"[0-9]")
CV_MARKER = re.compile(r"^\s*(?:[-*]|[0-9]+[.)])\s+")


def line_findings(line: str, kind: str) -> list[tuple[str, str]]:
    """判一行；返回 [(判据, 为什么)]，空列表表示这一行干净。"""
    found: list[tuple[str, str]] = []
    if kind == "cv":
        words = [word for word in ASCII_WORD.findall(line) if word.lower() not in ALLOWED_TERMS]
        if len(words) >= 3:
            found.append(("C1", "西文成句 / 术语成串：" + " ".join(words[:5])))
    for word in FLAVOR_WORDS:
        if word in line:
            found.append(("C2", "AI 味词「" + word + "」"))
    if kind == "cv":
        if "（" in line or "）" in line:
            found.append(("C3", "括号注释：把解释写成第二句"))
        if any(word in line for word in QUANT_WORDS) and not DIGIT.search(line):
            found.append(("C4", "量化词没有数字：没有数据就不写量化"))
        body = CV_MARKER.sub("", line).strip()
        if len(body) >= 8 and not any(verb in body for verb in MEANS_VERBS):
            found.append(("C5", "没写清用什么：缺动作动词"))
    return found


def file_findings(text: str, kind: str) -> list[tuple[int, str, str]]:
    """整份文件级的判据；返回 [(行号, 判据, 为什么)]，行号 0 表示不指向具体行。"""
    found: list[tuple[int, str, str]] = []
    if kind != "changelog":
        return found
    missing = [label for label, token in FIELDS if token not in text]
    if missing:
        found.append((0, "G1", "改动说明缺栏：" + "、".join(missing)))
    change_lines = [
        (number, line)
        for number, line in enumerate(text.splitlines(), start=1)
        if "改动：" in line
    ]
    if change_lines and not any(CITATION.search(line) for _, line in change_lines):
        found.append((change_lines[0][0], "G2", "改动栏没有 文件:行号 引证"))
    return found


def check_text(text: str, kind: str, where: str) -> tuple[list[str], int]:
    """返回 (HIT 明细行, 命中数)。"""
    hits: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for rule, why in line_findings(line, kind):
            hits.append(
                "HIT [" + rule + "] " + where + ":" + str(number) + " " + why
                + chr(10) + "    原文：" + line.strip()
            )
    for number, rule, why in file_findings(text, kind):
        location = where + (":" + str(number) if number else "")
        hits.append("HIT [" + rule + "] " + location + " " + why)
    return hits, len(hits)


def run_selftest() -> int:
    """词表不空转、每条判据都有会红的样本、合规样本必绿。"""
    failures = 0
    checks = 0

    def report(ok: bool, name: str, detail: str = "") -> None:
        nonlocal failures, checks
        checks += 1
        if ok:
            print("ok   " + name)
        else:
            print("FAIL " + name + ("：" + detail if detail else ""), file=sys.stderr)
            failures += 1

    report(len(FLAVOR_WORDS) > 0 and len(MEANS_VERBS) > 0 and len(QUANT_WORDS) > 0, "判据表非空")
    missed = [word for word in FLAVOR_WORDS if not any(r == "C2" for r, _ in line_findings(word, "cv"))]
    report(not missed, "词表每条都真的会被认出来", "漏认：" + "、".join(missed))

    bad_cv = chr(10).join(
        [
            "- 赋能业务闭环，打造一站式面试平台",
            "- 优化系统性能（响应更快）",
            "- 重构 interview_engine 与 QuestionService 的读写路径，修正 restore 写库",
        ]
    )
    bad_rules = {rule for line in bad_cv.splitlines() for rule, _ in line_findings(line, "cv")}
    expected_cv = {"C1", "C2", "C3", "C4", "C5"}
    report(
        bad_rules == expected_cv,
        "必红：cv 坏样本命中 C1-C5",
        "实得 " + (",".join(sorted(bad_rules)) if bad_rules else "0 命中"),
    )

    good_cv = chr(10).join(
        [
            "- 引入 Redis Stream 队列，把出题耗时从 3.2s 降到 0.8s",
            "- 拆分 interview_engine 的读写路径，restore 不再写库",
        ]
    )
    good_hits, _ = check_text(good_cv, "cv", "good-cv")
    report(not good_hits, "必绿：合规 cv 样本 0 命中", "；".join(good_hits))

    bad_changelog = chr(10).join(
        [
            "改动：引入 Redis Stream 队列，出题耗时从 3.2s 降到 0.8s",
            "证据：python3 scripts/verify_hermetic.py -> 命中 0 处",
        ]
    )
    changelog_hits, _ = check_text(bad_changelog, "changelog", "bad-changelog")
    changelog_rules = {hit.split()[1].strip("[]") for hit in changelog_hits if hit.startswith("HIT [")}
    report(
        changelog_rules == {"G1", "G2"},
        "必红：改动说明坏样本命中 G1+G2",
        "实得 " + (",".join(sorted(changelog_rules)) if changelog_rules else "0 命中"),
    )

    good_changelog = chr(10).join(
        [
            "改动：拆分 apps/api/src/better_resume/interview_engine/restore.py:41-58 的读写路径，restore 不再写库",
            "影响面：无",
            "未验证：并发 restore 未压测",
            "证据：uv run pytest tests/interview_engine -q -> 42 passed",
        ]
    )
    good_changelog_hits, _ = check_text(good_changelog, "changelog", "good-changelog")
    report(
        not good_changelog_hits,
        "必绿：合规改动说明 0 命中",
        "；".join(good_changelog_hits),
    )

    if failures:
        print("自检失败：" + str(failures) + "/" + str(checks) + " 个用例不符预期", file=sys.stderr)
        return 1
    print("自检通过：" + str(checks) + "/" + str(checks) + " 个用例符合预期")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="交付文案的机械判据（judgments 见脚本顶部）")
    parser.add_argument("target", nargs="?", help="被检查的文本文件")
    parser.add_argument("--kind", choices=KINDS, default="cv", help="cv=简历/交付文案（默认），changelog=改动说明")
    parser.add_argument("--selftest", action="store_true", help="内置样本自检")
    args = parser.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not args.target:
        parser.error("缺少被检查的文件（或用 --selftest）")
    path = Path(args.target)
    if not path.is_file():
        print("check_copy: 不是文件：" + args.target, file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    hits, count = check_text(text, args.kind, args.target)
    if hits:
        for hit in hits:
            print(hit)
        print(
            "check_copy: 命中 " + str(count) + " 处（kind=" + args.kind + "）；判据见脚本顶部，",
            "写作用法见 skills/verify-delivery/SKILL.md。",
            file=sys.stderr,
        )
        return 1
    print("check_copy: 0 命中（kind=" + args.kind + "，" + args.target + "）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
