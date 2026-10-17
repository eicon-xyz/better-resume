"""P14 网页样式守卫脚本的测试：它是守卫条款背后的机器闸门。

守卫条款（脚本报告行里的编号就是条款号）：
  G1  token 引用必须可解析——被引用的 --br-* 不得无定义；主题依赖 token
      （--br-color-* / --br-gradient-* / --br-shadow-*）必须有深色定义，不能只写浅色 :root；
  G2  token 源之外的页面 CSS 不得出现裸 hex/px/rgb/hsl 字面量；只有写在字面量上一行的
      /* allow: <理由> */ 注释才放行；
  G3  站点至少有一条宽度断点；
  G4  每处动画与过渡都在 prefers-reduced-motion 下处理；
  G5  页面使用样式化控件，而不是裸 select/input/table。

本文件把脚本当 CLI 对构造的输入树测试（票据约定的缝），另加一次对真实树的运行：
没人跑的守卫会撒谎。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GUARDS = REPO_ROOT / "scripts" / "check_web_style_guards.py"


def run_guards(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 固定 argv，这是测试夹具
        [sys.executable, str(GUARDS), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_clean_tokens(root: Path) -> Path:
    """满足 G1 与 G3 的 token 源：主题依赖名深浅成对，并带一条页面布局可依赖的宽度断点。"""
    return write(
        root,
        "styles/tokens.css",
        ":root { --br-color-bg: #ffffff; --br-color-accent: #2f6feb; }\n"
        "@media (prefers-color-scheme: dark) {\n"
        "  :root { --br-color-bg: #0f1115; --br-color-accent: #6d9bff; }\n"
        "}\n"
        "@media (min-width: 1024px) {\n"
        "  :root { --br-space-1: 4px; }\n"
        "}\n",
    )


def test_a_referenced_but_undefined_token_is_reported(tmp_path: Path) -> None:
    """G1：var(--br-x, fallback) 正是假变量藏身的方式——兜底色让页面照常渲染，
    而变量其实并不存在。"""
    write(tmp_path, "styles/tokens.css", ":root { --br-color-bg: #ffffff; }\n")
    write(tmp_path, "pages/X.module.css", ".a { color: var(--br-text-ghost, #666666); }\n")

    result = run_guards("--root", str(tmp_path))

    assert result.returncode != 0, result.stdout
    assert "G1" in result.stdout
    assert "--br-text-ghost" in result.stdout
    assert "X.module.css" in result.stdout


def test_a_theme_token_defined_only_for_light_mode_is_reported(tmp_path: Path) -> None:
    """G1b：只在浅色 :root 存在的颜色 token 会悄悄漂进深色主题，
    那里每个消费点都退回浏览器默认值。深浅两套都必须声明它。"""
    write(tmp_path, "styles/tokens.css", ":root { --br-color-accent: #2f6feb; }\n")
    write(tmp_path, "pages/X.module.css", ".a { color: var(--br-color-accent); }\n")

    result = run_guards("--root", str(tmp_path))

    assert result.returncode != 0, result.stdout
    assert "G1" in result.stdout
    assert "--br-color-accent" in result.stdout
    assert "深色" in result.stdout


def test_bare_hex_and_px_literals_are_reported(tmp_path: Path) -> None:
    """G2：页面 CSS 里的裸颜色或长度，就是一个从未被抽出来的 token。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/X.module.css",
        ".a {\n  color: #123456;\n  margin: 8px;\n}\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode != 0, result.stdout
    assert "G2" in result.stdout
    assert "#123456" in result.stdout
    assert "8px" in result.stdout
    assert "X.module.css" in result.stdout


def test_an_allow_comment_on_the_line_above_releases_a_literal(tmp_path: Path) -> None:
    """G2：白名单是字面量上一行的注释——就地写理由，
    读文件即可审计，而不是藏在守卫脚本里的清单。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/X.module.css",
        ".a {\n  /* allow: 折叠箭头的三角形几何，不属设计 token */\n  width: 8px;\n}\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode == 0, result.stdout


def test_a_same_line_allow_comment_does_not_release(tmp_path: Path) -> None:
    """G2：放行只认上一行。写在字面量同一行的尾注会让扫左侧的读者看不见漂移，不算放行。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/X.module.css",
        ".a { color: #123456; } /* allow: 想蒙混的同行尾注 */\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode != 0, result.stdout
    assert "G2" in result.stdout
    assert "#123456" in result.stdout


def test_the_real_web_tree_passes_every_guard() -> None:
    """闸门必须在 CI 真正看到的树上全绿——那是守卫存在的意义，
    而不只是夹具里能构造出的状态。"""
    result = run_guards()

    assert result.returncode == 0, result.stdout


