#!/usr/bin/env python3
"""P14 网页样式守卫：把 docs/tickets/p14-web-redesign 的样式条款做成会红的机器闸门（守卫①–⑤）。

脚本报告行里的编号就是条款号：

  G1  token 引用可解析、深浅主题成对。CSS 树里每个 var(--br-...) 都必须指向树中真实定义过的
      变量——典型漂移是 var(--br-text-muted, #666)：兜底色让页面照常渲染，而 token 从未存在。
      主题依赖的变量（--br-color-* / --br-gradient-* / --br-shadow-*）在 :root 定义后，还必须在
      prefers-color-scheme: dark 块里重述，避免新 token 只服务浅色。
  G2  token 源之外的页面 CSS 不得出现裸 hex/px/rgb/hsl 字面量。只有 /* allow: <理由> */ 写在
      字面量上一行时才放行，白名单留在文件里可审计，而不是藏在脚本里。
  G3  CSS 树至少声明一条宽度断点，让分栏布局在窄屏有塌缩形态，而不是只服务桌面。
  G4  每处 animation / transition 动效都在同一文件的 prefers-reduced-motion 下被同选择器重访。
  G5  页面不得直接打开原生 <select / <input / <table 标签；原生元素由样式化组件持有，绕过即失去
      共享样式。

用法：python3 scripts/check_web_style_guards.py [--root apps/web/src]
退出码：0 干净，1 有违规，2 调用错误。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT / "apps" / "web" / "src"
TOKEN_SOURCE = "styles/tokens.css"

COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
VAR_USE_RE = re.compile(r"var\(\s*(--br-[A-Za-z0-9_-]+)")
VAR_DEF_RE = re.compile(r"(--br-[A-Za-z0-9_-]+)\s*:")
# 主题依赖的 token：取值必须为深色主题重述而不是继承——这就是“深浅双定义”。
THEME_PREFIXES = ("--br-color-", "--br-gradient-", "--br-shadow-")
DARK_PRELUDE_RE = re.compile(r"prefers-color-scheme\s*:\s*dark")
ROOT_SELECTOR_RE = re.compile(r":root\b")
HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
PX_RE = re.compile(r"\b\d*\.?\d+px\b")
COLOR_FN_RE = re.compile(r"\b(?:rgba?|hsla?)\(")
ALLOW_RE = re.compile(r"/\*\s*allow:\s*\S.*?\*/")
MOTION_DECL_RE = re.compile(r"(?:^|[;{])\s*((?:animation|transition)[a-z-]*)\s*:\s*([^;{}]*)", re.MULTILINE)
REDUCED_PRELUDE_RE = re.compile(r"prefers-reduced-motion\s*:\s*reduce")
WIDTH_MEDIA_RE = re.compile(r"\(\s*(?:min|max)-width\s*:")
RAW_CONTROL_RE = re.compile(r"<\s*(select|input|table)\b")


class Block:
    """一对“<前言> { <主体> }”，主体带它在去注释源码中的偏移量。"""

    def __init__(self, prelude: str, body: str, body_start: int) -> None:
        self.prelude = prelude
        self.body = body
        self.body_start = body_start


def parse_blocks(source: str) -> list[Block]:
    """任意嵌套深度上的花括号块；前言取上一个 ';'、'{' 或 '}' 之后的文本。"""
    blocks: list[Block] = []
    prelude_start = 0
    stack: list[tuple[str, int]] = []  # (前言, 主体起点)
    for index, char in enumerate(source):
        if char == "{":
            stack.append((source[prelude_start:index], index + 1))
            prelude_start = index + 1
        elif char == "}":
            if stack:
                prelude, body_start = stack.pop()
                blocks.append(Block(prelude, source[body_start:index], body_start))
            prelude_start = index + 1
        elif char == ";":
            prelude_start = index + 1
    return blocks


def strip_comments(source: str) -> str:
    """把注释体涂空但保留换行，让行号不漂移。"""
    return COMMENT_RE.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), source)


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def css_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.css") if path.is_file())


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def guard_undefined_tokens(root: Path, files: list[Path]) -> list[str]:
    defined: set[str] = set()
    uses: list[tuple[Path, int, str]] = []
    for path in files:
        text = strip_comments(path.read_text(encoding="utf-8"))
        defined.update(match.group(1) for match in VAR_DEF_RE.finditer(text))
        uses.extend(
            (path, line_of(text, match.start()), match.group(1))
            for match in VAR_USE_RE.finditer(text)
        )
    problems = []
    for path, line, name in uses:
        if name not in defined:
            problems.append(
                f"{rel(path, root)}:{line}: G1 {name} 被引用但没有定义（守卫① token 零假变量）"
            )
    problems.extend(guard_dark_parity(root, files))
    return problems


def guard_dark_parity(root: Path, files: list[Path]) -> list[str]:
    """G1b：在 :root 定义的主题依赖 token 也必须为深色模式定义。"""
    problems = []
    for path in files:
        text = strip_comments(path.read_text(encoding="utf-8"))
        blocks = parse_blocks(text)
        dark_names = {
            match.group(1)
            for block in blocks
            if DARK_PRELUDE_RE.search(block.prelude)
            for match in VAR_DEF_RE.finditer(block.body)
        }
        for block in blocks:
            if not ROOT_SELECTOR_RE.search(block.prelude) or DARK_PRELUDE_RE.search(block.prelude):
                continue
            for match in VAR_DEF_RE.finditer(block.body):
                name = match.group(1)
                if not name.startswith(THEME_PREFIXES) or name in dark_names:
                    continue
                problems.append(
                    f"{rel(path, root)}:{line_of(text, block.body_start + match.start())}: "
                    f"G1 {name} 深色块缺定义（守卫① 深浅双定义）"
                )
    return problems


def guard_bare_literals(root: Path, files: list[Path]) -> list[str]:
    """G2：token 源之外不得有裸 hex/px/rgb/hsl；字面量上一行的“/* allow: 理由 */”注释放行该行。
    at-rule 前言行不在范围内：断点宽度是结构性输入（守卫 G3 要求它），不是从 token 集漂移的值。"""
    problems = []
    for path in files:
        if rel(path, root) == TOKEN_SOURCE:
            continue
        raw = path.read_text(encoding="utf-8")
        stripped_lines = strip_comments(raw).splitlines()
        raw_lines = raw.splitlines()
        for index, line in enumerate(stripped_lines):
            if line.lstrip().startswith("@"):
                continue
            literals = [
                match.group(0)
                for regex in (HEX_RE, PX_RE, COLOR_FN_RE)
                for match in regex.finditer(line)
            ]
            if not literals:
                continue
            previous = raw_lines[index - 1] if index > 0 else ""
            if ALLOW_RE.search(previous):
                continue
            problems.append(
                f"{rel(path, root)}:{index + 1}: G2 裸值 {', '.join(literals)}"
                f"（守卫② 零裸 hex/px；确需保留请在上一行写 /* allow: 理由 */）"
            )
    return problems


def motion_declarations(body: str) -> list[str]:
    """真正产生动效的声明（animation: none / transition: none 是覆盖，不是动效）。"""
    found = []
    for match in MOTION_DECL_RE.finditer(body):
        property_name, value = match.group(1), match.group(2).strip()
        if property_name in ("animation", "transition") and value == "none":
            continue
        found.append(property_name)
    return found


def selector_parts(prelude: str) -> set[str]:
    return {part.strip() for part in prelude.split(",") if part.strip()}


def guard_reduced_motion(root: Path, files: list[Path]) -> list[str]:
    """G4：每条动效规则都必须在同文件、同选择器下用 prefers-reduced-motion: reduce 重访
    （停掉或减弱都算）。"""
    problems = []
    for path in files:
        text = strip_comments(path.read_text(encoding="utf-8"))
        blocks = parse_blocks(text)
        reduced = [block for block in blocks if REDUCED_PRELUDE_RE.search(block.prelude)]
        covered: list[tuple[str, int]] = []
        for media in reduced:
            for inner in parse_blocks(media.body):
                # 任意 animation / transition 声明都算一次重访——包括刻意写下的
                # animation: none / transition: none，它们会直接停掉动效。
                if MOTION_DECL_RE.search(inner.body):
                    covered.append((inner.prelude, media.body_start + inner.body_start))
        for block in blocks:
            if block.prelude.lstrip().startswith("@") or not motion_declarations(block.body):
                continue
            if any(
                media.body_start <= block.body_start < media.body_start + len(media.body)
                for media in reduced
            ):
                continue  # 这条规则本身就是 reduced-motion 覆盖
            wants = selector_parts(block.prelude)
            if any(wants & selector_parts(prelude) for prelude, _offset in covered):
                continue
            problems.append(
                f"{rel(path, root)}:{line_of(text, block.body_start)}: "
                f"G4 {block.prelude.strip()} 的动画没有 prefers-reduced-motion 处理（守卫④）"
            )
    return problems


def guard_width_breakpoint(root: Path, files: list[Path]) -> list[str]:
    """G3：CSS 树里至少存在一条宽度媒体查询。条款是整棵树级而非逐文件：
    分栏布局要有窄屏形态。"""
    for path in files:
        text = strip_comments(path.read_text(encoding="utf-8"))
        for block in parse_blocks(text):
            if block.prelude.lstrip().startswith("@") and WIDTH_MEDIA_RE.search(block.prelude):
                return []
    return ["G3 全 CSS 树没有宽度断点（至少一条 min-width / max-width 媒体查询）（守卫③）"]


def guard_raw_page_controls(root: Path) -> list[str]:
    """G5：pages/**/*.tsx（排除测试文件）不得打开原生控件标签。样式化组件在 components/ 下，
    刻意不扫描——持有原生元素正是它们的职责。"""
    pages = root / "pages"
    if not pages.is_dir():
        return []
    problems = []
    for path in sorted(pages.rglob("*.tsx")):
        if path.name.endswith(".test.tsx"):
            continue
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            match = RAW_CONTROL_RE.search(line)
            if match:
                problems.append(
                    f"{rel(path, root)}:{index + 1}: G5 页面直接使用原生 <{match.group(1)}> 标签，"
                    f"请改用样式化组件（守卫⑤）"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="web 样式守卫（守卫①–⑤）")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="CSS 树根目录")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"no such root: {root}", file=sys.stderr)
        return 2

    files = css_files(root)
    problems = guard_undefined_tokens(root, files)
    problems.extend(guard_bare_literals(root, files))
    problems.extend(guard_width_breakpoint(root, files))
    problems.extend(guard_reduced_motion(root, files))
    problems.extend(guard_raw_page_controls(root))
    for problem in problems:
        print(problem)
    if problems:
        print(f"check_web_style_guards: {len(problems)} violation(s)")
        return 1
    print(f"check_web_style_guards: ok ({len(files)} css file(s) under {root})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
