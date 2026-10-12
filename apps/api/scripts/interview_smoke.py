"""面试冒烟：走一遍产品路径，要么打印它，要么断言它。

两种调用，一份实现：

    # 真实供应商：需要配置好的模型 key；打印黄金路径
    uv run python scripts/interview_smoke.py [base_url]

    # 假供应商：每个场景都被断言，失败退出非零
    uv run python scripts/interview_smoke.py --model smoke-fake --assert

断言运行默认打到 compose 入口（nginx），并点名其上游 smoke-fake：该供应商不携带 usage，所以
通过的断言运行绝不是关于真实模型的证据。它默认走遍每个场景：黄金路径、两种降级（没有文本层的
简历，以及技能匹配不到任何语料主题的简历），还有那条其 D23 规则回退仍须落到合法类别的无
category 形状。--scenario 过滤出其中一个用于调试。--expect-questions 注入被测试的契约值，
这正是让「错误期望 -> 非零退出」演示成为单条命令的原因。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

CJK_FONT = "STSong-Light"

DEFAULT_REAL_BASE_URL = "http://127.0.0.1:8040"
DEFAULT_ASSERT_BASE_URL = "http://127.0.0.1:8080"
REAL_QUESTION_COUNT = 3
CONTRACT_QUESTION_COUNT = 5
FAKE_MODEL = "smoke-fake"
SMOKE_USER_PREFIX = "m2-smoke"
QUESTION_LIMIT = 10
MAX_FOLLOW_UP = 2
LEGAL_CATEGORIES = ("fundamentals", "project", "internship")
DIMENSION_KEYS = ("accuracy", "depth", "coverage", "completeness")
MIN_SCORED_PER_CATEGORY = 2
THIN_SAMPLE_COMMENT = "样本不足"
#: 答题桶是 2/s（容量 4）；快速走完全程时最多照 Retry-After 重试这么多次。
RATE_LIMIT_RETRIES = 5
#: 引擎存在会话上的降级码（场景夹具里有镜像）。
RESUME_UNPARSABLE = "resume_unparsable"
CORPUS_NO_MATCH = "corpus_no_match"
#: 假供应商盯的提示标记；它据此切到无 category 形状（Q2）。
NO_CATEGORY_MARKER = "不给出 category"
REPO_ROOT = Path(__file__).resolve().parents[3]

RESUME_LINES: list[tuple[str, int, bool]] = [
    ("张三", 18, True),
    ("邮箱：zhangsan@example.com 电话：13800138000", 9, False),
    ("教育经历", 14, True),
    ("某大学 计算机科学与技术 2018-2022", 10, False),
    ("项目经历", 14, True),
    ("订单写入链路重构", 11, True),
    ("- 用 Python 重写批量写入，P99 从 800ms 降到 120ms，写入放大降低 40%", 10, False),
    ("- 设计幂等键与补偿任务，线上重复写入从每天 200 条降到 0", 10, False),
    ("技能特长", 14, True),
    ("Python, FastAPI, PostgreSQL, Redis, Docker", 10, False),
]

ANSWERS = [
    "我负责订单写入链路重构：先定位到写放大来自逐条 upsert，改成按主键排序的批量写入并加幂等键，"
    "P99 从 800ms 降到 120ms；补偿任务用定时扫描加去重表，线上重复写入从每天 200 条降到 0。",
    "压测用 locust 模拟峰值 3 倍流量，观察 P99、错误率和连接池等待；瓶颈在数据库连接数，"
    "把池大小和批大小做成可配并加了熔断降级，超时错误率从 1.2% 降到 0.05%。",
    "取舍上我优先保证正确性：先上幂等键再优化吞吐；代价是写入路径多一次查表，"
    "用 Redis 缓存热点键抵消，命中率 92%，整体仍是净收益。",
]

QUESTIONS_SQL = (
    "SELECT question_no, topic_no, follow_up_index, kind, coalesce(category, '') "
    "FROM interview_questions WHERE session_id = :'sid' "
    "ORDER BY topic_no, follow_up_index;"
)
SESSIONS_SQL = (
    "SELECT degraded_reasons::text, resume_warnings::text "
    "FROM interview_sessions WHERE id = :'sid';"
)


def build_resume_pdf() -> bytes:
    with contextlib.suppress(KeyError):  # 本进程内已注册
        pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for text, size, bold in RESUME_LINES:
        pdf.setFont(CJK_FONT, size + (1 if bold else 0))
        pdf.drawString(50, y, text)
        y -= size + 8
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_no_text_layer_pdf() -> bytes:
    """一页没有可提取文本：会降级为通用面试的扫描件情形。"""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.rect(50, 700, 300, 120, fill=1)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_unmatched_resume_pdf() -> bytes:
    """技能匹配不到任何语料主题的简历；它还带着解析器警告。"""
    with contextlib.suppress(KeyError):  # 本进程内已注册
        pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont(CJK_FONT, 10)
    pdf.drawString(50, 800, "COBOL, Fortran, Pascal, Ada")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_no_category_resume_pdf() -> bytes:
    """黄金简历加上让假供应商省略 category 的标记（Q2）。"""
    with contextlib.suppress(KeyError):  # 本进程内已注册
        pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for text, size, bold in RESUME_LINES:
        pdf.setFont(CJK_FONT, size + (1 if bold else 0))
        pdf.drawString(50, y, text)
        y -= size + 8
    pdf.setFont(CJK_FONT, 10)
    pdf.drawString(50, y, f"技能补充：{NO_CATEGORY_MARKER}")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@dataclass(frozen=True)
class Scenario:
    """一个上传并走完全程的变体，外加契约期望它产生的降级。"""

    name: str
    title: str
    build_resume: Callable[[], bytes]
    degraded_reasons: tuple[str, ...]
    resume_warnings: tuple[str, ...]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("golden", "healthy resume", build_resume_pdf, (), ()),
    Scenario(
        "no-text-layer",
        "no extractable text layer",
        build_no_text_layer_pdf,
        (RESUME_UNPARSABLE,),
        (),
    ),
    Scenario(
        "unmatched-corpus",
        "skills match no corpus topic",
        build_unmatched_resume_pdf,
        (CORPUS_NO_MATCH,),
        ("no_sections_detected", "no_contact_found"),
    ),
    Scenario(
        "no-category",
        "vendor omits category; the D23 rule fallback decides",
        build_no_category_resume_pdf,
        (),
        (),
    ),
)
SCENARIO_NAMES = tuple(scenario.name for scenario in SCENARIOS)
SCENARIO_BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}


def select_scenarios(names: Sequence[str] | None) -> list[Scenario]:
    if not names:
        return list(SCENARIOS)
    return [SCENARIO_BY_NAME[name] for name in names]


def _clip(text: str, limit: int = 2000) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _query_hint(session_id: str) -> str:
    return (
        "docker compose exec -T postgres psql -U better_resume -d better_resume "
        '-c "SELECT question_no, topic_no, follow_up_index, kind, category '
        "FROM interview_questions WHERE session_id = '" + session_id + "' "
        'ORDER BY topic_no, follow_up_index;"'
    )


def _psql_query(sql: str, session_id: str) -> list[str] | None:
    """在 compose 栈内跑一条固定查询；docker 不可用时为 None。"""
    docker = shutil.which("docker")
    if docker is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - 固定 argv，不走 shell
            [
                docker,
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "better_resume",
                "-d",
                "better_resume",
                "-v",
                "ON_ERROR_STOP=1",
                "-t",
                "-A",
                "-F",
                "|",
                "-v",
                f"sid={session_id}",
            ],
            input=sql,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            cwd=REPO_ROOT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def probe_db_rows(session_id: str) -> dict[str, Any] | None:
    """读取持久化的会话通知与问题行。

    None 表示 docker/psql 探针本身不可用；查询跑了但没找到 sessions 行时返回一个标记为
    session_row_missing 的快照，让断言能判它失败而不是跳过。它同时喂给失败诊断和持久化断言，
    所以一个场景的降级必须在 Postgres 里可见，而不只是在 HTTP 响应里。
    """
    session_lines = _psql_query(SESSIONS_SQL, session_id)
    question_lines = _psql_query(QUESTIONS_SQL, session_id)
    if session_lines is None or question_lines is None:
        return None
    if not session_lines:
        return {
            "session_row_missing": True,
            "degraded_reasons": None,
            "resume_warnings": None,
            "questions": [],
        }
    try:
        reasons_text, warnings_text = session_lines[0].split("|", 1)
        degraded_reasons = list(json.loads(reasons_text))
        resume_warnings = list(json.loads(warnings_text))
        questions = []
        for line in question_lines:
            question_no, topic_no, follow_up_index, kind, category = line.split("|")[:5]
            questions.append(
                {
                    "question_no": question_no,
                    "topic_no": int(topic_no),
                    "follow_up_index": int(follow_up_index),
                    "kind": kind,
                    "category": category or None,
                }
            )
    except (ValueError, TypeError):
        return None
    return {
        "degraded_reasons": degraded_reasons,
        "resume_warnings": resume_warnings,
        "questions": questions,
    }


class GoldenPathChecks:
    """黄金路径断言；每个失败都点名步骤、原始响应体与一次 DB 查询。"""

    def __init__(
        self,
        *,
        expect_questions: int,
        expect_degraded_reasons: Sequence[str] = (),
        expect_resume_warnings: Sequence[str] = (),
        db_probe: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> None:
        self.expect_questions = expect_questions
        self.expect_degraded_reasons = tuple(expect_degraded_reasons)
        self.expect_resume_warnings = tuple(expect_resume_warnings)
        self.db_probe = db_probe
        self.session_id: str | None = None
        self.failures: list[str] = []
        self.passed = 0
        self.main_category: dict[object, object] = {}
        self.saw_follow_up = False

    def bind(self, session_id: str) -> None:
        self.session_id = session_id

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0

    def expect(self, step: str, ok: bool, *, detail: str = "", raw: object = None) -> bool:
        if ok:
            self.passed += 1
            print(f"[golden-path] PASS  {step}")
            return True
        self.failures.append(step)
        print(f"[golden-path] FAIL  {step}: {detail}")
        if raw:
            print(f"[golden-path]       raw response: {_clip(str(raw))}")
        self._show_db()
        return False

    def expect_status(self, step: str, response: httpx.Response) -> bool:
        return self.expect(
            step,
            200 <= response.status_code < 300,
            detail=f"HTTP {response.status_code}",
            raw=response.text,
        )

    def degradation_checks(
        self,
        where: str,
        *,
        session: Any,
        raw: str,
        batch_degraded: object = None,
        batch_reasons: object = None,
    ) -> None:
        expected_reasons = list(self.expect_degraded_reasons)
        expected_warnings = list(self.expect_resume_warnings)
        session = session if isinstance(session, dict) else {}
        reasons = session.get("degraded_reasons")
        warnings = session.get("resume_warnings")
        self.expect(
            f"{where}: degraded_reasons are explicit",
            list(reasons or []) == expected_reasons,
            detail=f"reasons={reasons!r} expected={expected_reasons!r}",
            raw=raw,
        )
        if where == "questions":
            self.expect(
                "questions: degraded flag matches the reasons",
                bool(batch_degraded) == bool(expected_reasons)
                and list(batch_reasons or []) == expected_reasons,
                detail=f"degraded={batch_degraded!r} reasons={batch_reasons!r}",
                raw=raw,
            )
        self.expect(
            f"{where}: resume_warnings are persisted",
            warnings == expected_warnings,
            detail=f"warnings={warnings!r} expected={expected_warnings!r}",
            raw=raw,
        )

    def question_batch(self, batch: Any, raw: str) -> None:
        if not isinstance(batch, dict):
            self.expect(
                "questions: JSON object",
                False,
                detail=f"type={type(batch).__name__}",
                raw=raw,
            )
            return
        questions = batch.get("questions")
        questions = questions if isinstance(questions, list) else []
        self.expect(
            "questions: contract count",
            len(questions) == self.expect_questions,
            detail=f"expected {self.expect_questions}, got {len(questions)}",
            raw=raw,
        )
        bad = []
        for question in questions:
            question = question if isinstance(question, dict) else {}
            topic = question.get("topic_no")
            category = question.get("category")
            self.main_category[topic] = category
            if (
                question.get("kind", "main") != "main"
                or category not in LEGAL_CATEGORIES
                or not question.get("text")
            ):
                bad.append(
                    f"{question.get('question_no')}: kind={question.get('kind')!r} "
                    f"category={category!r}"
                )
        self.expect(
            "questions: every main question carries a legal category",
            not bad,
            detail="; ".join(bad),
            raw=raw,
        )
        session = batch.get("session")
        session = session if isinstance(session, dict) else {}
        self.degradation_checks(
            "questions",
            session=session,
            raw=raw,
            batch_degraded=batch.get("degraded"),
            batch_reasons=batch.get("degraded_reasons"),
        )
        self.expect(
            "questions: resume_score is a number",
            _is_number(session.get("resume_score")),
            detail=f"resume_score={session.get('resume_score')!r}",
            raw=raw,
        )

    def answer(self, question_no: str, payload: Any, raw: str) -> None:
        payload = payload if isinstance(payload, dict) else {}
        answer = payload.get("answer")
        answer = answer if isinstance(answer, dict) else {}
        self.expect(
            f"answer {question_no}: scored",
            _is_number(answer.get("score")),
            detail=f"score={answer.get('score')!r} error={answer.get('error_message')!r}",
            raw=raw,
        )
        action = payload.get("next_action")
        self.expect(
            f"answer {question_no}: advances the flow",
            action in ("next_question", "follow_up", "finished"),
            detail=f"next_action={action!r}",
            raw=raw,
        )
        if action != "follow_up":
            return
        self.saw_follow_up = True
        follow_up = payload.get("next_question")
        follow_up = follow_up if isinstance(follow_up, dict) else {}
        topic = follow_up.get("topic_no")
        category = follow_up.get("category")
        inherits = (
            follow_up.get("kind") == "follow_up"
            and int(follow_up.get("follow_up_index") or 0) >= 1
            and bool(follow_up.get("text"))
            and category in LEGAL_CATEGORIES
            and category == self.main_category.get(topic)
        )
        self.expect(
            f"answer {question_no}: follow-up inherits topic {topic} category",
            inherits,
            detail=(
                f"follow-up category={category!r}, main category={self.main_category.get(topic)!r}"
            ),
            raw=raw,
        )

    def full_path(self, completed: bool, answered: int) -> None:
        self.expect(
            "answers: reaches the end of the interview",
            completed,
            detail=f"stopped after {answered} answers without a finished next_action",
        )
        self.expect(
            "answers: at least one follow-up was asked",
            self.saw_follow_up,
            detail="no next_action was follow_up",
        )

    def report(self, report: Any, raw: str) -> None:
        if not isinstance(report, dict):
            self.expect(
                "report: JSON object", False, detail=f"type={type(report).__name__}", raw=raw
            )
            return
        session = report.get("session")
        session = session if isinstance(session, dict) else {}
        self.degradation_checks("report", session=session, raw=raw)
        self.expect(
            "report: session is finished",
            session.get("status") == "finished",
            detail=f"status={session.get('status')!r}",
            raw=raw,
        )
        self.expect(
            "report: overall_score is a number",
            _is_number(report.get("overall_score")),
            detail=f"overall_score={report.get('overall_score')!r}",
            raw=raw,
        )
        dimensions = report.get("dimensions")
        dimensions = dimensions if isinstance(dimensions, list) else []
        keys = [item.get("key") for item in dimensions if isinstance(item, dict)]
        self.expect(
            "report: four dimensions in contract order",
            keys == list(DIMENSION_KEYS),
            detail=f"keys={keys}",
            raw=raw,
        )
        self.expect(
            "report: every dimension is scored",
            bool(dimensions) and all(_is_number(item.get("score")) for item in dimensions),
            detail=f"dimensions={dimensions}",
            raw=raw,
        )
        turns = report.get("turns")
        turns = turns if isinstance(turns, list) else []
        self.expect(
            "report: turns replay the interview",
            bool(turns),
            detail=f"turns={len(turns)}",
            raw=raw,
        )
        main_category = {
            turn.get("topic_no"): turn.get("category")
            for turn in turns
            if isinstance(turn, dict) and turn.get("kind") == "main"
        }
        bad_turns = []
        for turn in turns:
            if not isinstance(turn, dict):
                bad_turns.append(f"{turn!r}")
                continue
            category = turn.get("category")
            if turn.get("kind") == "main" and (
                category not in LEGAL_CATEGORIES or turn.get("score") is None
            ):
                bad_turns.append(
                    f"{turn.get('question_no')}: main category={category!r} "
                    f"score={turn.get('score')!r}"
                )
            if turn.get("kind") == "follow_up":
                expected = main_category.get(turn.get("topic_no"))
                if category != expected or category not in LEGAL_CATEGORIES:
                    bad_turns.append(
                        f"{turn.get('question_no')}: follow-up category={category!r} "
                        f"main={expected!r}"
                    )
        self.expect(
            "report: every turn keeps its topic category",
            not bad_turns,
            detail="; ".join(bad_turns),
            raw=raw,
        )
        self.expect(
            "report: follow-up turns are present",
            any(isinstance(turn, dict) and turn.get("kind") == "follow_up" for turn in turns),
            detail="no follow_up turn in the report",
            raw=raw,
        )
        categories = report.get("categories")
        categories = categories if isinstance(categories, list) else []
        keys = [item.get("key") for item in categories if isinstance(item, dict)]
        self.expect(
            "report: one section per category",
            keys == list(LEGAL_CATEGORIES),
            detail=f"keys={keys}",
            raw=raw,
        )
        bad_categories = []
        for item in categories:
            if not isinstance(item, dict):
                bad_categories.append(f"{item!r}")
                continue
            scored = [
                turn
                for turn in turns
                if isinstance(turn, dict)
                and turn.get("category") == item.get("key")
                and _is_number(turn.get("score"))
            ]
            comment = item.get("comment")
            if item.get("count") != len(scored):
                bad_categories.append(
                    f"{item.get('key')}: count={item.get('count')!r} turns={len(scored)}"
                )
            elif len(scored) < MIN_SCORED_PER_CATEGORY:
                if item.get("score") is not None or comment != THIN_SAMPLE_COMMENT:
                    bad_categories.append(
                        f"{item.get('key')}: thin sample score={item.get('score')!r} "
                        f"comment={comment!r}"
                    )
            elif not _is_number(item.get("score")) or not comment:
                bad_categories.append(
                    f"{item.get('key')}: score={item.get('score')!r} comment={comment!r}"
                )
        self.expect(
            "report: category aggregates match the turns",
            not bad_categories,
            detail="; ".join(bad_categories),
            raw=raw,
        )
        self.expect(
            "report: suggestions are present",
            bool(report.get("suggestions")),
            detail=f"suggestions={report.get('suggestions')!r}",
            raw=raw,
        )

    def persistence_checks(self) -> None:
        """确认响应展示的内容也落到了 Postgres。

        不可用的 docker/psql 探针会打印一行明确的 SKIPPED，绝不判这次运行失败；查询跑了但
        没找到 sessions 行是一次具名失败。逐行检查仍会从存储的行里重新推导类别。
        """
        if self.db_probe is None or self.session_id is None:
            print("[golden-path] SKIPPED (no docker probe): no db probe was configured")
            return
        snapshot = self.db_probe(self.session_id)
        if snapshot is None:
            print(
                "[golden-path] SKIPPED (docker/psql probe unavailable): persistence is not checked"
            )
            return
        if snapshot.get("session_row_missing"):
            self.expect(
                "db: session row is persisted",
                False,
                detail=f"no sessions row for session_id={self.session_id}",
            )
            return
        reasons = snapshot.get("degraded_reasons")
        warnings = snapshot.get("resume_warnings")
        self.expect(
            "db: session degradation is persisted",
            list(reasons or []) == list(self.expect_degraded_reasons)
            and list(warnings or []) == list(self.expect_resume_warnings),
            detail=(
                f"db reasons={reasons!r} warnings={warnings!r} "
                f"expected reasons={list(self.expect_degraded_reasons)!r} "
                f"warnings={list(self.expect_resume_warnings)!r}"
            ),
        )
        bad: list[str] = []
        main_category: dict[object, object] = {}
        rows = snapshot.get("questions") or []
        if not rows:
            bad.append("no question rows")
        for row in rows:
            row = row if isinstance(row, dict) else {}
            topic = row.get("topic_no")
            category = row.get("category")
            if category not in LEGAL_CATEGORIES:
                bad.append(f"{row.get('question_no')}: category={category!r}")
            if row.get("kind") == "follow_up":
                expected = main_category.get(topic)
                if category != expected:
                    bad.append(
                        f"{row.get('question_no')}: follow-up category={category!r} "
                        f"main={expected!r}"
                    )
            else:
                main_category[topic] = category
        self.expect(
            "db: question categories are legal and inherited",
            not bad,
            detail="; ".join(bad),
        )

    def _show_db(self) -> None:
        if not self.session_id:
            return
        snapshot = self.db_probe(self.session_id) if self.db_probe is not None else None
        if not snapshot:
            print(f"[golden-path]       inspect: {_query_hint(self.session_id)}")
            return
        print(
            "[golden-path]       db session: "
            f"degraded_reasons={snapshot.get('degraded_reasons')!r} "
            f"resume_warnings={snapshot.get('resume_warnings')!r}"
        )
        for row in snapshot.get("questions") or []:
            print(
                "[golden-path]         "
                f"{row.get('question_no')} topic={row.get('topic_no')} "
                f"kind={row.get('kind')} category={row.get('category')!r}"
            )


def _decode(response: httpx.Response, checks: GoldenPathChecks | None, step: str) -> Any | None:
    """成功 -> 解析后的 JSON。非 2xx 或畸形响应体会被点名并返回 None。"""
    if checks is not None:
        if not checks.expect_status(step, response):
            return None
    elif not 200 <= response.status_code < 300:
        print(
            f"{step} failed: HTTP {response.status_code} {response.text[:200]}",
            file=sys.stderr,
        )
        return None
    try:
        return response.json()
    except ValueError:
        if checks is not None:
            checks.expect(
                f"{step}: JSON body", False, detail="response is not JSON", raw=response.text
            )
        else:
            print(f"{step} failed: response is not JSON", file=sys.stderr)
        return None


def _rate_limit_delay(response: httpx.Response) -> float:
    """照服务端的 Retry-After 办；否则快速答题会撞上 2/s 桶。"""
    raw = response.headers.get("Retry-After")
    try:
        return max(0.0, float(raw)) if raw else 1.0
    except ValueError:
        return 1.0


async def _send(
    client: httpx.AsyncClient,
    checks: GoldenPathChecks | None,
    step: str,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response | None:
    """传输错误是一次具名步骤失败，绝不是裸 traceback。"""
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            if checks is not None:
                checks.expect(step, False, detail=f"transport error: {exc}", raw="")
            else:
                print(f"{step} failed: {exc}", file=sys.stderr)
            return None
        if response.status_code != 429 or attempt == RATE_LIMIT_RETRIES:
            return response
        delay = _rate_limit_delay(response)
        # 两种调用都需要这个退避；真实运行不得静默重试。
        print(f"[golden-path] retry {step}: HTTP 429, waiting {delay:g}s")
        await asyncio.sleep(delay)
    return response


def _question_form(args: argparse.Namespace) -> dict[str, str]:
    data = {"count": str(args.count)}
    if args.model_ref:
        data["model_ref"] = args.model_ref
    return data


def _answer_body(args: argparse.Namespace, question_no: str, answer: str, asked: int) -> dict:
    body: dict[str, Any] = {
        "question_no": question_no,
        "answer": answer,
        "request_id": f"smoke-{asked}",
    }
    if args.model_ref:
        body["model_ref"] = args.model_ref
    return body


def _finish_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {"params": {"model_ref": args.model_ref}} if args.model_ref else {}


async def run(
    args: argparse.Namespace,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    db_probe: Callable[[str], dict[str, Any] | None] | None = None,
) -> int:
    scenarios = select_scenarios(args.scenarios) if args.assert_mode else [SCENARIOS[0]]
    # 真实运行保留基线身份；只有断言运行才会生成唯一用户。
    run_user = (
        f"{SMOKE_USER_PREFIX}-{uuid.uuid4().hex[:8]}" if args.assert_mode else SMOKE_USER_PREFIX
    )
    if args.assert_mode:
        print(
            f"[golden-path] upstream={args.model_ref} (fake vendor: its responses carry no usage; "
            "this is not a real-model result)"
        )
        print(
            f"[golden-path] base_url={args.base_url} count={args.count} "
            f"expect_questions={args.expect_questions} run_user={run_user} "
            f"scenarios={','.join(scenario.name for scenario in scenarios)}"
        )
    codes = [
        await _run_scenario(args, scenario, user=run_user, transport=transport, db_probe=db_probe)
        for scenario in scenarios
    ]
    return 0 if all(code == 0 for code in codes) else 1


async def _run_scenario(
    args: argparse.Namespace,
    scenario: Scenario,
    *,
    user: str,
    transport: httpx.AsyncBaseTransport | None = None,
    db_probe: Callable[[str], dict[str, Any] | None] | None = None,
) -> int:
    checks = (
        GoldenPathChecks(
            expect_questions=args.expect_questions,
            expect_degraded_reasons=scenario.degraded_reasons,
            expect_resume_warnings=scenario.resume_warnings,
            db_probe=db_probe,
        )
        if args.assert_mode
        else None
    )
    if checks is not None:
        print(f"[golden-path] scenario={scenario.name}: {scenario.title}")

    async with httpx.AsyncClient(
        base_url=args.base_url,
        trust_env=False,
        proxy=None,
        timeout=args.timeout,
        transport=transport,
    ) as client:
        login = await _send(
            client,
            checks,
            "login: session created",
            "POST",
            "/api/v1/auth/session",
            json={"user_id": user},
        )
        if login is None:
            return 1
        print("login:", login.status_code)
        if _decode(login, checks, "login: session created") is None:
            return 1

        created = await _send(
            client, checks, "session: created", "POST", "/api/v1/interview/sessions", json={}
        )
        if created is None:
            return 1
        session = _decode(created, checks, "session: created")
        if not isinstance(session, dict):
            return 1
        session_id = session["id"]
        if checks is not None:
            checks.bind(session_id)
        print("session:", session_id, session["status"])

        generated = await _send(
            client,
            checks,
            "questions: generated",
            "POST",
            f"/api/v1/interview/sessions/{session_id}/questions",
            files={
                "file": (
                    f"{scenario.name}.pdf" if args.assert_mode else "cv.pdf",
                    scenario.build_resume(),
                    "application/pdf",
                )
            },
            data=_question_form(args),
        )
        if generated is None:
            return 1
        batch = _decode(generated, checks, "questions: generated")
        if not isinstance(batch, dict):
            if checks is not None:
                checks.question_batch(batch, generated.text)
            return 1
        if checks is not None:
            checks.question_batch(batch, generated.text)
        print(
            f"questions: {len(batch['questions'])}  resume_score={batch['session']['resume_score']}"
        )
        for question in batch["questions"]:
            print(f"  {question['question_no']}. {question['text'][:60]}")

        # 真实运行一直答完六题就停；断言运行走完契约路径（每个主题最多取 MAX_FOLLOW_UP 次追问）
        # 直到结束。
        max_answers = args.count * (1 + MAX_FOLLOW_UP) if checks is not None else 6
        asked = 0
        completed = False
        while asked < max_answers:
            restored = await _send(
                client,
                checks,
                "restore: current question",
                "GET",
                f"/api/v1/interview/sessions/{session_id}/restore",
            )
            if restored is None:
                return 1
            view = _decode(restored, checks, "restore: current question")
            if not isinstance(view, dict):
                return 1
            question_no = view["flow"]["current_question_no"]
            if question_no is None:
                completed = True
                break
            answer = ANSWERS[min(asked, len(ANSWERS) - 1)]
            submitted = await _send(
                client,
                checks,
                f"answer {question_no}: submitted",
                "POST",
                f"/api/v1/interview/sessions/{session_id}/answers",
                json=_answer_body(args, question_no, answer, asked),
            )
            if submitted is None:
                return 1
            payload = _decode(submitted, checks, f"answer {question_no}: submitted")
            if not isinstance(payload, dict):
                return 1
            if checks is not None:
                checks.answer(question_no, payload, submitted.text)
            print(
                f"answered {question_no}: score={payload['answer']['score']} "
                f"next={payload['next_action']} next_no={payload['next_question_no']} "
                f"reason={payload['answer']['follow_up_reason']}"
            )
            asked += 1
            if payload["next_action"] == "finished":
                completed = True
                break

        if checks is not None:
            checks.full_path(completed, asked)

        finished = await _send(
            client,
            checks,
            "report: finished",
            "POST",
            f"/api/v1/interview/sessions/{session_id}/finish",
            **_finish_kwargs(args),
        )
        if finished is None:
            return 1
        report = _decode(finished, checks, "report: finished")
        if not isinstance(report, dict):
            if checks is not None:
                checks.report(report, finished.text)
            return 1
        if checks is not None:
            checks.report(report, finished.text)
        print(
            "report:",
            json.dumps(
                {
                    "overall": report["overall_score"],
                    "dimensions": {item["key"]: item["score"] for item in report["dimensions"]},
                    "turns": len(report["turns"]),
                    "follow_ups": len([t for t in report["turns"] if t["kind"] == "follow_up"]),
                    "suggestions": report["suggestions"],
                    "summary": (report["summary"] or "")[:80],
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        again_response = await _send(
            client,
            checks,
            "report: finish is idempotent",
            "POST",
            f"/api/v1/interview/sessions/{session_id}/finish",
            **_finish_kwargs(args),
        )
        if again_response is None:
            return 1
        again = _decode(again_response, checks, "report: finish is idempotent")
        if not isinstance(again, dict):
            return 1
        idempotent = again["overall_score"] == report["overall_score"]
        print("finish idempotent:", idempotent)
        if checks is not None:
            checks.expect(
                "report: a second finish returns the same score",
                idempotent,
                detail=f"first={report['overall_score']!r} second={again['overall_score']!r}",
                raw=finished.text,
            )
            checks.persistence_checks()
            return checks.exit_code
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="interview_smoke.py",
        description=(
            "Walk the interview golden path: print it with a real vendor, "
            "or assert it with the fake one."
        ),
    )
    parser.add_argument(
        "base_url",
        nargs="?",
        default=None,
        help="entry URL (default: 8040 real, 8080 assert)",
    )
    parser.add_argument(
        "--model", dest="model_ref", default=None, help="model_ref sent with requests"
    )
    parser.add_argument(
        "--assert",
        dest="assert_mode",
        action="store_true",
        help="assert every scenario against the fake vendor; a failure exits non-zero",
    )
    parser.add_argument(
        "--expect-questions",
        type=int,
        default=CONTRACT_QUESTION_COUNT,
        help="expected main-question count in --assert mode",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="questions to request (default: 3 real, 5 assert)",
    )
    parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        choices=SCENARIO_NAMES,
        help="assert only the named scenario (repeatable; default: every scenario)",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)
    if args.assert_mode and args.model_ref != FAKE_MODEL:
        parser.error("--assert runs against the fake vendor: pass --model smoke-fake")
    if args.scenarios and not args.assert_mode:
        parser.error("--scenario only applies to --assert mode")
    if args.assert_mode and not 1 <= args.expect_questions <= QUESTION_LIMIT:
        parser.error(f"--expect-questions must be between 1 and {QUESTION_LIMIT}")
    if args.count is None:
        args.count = CONTRACT_QUESTION_COUNT if args.assert_mode else REAL_QUESTION_COUNT
    if args.base_url is None:
        args.base_url = DEFAULT_ASSERT_BASE_URL if args.assert_mode else DEFAULT_REAL_BASE_URL
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_probe = probe_db_rows if args.assert_mode else None
    return asyncio.run(run(args, db_probe=db_probe))


if __name__ == "__main__":
    raise SystemExit(main())
