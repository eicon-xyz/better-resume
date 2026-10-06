#!/usr/bin/env python3
"""Render docs/audit/units/*.json into one self-contained HTML module-design audit.

Usage: python3 scripts/build_module_audit.py
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNITS = ROOT / "docs" / "audit" / "units"
OUT = ROOT / "docs" / "audit" / "MODULE-AUDIT.html"

# Rendering order and display metadata. Any unit JSON not listed is appended.
UNIT_ORDER = [
    ("settings_observability", "配置与装配", "settings / observability / main"),
    ("http", "HTTP 薄层", "http/"),
    ("identity_jobs", "身份与作业", "identity/ jobs/ worker.py redis_client.py"),
    ("ai_resilience", "韧性链", "ai_resilience/"),
    ("llm_gateway", "模型网关", "llm_gateway/"),
    ("interview_engine", "面试引擎", "interview_engine/"),
    ("conversation_chat", "会话与聊天", "conversation/ chat/"),
    ("media", "语音", "media/"),
    ("resume_parser_db", "简历解析与库", "resume_parser/ db/ migrations/"),
    ("web", "前端", "apps/web/src"),
]

SEVERITY_ORDER = {"高": 0, "中": 1, "低": 2}
SEVERITY_LABEL = {"高": "高", "中": "中", "低": "低"}

# The user's checklist, verbatim, grouped as given.
CHECKLIST = [
    ("设计一个模块时", [
        "先用一句话写清：它做什么、给谁用、最重要的 1~3 件事是什么。",
        "设计两次：造 2~3 个差异明显的接口方案，按「上层易用性 > 接口简单 > 通用性 > 实现效率」打分。",
        "先写接口注释（含错误模式、前置条件、不变量），再写签名，最后才写实现。",
        "问：能不能用更少的通用方法覆盖这些专用方法？",
        "问：这个复杂度应该下沉到模块里，还是推给使用者？",
        "问：我是不是暴露了一个本来可以自动算出来的配置参数？",
        "问：接口注释里有没有调用者不需要知道的实现细节？",
    ]),
    ("拆分还是合并时", [
        "两类是否共享同一份知识（同一个格式/协议/算法）？共享就合并。",
        "拆开后接口是变简单了还是变复杂了？只有更简单才拆。",
        "是否存在重复？（注意：重复的是知识，不是代码长相）。",
        "通用代码和专用代码是否干净地分开了？专用代码该上移到应用层还是下移到驱动层。",
    ]),
    ("写代码时", [
        "命名是否精确 + 一致？想不出好名字就先改设计。",
        "是否消除了特殊情况（空值、边界）而不是加 if 判断。",
        "错误能不能通过定义规避，而不是抛给每个调用者。",
        "注释是否只描述代码中难以理解的内容（意图/为什么/概念框架），而不是复述代码。",
        "多返回值是否用了带具名字段的类而不是 Pair。",
        "代码是否符合周围既有约定。",
    ]),
    ("改代码 / 提交时", [
        "这次改动有没有让设计变好一点（哪怕一处）？",
        "注释是否还在它所描述的代码附近，并且同步更新了？",
        "性能改动前是否测量过、改后是否复测、无改善是否撤销？",
    ]),
    ("评审时", [
        "逐条扫危险信号速查表（见下）。",
        "做删除测试：删掉这个类/方法，调用方是变简单还是变复杂？",
        "说出这个模块重要的 1~3 件事，检查它们有没有出现在接口、命名和高频路径上。",
    ]),
]

SIGNALS = [
    ("浅模块", "接口并不比实现简单多少；文档比代码还长"),
    ("信息泄露", "同一个设计决策出现在多个模块里"),
    ("时间分解", "代码结构跟着执行顺序走，而不是跟着知识走"),
    ("过度暴露", "用常见功能还得先了解罕见功能"),
    ("多类症", "「类是好的，所以类越多越好」，结果一堆小类各自带一个接口"),
    ("透传方法", "除了转调同签名方法什么都不做"),
    ("透传变量", "变量只是路过一串不使用它的方法"),
    ("连体方法", "不理解 A 的实现就无法理解 B 的实现"),
    ("重复", "同一份知识反复出现（不是代码长得像）"),
    ("通用专用混合体", "通用机制和某个调用者的专用逻辑混在一个类里"),
    ("注释重复了代码", "删掉它，读者不损失任何信息"),
    ("实现文档污染接口", "接口注释里写了调用者不需要知道的实现细节"),
    ("模糊的名称", "名字宽泛到无法传递有用信息（data / time / count）"),
    ("难以选取名称", "起不出精确又直观的名字 → 设计有问题"),
    ("难以描述", "要完整描述一个变量/方法，文档必须写很长 → 分解有问题"),
    ("难以理解的代码", "快速阅读无法理解其含义与行为"),
]

FILE_RE = re.compile(r"^[\w./\u4e00-\u9fff ()-]+?\.(py|ts|tsx|md|yaml|yml|json|sh|sql)(:\d+(?:-\d+)?)?$")


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def short_where(items: list[str]) -> str:
    return " ".join(items)


def path_html(where: str) -> str:
    return f'<code class="path">{esc(where)}</code>'


def load_units() -> list[dict]:
    units = []
    for path in sorted(UNITS.glob("*.json")):
        if path.stem == "EXAMPLE":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path.name}: invalid JSON: {exc}") from exc
        data.setdefault("unit", path.stem)
        data.setdefault("issues", [])
        data.setdefault("passes", [])
        data.setdefault("scope", [])
        data["_source"] = path.name
        units.append(data)
    return units


def order_key(unit: dict) -> tuple[int, str]:
    for index, (uid, _, _) in enumerate(UNIT_ORDER):
        if unit["unit"] == uid:
            return (index, "")
    return (len(UNIT_ORDER), unit["unit"])


def group_of(unit_id: str) -> tuple[str, str]:
    for uid, group, scope in UNIT_ORDER:
        if unit_id == uid:
            return group, scope
    return "其它", ""


def severity_tally(issues: list[dict]) -> Counter:
    return Counter(issue.get("severity", "中") for issue in issues)


def sort_issues(issues: list[dict]) -> list[dict]:
    return sorted(
        issues,
        key=lambda issue: (
            SEVERITY_ORDER.get(issue.get("severity", "中"), 3),
            issue.get("dim", ""),
            issue.get("id", ""),
        ),
    )


CSS = """
:root{
  --bg:#f6f7f9; --panel:#fff; --ink:#1b1f24; --muted:#5b6672; --line:#dfe3e8;
  --high:#c0392b; --mid:#b9770e; --low:#5d6d7e; --accent:#1f4e79; --ok:#1e7b4f;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--accent)}
code{font-family:var(--mono);font-size:.86em;background:#eef1f4;padding:.1em .35em;border-radius:4px}
pre{font-family:var(--mono);font-size:12.5px;line-height:1.5;background:#20262e;color:#e6edf3;
  padding:12px 14px;border-radius:8px;overflow-x:auto;margin:.5em 0;white-space:pre}
pre .ln{color:#7d8998;user-select:none}
.wrap{max-width:1180px;margin:0 auto;padding:32px 20px 80px}
header.top{border-bottom:3px solid var(--accent);padding-bottom:18px;margin-bottom:26px}
header.top h1{margin:0 0 6px;font-size:30px;letter-spacing:-.01em}
header.top .sub{color:var(--muted);font-size:14px}
header.top .meta{margin-top:10px;font-size:13px;color:var(--muted)}
h2{font-size:22px;margin:44px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:17px;margin:26px 0 8px}
p.lede{color:var(--muted);max-width:78ch}
nav.toc{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin:18px 0 8px}
nav.toc ol{margin:6px 0 0;padding-left:22px;columns:2;column-gap:34px}
nav.toc li{margin:3px 0;break-inside:avoid}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent);
  border-radius:8px;padding:12px 14px}
.tile .name{font-weight:600;font-size:15px}
.tile .scope{color:var(--muted);font-size:12px;margin-top:2px;word-break:break-all}
.tile .nums{margin-top:8px;font-size:13px;display:flex;gap:10px;flex-wrap:wrap}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;line-height:1.7}
.pill.high{background:#fdecea;color:var(--high)}
.pill.mid{background:#fdf3e2;color:var(--mid)}
.pill.low{background:#eef1f4;color:var(--low)}
.pill.ok{background:#e8f5ee;color:var(--ok)}
.pill.dim{background:#eef1f4;color:var(--muted);font-weight:500}
.unit{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin:18px 0}
.unit > h2{margin-top:0;border:0;padding:0;font-size:24px}
.unit .scope-line{color:var(--muted);font-size:12.5px;font-family:var(--mono);word-break:break-all}
.unit .brief{margin:14px 0 0;padding:12px 14px;background:#f8fafc;border-left:3px solid var(--accent);border-radius:0 6px 6px 0}
.unit .brief dt{font-weight:600;font-size:13px;color:var(--accent);margin-top:8px}
.unit .brief dt:first-child{margin-top:0}
.unit .brief dd{margin:2px 0 0;font-size:14px}
.issues{margin-top:16px}
.issue{border-top:1px solid var(--line);padding:14px 0 4px}
.issue:first-child{border-top:0}
.issue .head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.issue .id{font-family:var(--mono);font-size:12px;color:var(--muted)}
.issue .title{font-weight:600;font-size:15.5px;flex:1 1 320px}
.issue .dim{font-size:12px;color:var(--accent);background:#eaf1f8;padding:1px 8px;border-radius:6px;white-space:nowrap}
.issue .signals{margin:6px 0 0;font-size:12.5px;color:var(--muted)}
.issue .where{margin:8px 0 0;font-size:12.5px;line-height:1.9}
.issue .why,.issue .fix{margin:8px 0 0;font-size:14px}
.issue .why b,.issue .fix b{color:var(--accent)}
.passes{margin-top:16px;border-top:1px dashed var(--line);padding-top:12px}
.passes h4{margin:0 0 6px;font-size:13px;color:var(--ok)}
.passes ul{margin:0;padding-left:20px;font-size:13.5px;color:#38424d}
table{border-collapse:collapse;width:100%;background:var(--panel);font-size:13.5px;margin:12px 0}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef1f4;font-weight:600;white-space:nowrap}
td.num{text-align:right;font-family:var(--mono)}
.bar{display:inline-block;height:9px;border-radius:3px;vertical-align:middle}
.callout{background:#fff8e6;border:1px solid #f0d9a8;border-left:4px solid #d68910;border-radius:8px;padding:12px 16px;margin:14px 0}
.callout.warn{background:#fdecea;border-color:#f3c2bc;border-left-color:var(--high)}
.callout.info{background:#eef4fa;border-color:#c9dcee;border-left-color:var(--accent)}
.checklist{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:6px 20px 16px;margin:14px 0}
.checklist h3{margin:16px 0 6px;font-size:15px}
.checklist ul{margin:0;padding-left:20px}
.checklist li{margin:3px 0;font-size:14px}
footer{margin-top:50px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
.fixrec{margin:10px 0 2px;padding:10px 14px;background:#eef7f1;border:1px solid #cfe7da;border-left:4px solid var(--ok);border-radius:0 6px 6px 0}
.fixrec .fixhead{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.fixrec .fixtitle{font-weight:600;font-size:14px}
.fixrec pre{background:#1d2b24}
.fixrec .why,.fixrec .where{margin:6px 0 0;font-size:13.5px}
@media print{body{background:#fff}.unit{break-inside:avoid}nav.toc{display:none}}
"""


STATUS_LABEL = {
    "fixed": ("已修复", "ok"),
    "fixing": ("修复中", "mid"),
    "wontfix": ("不修（已说明）", "dim"),
}


def fix_html(issue: dict) -> str:
    """Render the remediation block attached to an issue, when one exists."""
    fix = issue.get("fix_record")
    if not fix:
        return ""
    status = fix.get("status", "fixing")
    label, pill = STATUS_LABEL.get(status, ("修复中", "mid"))
    files = fix.get("files") or []
    file_list = "、".join(f"<code>{esc(f)}</code>" for f in files)
    evidence = (fix.get("evidence") or "").strip()
    evidence_html = f"<pre>{esc(evidence)}</pre>" if evidence else ""
    return (
        '<div class="fixrec">'
        f'<div class="fixhead"><span class="pill {pill}">{esc(label)}</span>'
        f'<span class="fixtitle">{esc(fix.get("title", ""))}</span></div>'
        f'<p class="why"><b>修法：</b>{esc(fix.get("approach", ""))}</p>'
        f'<p class="where">改动：{file_list or "（待记录）"}</p>'
        f'{evidence_html}'
        f'<p class="why"><b>验证：</b>{esc(fix.get("verification", ""))}</p>'
        f'<p class="why"><b>未验证 / 已知边界：</b>{esc(fix.get("unverified", ""))}</p>'
        "</div>"
    )


def issue_html(issue: dict) -> str:
    where = "".join(f'<div>{path_html(w)}</div>' for w in issue.get("where", []))
    signals = issue.get("signals") or []
    signal_html = (
        f'<p class="signals">危险信号：{"、".join(esc(s) for s in signals)}</p>' if signals else ""
    )
    fix_block = fix_html(issue)
    evidence = (issue.get("evidence") or "").strip()
    if evidence:
        lines = evidence.split("\n")
        body = "\n".join(f'<span class="ln">{i + 1:>3}</span>  {esc(line)}' for i, line in enumerate(lines))
        evidence_html = f"<pre>{body}</pre>"
    else:
        evidence_html = '<p class="lede">（无摘录）</p>'
    return f"""      <div class="issue" id="{esc(issue.get('id', ''))}">
        <div class="head">
          <span class="pill {severity_class(issue.get('severity'))}">{esc(issue.get('severity', '中'))}</span>
          <span class="title">{esc(issue.get('title', ''))}</span>
          <span class="id">{esc(issue.get('id', ''))}</span>
          <span class="dim">{esc(issue.get('dim', ''))}</span>
          {status_badge(issue)}
        </div>
{signal_html}        <div class="where">{where}</div>
        {evidence_html}
        <p class="why"><b>为什么是问题：</b>{esc(issue.get('why', ''))}</p>
        <p class="fix"><b>修法：</b>{esc(issue.get('fix', ''))}</p>
{fix_block}      </div>"""


def status_badge(issue: dict) -> str:
    fix = issue.get("fix_record")
    if not fix:
        return ""
    label, pill = STATUS_LABEL.get(fix.get("status", "fixing"), ("修复中", "mid"))
    return f'<span class="pill {pill}">{esc(label)}</span>'


def severity_class(severity: object) -> str:
    return {"高": "high", "中": "mid", "低": "low"}.get(str(severity), "low")


def unit_html(unit: dict) -> str:
    issues = sort_issues(unit.get("issues", []))
    tally = severity_tally(issues)
    group, scope_hint = group_of(unit["unit"])
    scope = unit.get("scope") or ([scope_hint] if scope_hint else [])
    passes = unit.get("passes", [])
    pass_html = ""
    if passes:
        items = "".join(
            f'<li><b>{esc(p.get("dim", ""))}</b>：{esc(p.get("note", ""))}</li>' for p in passes
        )
        pass_html = f'<div class="passes"><h4>检查过且未发现问题的维度</h4><ul>{items}</ul></div>'
    issues_html = "\n".join(issue_html(issue) for issue in issues) or '<p class="lede">（无问题条目）</p>'
    return f"""  <section class="unit" id="unit-{esc(unit['unit'])}">
    <h2>{esc(unit.get('title', unit['unit']))} <span class="pill dim">{esc(group)}</span></h2>
    <div class="scope-line">范围：{esc(' ｜ '.join(scope))}</div>
    <div class="nums" style="margin-top:8px">
      <span class="pill high">高 {tally.get('高', 0)}</span>
      <span class="pill mid">中 {tally.get('中', 0)}</span>
      <span class="pill low">低 {tally.get('低', 0)}</span>
      <span class="pill ok">通过维度 {len(passes)}</span>
    </div>
    <dl class="brief">
      <dt>一句话</dt><dd>{esc(unit.get('one_sentence', ''))}</dd>
      <dt>它独占的那份知识</dt><dd>{esc(unit.get('knowledge', ''))}</dd>
    </dl>
    <div class="issues">
{issues_html}
    </div>
{pass_html}
  </section>"""


def overview_html(units: list[dict]) -> str:
    totals = Counter()
    all_issues: list[dict] = []
    for unit in units:
        for issue in unit.get("issues", []):
            totals[issue.get("severity", "中")] += 1
            all_issues.append({**issue, "_unit": unit["unit"], "_title": unit.get("title", unit["unit"])})

    tiles = []
    for unit in units:
        issues = unit.get("issues", [])
        tally = severity_tally(issues)
        group, scope_hint = group_of(unit["unit"])
        tiles.append(f"""      <a class="tile" href="#unit-{esc(unit['unit'])}" style="text-decoration:none;color:inherit">
        <div class="name"><code>{esc(unit['unit'])}</code></div>
        <div class="scope">{esc(group)} ｜ {esc(scope_hint)}</div>
        <div class="nums">
          <span class="pill high">高 {tally.get('高', 0)}</span>
          <span class="pill mid">中 {tally.get('中', 0)}</span>
          <span class="pill low">低 {tally.get('低', 0)}</span>
        </div>
      </a>""")

    # Dimension / signal aggregate across units.
    dim_counter: Counter = Counter()
    sig_counter: Counter = Counter()
    for issue in all_issues:
        dim_counter[issue.get("dim", "未分类")] += 1
        for signal in issue.get("signals", []):
            sig_counter[signal] += 1

    def bars(counter: Counter, colour: str) -> str:
        rows = []
        for label, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
            width = min(320, count * 18)
            bar = f'<span class="bar" style="width:{width}px;background:{colour}"></span>'
            rows.append(f"<tr><td>{esc(label)}</td><td class='num'>{count}</td><td>{bar}</td></tr>")
        return "".join(rows)

    dim_rows = bars(dim_counter, "var(--accent)")
    sig_rows = bars(sig_counter, "var(--high)")

    hotspots = sorted(
        [issue for issue in all_issues if issue.get("severity") == "高"],
        key=lambda issue: issue.get("_unit", ""),
    )
    hot_rows = "".join(
        f"<tr><td><a href='#unit-{esc(i['_unit'])}'>{esc(group_of(i['_unit'])[0])}</a></td>"
        f"<td>{esc(i.get('title', ''))}</td><td>{esc('、'.join(i.get('signals', [])))}</td>"
        f"<td>{esc(i.get('dim', ''))}</td></tr>"
        for i in hotspots
    )

    # Cross-module leakage: issues whose evidence names another module.
    leak_rows = []
    for issue in all_issues:
        if "信息泄露" in issue.get("signals", []) or "重复" in issue.get("signals", []):
            leak_rows.append(
                f"<tr><td><a href='#unit-{esc(issue['_unit'])}'>{esc(issue['_unit'])}</a></td>"
                f"<td>{esc(issue.get('title', ''))}</td>"
                f"<td>{esc(' '.join(issue.get('where', [])))}</td></tr>"
            )
    leak_table = (
        "<table><thead><tr><th>所属 unit</th><th>跨模块的知识重复 / 泄露</th><th>证据位置</th></tr></thead><tbody>"
        + "".join(leak_rows)
        + "</tbody></table>"
        if leak_rows
        else "<p class='lede'>未发现本条。</p>"
    )

    # Sites that more than one unit independently flagged (hit by 高/中 issues in 2+ units).
    file_units: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for issue in all_issues:
        if issue.get("severity") == "低":
            continue
        for where in issue.get("where", []):
            rel = where.split(":")[0].strip()
            if rel:
                file_units[rel][issue["_unit"]].append(issue.get("id", ""))
    overlap_rows = []
    for rel, units_on_file in sorted(file_units.items()):
        if len(units_on_file) >= 2:
            cells = "；".join(
                f"<a href='#unit-{esc(u)}'>{esc(u)}</a> ({esc('、'.join(ids))})"
                for u, ids in sorted(units_on_file.items())
            )
            overlap_rows.append(f"<tr><td><code>{esc(rel)}</code></td><td>{cells}</td></tr>")
    overlap_table = (
        "<table><thead><tr><th>同一处代码</th><th>被哪些 unit 独立命中</th></tr></thead><tbody>"
        + "".join(overlap_rows)
        + "</tbody></table>"
        if overlap_rows
        else "<p class='lede'>未发现同一文件被两个以上 unit 独立命中。</p>"
    )

    toc = "".join(
        f"<li><a href='#unit-{esc(u['unit'])}'>{esc(group_of(u['unit'])[0])}"
        f"（{len(u.get('issues', []))} 条）</a></li>"
        for u in units
    )

    return f"""
  <h2 id="summary">一、总览</h2>
  <div class="tiles">
{chr(10).join(tiles)}
  </div>
  <p class="lede">共 <b>{len(units)}</b> 个审计单元、<b>{len(all_issues)}</b> 条问题：
    高 <b>{totals.get('高', 0)}</b>、中 <b>{totals.get('中', 0)}</b>、低 <b>{totals.get('低', 0)}</b>。
    每条问题都带 <code>文件:行号</code> 与原文摘录，可按图索骥复核。</p>

  <nav class="toc">
    <b>模块索引</b>
    <ol>{toc}</ol>
  </nav>

  <h3>高危问题速览（{len(hotspots)} 条）</h3>
  <table>
    <thead><tr><th>模块</th><th>问题</th><th>危险信号</th><th>检查维度</th></tr></thead>
    <tbody>{hot_rows}</tbody>
  </table>

  <h3>检查维度命中分布</h3>
  <table>
    <thead><tr><th>维度 / 判据</th><th>命中条数</th><th></th></tr></thead>
    <tbody>{dim_rows or '<tr><td colspan="3">无</td></tr>'}</tbody>
  </table>

  <h3>危险信号命中分布</h3>
  <table>
    <thead><tr><th>危险信号</th><th>命中条数</th><th></th></tr></thead>
    <tbody>{sig_rows or '<tr><td colspan="3">无</td></tr>'}</tbody>
  </table>

  <h3>跨模块一览（信息泄露 / 重复知识）</h3>
  {leak_table}

  <h3>同一处代码被多个 unit 独立命中</h3>
  <p class="lede">下面这些位置分别被两个以上审计单元独立写进了问题清单——独立命中同一处，
    通常说明它不是某个模块的局部口味问题，而是跨模块的结构问题。</p>
  {overlap_table}
"""


def appendix_html() -> str:
    checklist_html = "".join(
        f"<h3>{esc(group)}</h3><ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"
        for group, items in CHECKLIST
    )
    signals_html = "".join(
        f"<tr><td><b>{esc(name)}</b></td><td>{esc(rule)}</td></tr>" for name, rule in SIGNALS
    )
    return f"""
  <h2 id="appendix">附录 A：本次使用的检查清单（原文）</h2>
  <div class="checklist">{checklist_html}</div>

  <h2 id="signals">附录 B：危险信号速查表（原文）</h2>
  <table><thead><tr><th>危险信号</th><th>一句话判据</th></tr></thead><tbody>{signals_html}</tbody></table>

  <h2 id="method">附录 C：方法与口径</h2>
  <ul>
    <li><b>审计对象</b>：仓库 <code>apps/api/src/better_resume/**</code>、<code>apps/web/src/**</code>、
      <code>apps/api/migrations/**</code>；按 <code>skills/modules/</code> 的既有模块划分加
      <code>http/</code>、<code>web</code>、<code>jobs+worker</code> 补全，共 {len(UNIT_ORDER)} 个单元。</li>
    <li><b>判据来源</b>：用户给的模块设计检查清单 + 危险信号速查表（附录 A/B 原文）；
      仓库既有规范 <code>AGENTS.md</code>、<code>CODING_STANDARDS.md</code> 用于「符合周围既有约定」这一条。</li>
    <li><b>证据口径</b>：每条问题的 <code>where</code> 是仓库相对路径 + 行号，<code>evidence</code> 是该处的原文摘录；
      复核方式为按行号打开文件比对。</li>
    <li><b>severity 口径</b>：<b>高</b> = 真会咬人的设计决策（调用者被迫了解实现 / 会扩散的重复 / 错误被结构固化）；
      <b>中</b> = 明显可改进但不紧急；<b>低</b> = 吹毛求疵。</li>
    <li><b>未做的事</b>：本次审计不改代码、不跑行为测试；<code>passes</code> 只记录实际读过且确认过关的维度，
      未列出的维度表示「本次未检查」，不等于「没问题」。</li>
    <li><b>修复记录</b>：已经动手修的问题在 <code>docs/audit/FIXES.md</code>（改了什么/为什么/怎么验证/未验证项），
      对应条目在本页会显示绿色「已修复 / 修复中」标记。</li>
    <li><b>可复跑</b>：<code>python3 scripts/build_module_audit.py</code> 由
      <code>docs/audit/units/*.json</code> 重新生成这份 HTML（数据与渲染分离，便于逐条修订后重出）。</li>
  </ul>
"""


def main() -> None:
    units = sorted(load_units(), key=order_key)
    if not units:
        raise SystemExit(f"no unit JSON found under {UNITS}")

    generated = date.today().isoformat()
    body = "\n".join(unit_html(unit) for unit in units)
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>better-resume 模块设计审计：问题清单与原因</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1>better-resume 模块设计审计：问题清单与原因</h1>
  <div class="sub">用「模块设计检查清单 + 危险信号速查表」逐条拷问每个模块，产出可复核的问题清单。</div>
  <div class="meta">生成日期 {generated} ｜ 审计单元 {len(units)} 个 ｜
    数据源 <code>docs/audit/units/*.json</code> ｜ 生成器 <code>scripts/build_module_audit.py</code></div>
</header>

<p class="lede">这份文件回答一个问题：<b>如果按「深模块」的标准重读这个仓库，每个模块欠了什么？</b>
每一条都落到具体的行、贴出原文，并说明「调用者 / 维护者为此付出了什么代价」，而不是给一份偏好清单。
读法建议：先看总览里的高危速览，再按模块索引跳到你在意的模块；<code>通过</code> 一栏是实际检查过、确认没问题的维度。</p>

<div class="callout info">
  <b>怎么用：</b>清单里每条 <span class="pill high">高</span> 都对应一个「现在就会让你疼」的决策；
  <span class="pill mid">中</span> 是值得排期但不必今天动的；
  <span class="pill low">低</span> 是风格洁癖。行号会随代码漂移，修完之后请重跑生成器重出这份报告。
</div>

{overview_html(units)}

  <h2 id="modules">二、逐模块问题清单</h2>
{body}

{appendix_html()}

<footer>
  由 <code>scripts/build_module_audit.py</code> 生成；数据在 <code>docs/audit/units/</code>，
  契约与判据在 <code>docs/audit/CONTRACT.md</code>。行号基于生成时的 <code>HEAD</code>，代码移动后需重跑。
</footer>
</div>
</body>
</html>
"""
    OUT.write_text(doc, encoding="utf-8")
    total = sum(len(unit.get("issues", [])) for unit in units)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(units)} units, {total} issues")


if __name__ == "__main__":
    main()