def test_an_animation_without_reduced_motion_is_reported(tmp_path: Path) -> None:
    """G4：无限动画是晕动敏感访客唯一无法回避的东西。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/X.module.css",
        ".cursor { animation: blink 1s steps(2, start) infinite; }\n"
        "@keyframes blink { 50% { opacity: 0; } }\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode != 0, result.stdout
    assert "G4" in result.stdout
    assert ".cursor" in result.stdout
    assert "X.module.css" in result.stdout


def test_an_animation_overridden_under_reduced_motion_passes(tmp_path: Path) -> None:
    """G4：覆盖规则可以彻底停掉动画或只是减弱——两者都算处理，
    只要同选择器在媒体查询下被重访。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/X.module.css",
        ".cursor { animation: blink 1s steps(2, start) infinite; }\n"
        "@keyframes blink { 50% { opacity: 0; } }\n"
        "@media (prefers-reduced-motion: reduce) {\n"
        "  .cursor { animation: none; }\n"
        "}\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode == 0, result.stdout


def test_a_tree_without_a_width_breakpoint_is_reported(tmp_path: Path) -> None:
    """G3：站点必须声明至少一条视口断点。没有断点，
    两列布局在窄屏仍保持桌面形态、从不塌缩。"""
    write(
        tmp_path,
        "styles/tokens.css",
        ":root { --br-color-bg: #ffffff; }\n"
        "@media (prefers-color-scheme: dark) {\n"
        "  :root { --br-color-bg: #0f1115; }\n"
        "}\n",
    )
    write(tmp_path, "pages/X.module.css", ".a { color: var(--br-color-bg); }\n")

    result = run_guards("--root", str(tmp_path))

    assert result.returncode != 0, result.stdout
    assert "G3" in result.stdout


def test_raw_select_input_and_table_in_pages_are_reported(tmp_path: Path) -> None:
    """G5：页面伸手拿原生控件就绕过了共享样式，所以 pages/**/*.tsx 里每个裸
    <select / <input / <table 都会被点名文件与行号。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/X.tsx",
        "export function X() {\n"
        "  return (\n"
        "    <form>\n"
        '      <select aria-label="模型" />\n'
        '      <input aria-label="目标" />\n'
        "      <table><tbody /></table>\n"
        "    </form>\n"
        "  );\n"
        "}\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode != 0, result.stdout
    assert "G5" in result.stdout
    assert "pages/X.tsx:4" in result.stdout
    assert "select" in result.stdout
    assert "input" in result.stdout
    assert "table" in result.stdout


def test_styled_controls_in_pages_pass(tmp_path: Path) -> None:
    """G5：样式化组件是大写 JSX，不是裸标签——用它们就是修法。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/Y.tsx",
        'import { Input, Select, Table } from "../components";\n'
        "export function Y() {\n"
        "  return (\n"
        "    <Table>\n"
        '      <Select aria-label="模型" />\n'
        '      <Input aria-label="目标" />\n'
        "    </Table>\n"
        "  );\n"
        "}\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode == 0, result.stdout


def test_page_test_files_are_exempt_from_g5(tmp_path: Path) -> None:
    """G5：夹具与页面测试可以故意写出裸标签；条款管的是浏览器加载的页面，
    所以跳过 *.test.tsx。"""
    write_clean_tokens(tmp_path)
    write(tmp_path, "pages/X.test.tsx", 'const tag = "<select>";\n')

    result = run_guards("--root", str(tmp_path))

    assert result.returncode == 0, result.stdout


def test_component_implementations_are_out_of_scope_for_g5(tmp_path: Path) -> None:
    """G5：样式化控件本身必须渲染原生元素——那是它们的职责，
    所以 components/** 刻意不扫描。"""
    write_clean_tokens(tmp_path)
    write(tmp_path, "components/Select.tsx", "export function Select() { return <select />; }\n")

    result = run_guards("--root", str(tmp_path))

    assert result.returncode == 0, result.stdout


def test_a_transition_without_reduced_motion_is_reported(tmp_path: Path) -> None:
    """G4：过渡同样属于动效，必须有 prefers-reduced-motion 处理。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/X.module.css",
        ".bar { transition: width 200ms ease; }\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode != 0, result.stdout
    assert "G4" in result.stdout
    assert ".bar" in result.stdout
    assert "X.module.css" in result.stdout


def test_a_transition_overridden_under_reduced_motion_passes(tmp_path: Path) -> None:
    """G4：同选择器在 reduced-motion 内以 transition* 重访即算覆盖（含 none）。"""
    write_clean_tokens(tmp_path)
    write(
        tmp_path,
        "pages/X.module.css",
        ".bar { transition: width 200ms ease; }\n"
        "@media (prefers-reduced-motion: reduce) {\n"
        "  .bar { transition: none; }\n"
        "}\n",
    )

    result = run_guards("--root", str(tmp_path))

    assert result.returncode == 0, result.stdout
