"""the interview smoke's assertion mode, driven by a mock stack (no network, no vendor)."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from scripts import interview_smoke

CATEGORIES = ("fundamentals", "project", "internship")
MAX_FOLLOW_UP = 2
QUESTION_COUNT = 5
DIMENSION_KEYS = ("accuracy", "depth", "coverage", "completeness")


SCENARIO_RESPONSES: dict[str, dict[str, Any]] = {
    "golden": {"degraded": False, "reasons": [], "warnings": [], "all_fundamentals": False},
    "no-text-layer": {
        "degraded": True,
        "reasons": ["resume_unparsable"],
        "warnings": [],
        "all_fundamentals": False,
    },
    "unmatched-corpus": {
        "degraded": True,
        "reasons": ["corpus_no_match"],
        "warnings": ["no_sections_detected", "no_contact_found"],
        "all_fundamentals": False,
    },
    "no-category": {"degraded": False, "reasons": [], "warnings": [], "all_fundamentals": True},
}

_KEEP = object()


@dataclass
class _Session:
    session_id: str
    scenario: str = "golden"
    current: str | None = None
    answered: list[str] = field(default_factory=list)
    finishes: int = 0

    @property
    def config(self) -> dict[str, Any]:
        return SCENARIO_RESPONSES.get(self.scenario, SCENARIO_RESPONSES["golden"])


class FakeStack:
    """The compose stack in miniature: the fake vendor JSON shapes, no HTTP.

    The resume filename tells the fake which scenario a session uploaded; the real engine
    turns each resume into a different response, so the fake mirrors that here.
    """

    def __init__(
        self,
        *,
        question_count: int = QUESTION_COUNT,
        follow_up_category: str | None = None,
        report_dimensions: list[dict[str, Any]] | None = None,
        answer_status: int = 201,
        answer_detail: str = "answer endpoint rejected",
        answer_rate_limited_once: bool = False,
        category_override: object = _KEEP,
        aggregate_bump: int = 0,
        thin_sample_comment: str = "样本不足",
        degradation_override: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.question_count = question_count
        self.follow_up_category = follow_up_category
        self.report_dimensions = report_dimensions
        self.answer_status = answer_status
        self.answer_detail = answer_detail
        self.answer_rate_limited_once = answer_rate_limited_once
        self.category_override = category_override
        self.aggregate_bump = aggregate_bump
        self.thin_sample_comment = thin_sample_comment
        self.degradation_override = degradation_override or {}
        self.sessions: dict[str, _Session] = {}
        self.requests: list[httpx.Request] = []
        self._sequence = 0
        self._rate_limited = False
        #: A non-zero delta makes the second finish answer with a different score.
        self.second_finish_bump = 0.0

    def main_category(self, topic: int) -> str:
        return CATEGORIES[(topic - 1) % len(CATEGORIES)]

    def _config(self, state: _Session) -> dict[str, Any]:
        config = dict(state.config)
        config.update(self.degradation_override.get(state.scenario, {}))
        return config

    def _category(self, topic: int, follow_up: bool, state: _Session) -> str | None:
        if self.category_override is not _KEEP:
            return self.category_override  # type: ignore[return-value]
        if follow_up and self.follow_up_category is not None:
            return self.follow_up_category
        if self._config(state)["all_fundamentals"]:
            return CATEGORIES[0]
        return self.main_category(topic)

    def _question_view(self, question_no: str | None, state: _Session) -> dict[str, Any] | None:
        if question_no is None:
            return None
        topic_text, _, follow_text = question_no.partition("-F")
        follow_up_index = int(follow_text) if follow_text else 0
        topic = int(topic_text)
        return {
            "question_no": question_no,
            "topic_no": topic,
            "follow_up_index": follow_up_index,
            "kind": "follow_up" if follow_up_index else "main",
            "category": self._category(topic, follow_up_index > 0, state),
            "text": f"question {question_no}",
            "focus_points": ["p"],
        }

    def _advance(self, question_no: str) -> tuple[str, str | None]:
        topic_text, _, follow_text = question_no.partition("-F")
        topic = int(topic_text)
        if not follow_text:
            return "follow_up", f"{topic}-F1"
        index = int(follow_text)
        if index < MAX_FOLLOW_UP:
            return "follow_up", f"{topic}-F{index + 1}"
        if topic < self.question_count:
            return "next_question", str(topic + 1)
        return "finished", None

    def _session(self, path: str) -> _Session:
        return self.sessions[path.split("/")[-2]]

    def _scenario_name(self, request: httpx.Request) -> str:
        marker = b"filename="
        start = request.content.find(marker)
        if start < 0:
            return "golden"
        raw = request.content[start + len(marker) :]
        if raw[:1] == b'"':
            raw = raw[1:]
        end = raw.find(b'"')
        filename = raw[:end].decode("utf-8", "replace")
        return filename[: -len(".pdf")] if filename.endswith(".pdf") else filename

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/v1/auth/session":
            return httpx.Response(201, json={"user_id": "m2-smoke"})
        if path == "/api/v1/interview/sessions" and request.method == "POST":
            self._sequence += 1
            state = _Session(session_id=f"sess-{self._sequence}")
            self.sessions[state.session_id] = state
            return httpx.Response(201, json={"id": state.session_id, "status": "draft"})
        if path.endswith("/questions"):
            state = self._session(path)
            state.scenario = self._scenario_name(request)
            state.current = "1"
            state.answered = []
            return httpx.Response(201, json=self._batch(state))
        if path.endswith("/restore"):
            return httpx.Response(
                200, json={"flow": {"current_question_no": self._session(path).current}}
            )
        if path.endswith("/answers"):
            if self.answer_status >= 400:
                return httpx.Response(self.answer_status, json={"detail": self.answer_detail})
            if self.answer_rate_limited_once and not self._rate_limited:
                self._rate_limited = True
                return httpx.Response(
                    429,
                    headers={"Retry-After": "0"},
                    json={"detail": "rate limit exceeded for answer", "bucket": "answer"},
                )
            return self._answer(request, self._session(path))
        if path.endswith("/finish"):
            state = self._session(path)
            state.finishes += 1
            return httpx.Response(201, json=self._report(state))
        return httpx.Response(404, json={"detail": f"no route for {path}"})

    def _batch(self, state: _Session) -> dict[str, Any]:
        config = self._config(state)
        return {
            "session": {
                "id": state.session_id,
                "status": "ready",
                "resume_score": 72.0,
                "resume_warnings": list(config["warnings"]),
                "degraded_reasons": list(config["reasons"]),
            },
            "questions": [
                self._question_view(str(index), state)
                for index in range(1, self.question_count + 1)
            ],
            "suggestions": ["补充量化结果"],
            "degraded": bool(config["degraded"]),
            "degraded_reasons": list(config["reasons"]),
        }

    def _answer(self, request: httpx.Request, state: _Session) -> httpx.Response:
        body = json.loads(request.content)
        question_no = body["question_no"]
        state.answered.append(question_no)
        action, next_no = self._advance(question_no)
        state.current = next_no
        return httpx.Response(
            201,
            json={
                "answer": {
                    "question_no": question_no,
                    "score": 75.0,
                    "follow_up_reason": "AI_SUGGESTED",
                },
                "next_action": action,
                "next_question_no": next_no,
                "next_question": self._question_view(next_no, state),
            },
        )

    def _report(self, state: _Session) -> dict[str, Any]:
        config = self._config(state)
        turns = [self._turn(question_no, state) for question_no in state.answered]
        categories = []
        for key in CATEGORIES:
            scored = [turn["score"] for turn in turns if turn["category"] == key]
            count = len(scored) + self.aggregate_bump
            if len(scored) < 2:
                categories.append(
                    {
                        "key": key,
                        "label": key,
                        "count": count,
                        "score": None,
                        "comment": self.thin_sample_comment,
                    }
                )
            else:
                categories.append(
                    {
                        "key": key,
                        "label": key,
                        "count": count,
                        "score": 75.0,
                        "comment": "基本掌握，细节还可以再深",
                    }
                )
        return {
            "session": {
                "id": state.session_id,
                "status": "finished",
                "resume_warnings": list(config["warnings"]),
                "degraded_reasons": list(config["reasons"]),
            },
            "overall_score": 75.0 + (self.second_finish_bump if state.finishes > 1 else 0.0),
            "dimensions": self.report_dimensions
            if self.report_dimensions is not None
            else [{"key": key, "label": key, "score": 75.0} for key in DIMENSION_KEYS],
            "categories": categories,
            "turns": turns,
            "suggestions": ["补充量化结果"],
            "summary": None,
        }

    def _turn(self, question_no: str, state: _Session) -> dict[str, Any]:
        view = self._question_view(question_no, state) or {}
        return {
            "question_no": question_no,
            "topic_no": view["topic_no"],
            "follow_up_index": view["follow_up_index"],
            "kind": view["kind"],
            "category": view["category"],
            "question": view["text"],
            "answer": "answer",
            "score": 75.0,
            "feedback": "feedback",
            "missing_points": [],
            "follow_up_reason": None,
        }


def run_smoke(
    stack: FakeStack,
    *,
    assert_mode: bool = True,
    expect_questions: int = QUESTION_COUNT,
    transport: httpx.AsyncBaseTransport | None = None,
    db_probe: Callable[[str], dict[str, Any] | None] | None = None,
    scenarios: list[str] | None = None,
) -> tuple[int, str]:
    argv: list[str] = []
    if assert_mode:
        argv += ["--model", "smoke-fake", "--assert", "--expect-questions", str(expect_questions)]
        for name in scenarios or []:
            argv += ["--scenario", name]
    argv.append("http://127.0.0.1:8080")
    args = interview_smoke.parse_args(argv)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = asyncio.run(
            interview_smoke.run(
                args, transport=transport or httpx.MockTransport(stack), db_probe=db_probe
            )
        )
    return code, output.getvalue()


def test_assert_mode_passes_the_golden_path() -> None:
    code, output = run_smoke(FakeStack())

    print("[green]")
    print(output)
    assert code == 0, output
    assert "[golden-path] upstream=smoke-fake" in output
    assert "FAIL" not in output
    assert "[golden-path] PASS  questions: contract count" in output


def test_assert_mode_is_red_when_the_expected_count_is_wrong() -> None:
    code, output = run_smoke(FakeStack(), expect_questions=4)

    print("[red: wrong count]")
    print(output)
    assert code != 0
    assert "[golden-path] FAIL  questions: contract count" in output
    assert "expected 4, got 5" in output


def test_assert_mode_names_the_step_and_shows_the_raw_body() -> None:
    stack = FakeStack(answer_status=500, answer_detail="upstream exploded")
    code, output = run_smoke(stack)

    print("[red: broken answer]")
    print(output)
    assert code != 0
    assert "[golden-path] FAIL  answer 1: submitted" in output
    assert "HTTP 500" in output
    assert "upstream exploded" in output
    assert "inspect: docker compose exec -T postgres psql" in output


def test_assert_mode_names_a_transport_failure() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    code, output = run_smoke(FakeStack(), transport=httpx.MockTransport(refuse))

    assert code != 0
    assert "FAIL  login: session created: transport error" in output


def test_follow_up_must_inherit_its_topic_category() -> None:
    code, output = run_smoke(FakeStack(follow_up_category="fundamentals"))

    assert code != 0
    assert "follow-up inherits topic" in output
    assert "follow-up category='fundamentals'" in output


def test_report_structure_is_asserted() -> None:
    code, output = run_smoke(FakeStack(report_dimensions=[]))

    assert code != 0
    assert "FAIL  report: four dimensions" in output


def test_real_mode_prints_the_report_without_asserting() -> None:
    code, output = run_smoke(FakeStack(), assert_mode=False)

    assert code == 0, output
    assert "report:" in output
    assert "finish idempotent: True" in output
    assert "[golden-path]" not in output


def test_assert_mode_requires_the_fake_vendor() -> None:
    with pytest.raises(SystemExit):
        interview_smoke.parse_args(["--assert", "http://127.0.0.1:8080"])


def test_real_mode_keeps_the_legacy_default_base_url() -> None:
    args = interview_smoke.parse_args([])
    assert args.base_url == "http://127.0.0.1:8040"
    assert args.count == 3
    assert args.assert_mode is False


def test_script_never_lets_a_proxy_swallow_loopback() -> None:
    text = Path(interview_smoke.__file__).read_text(encoding="utf-8")

    assert "trust_env=False" in text
    assert "proxy=None" in text
    assert "timeout=args.timeout" in text


def test_a_rate_limited_answer_is_retried() -> None:
    stack = FakeStack(answer_rate_limited_once=True)

    code, output = run_smoke(stack, scenarios=["golden"])

    print("[green: retried a 429]")
    print(output)
    assert code == 0, output
    assert "retry answer 1: submitted: HTTP 429" in output


def test_default_assert_mode_runs_every_scenario() -> None:
    stack = FakeStack()

    code, output = run_smoke(stack)

    print("[green: all four scenarios]")
    print(output)
    assert code == 0, output
    assert [state.scenario for state in stack.sessions.values()] == [
        "golden",
        "no-text-layer",
        "unmatched-corpus",
        "no-category",
    ]
    for name in ("golden", "no-text-layer", "unmatched-corpus", "no-category"):
        assert f"[golden-path] scenario={name}" in output


def test_a_wrong_degradation_reason_is_red() -> None:
    stack = FakeStack(
        degradation_override={"no-text-layer": {"degraded": False, "reasons": [], "warnings": []}}
    )

    code, output = run_smoke(stack, scenarios=["no-text-layer"])

    print("[red: degradation reason]")
    print(output)
    assert code != 0
    assert "FAIL  questions: degraded_reasons are explicit" in output
    assert "expected=['resume_unparsable']" in output


def test_a_wrong_resume_warning_is_red() -> None:
    stack = FakeStack(
        degradation_override={
            "unmatched-corpus": {
                "degraded": True,
                "reasons": ["corpus_no_match"],
                "warnings": [],
            }
        }
    )

    code, output = run_smoke(stack, scenarios=["unmatched-corpus"])

    print("[red: resume warnings]")
    print(output)
    assert code != 0
    assert "FAIL  questions: resume_warnings are persisted" in output
    assert "no_sections_detected" in output


def test_an_illegal_category_is_red() -> None:
    stack = FakeStack(category_override="bogus")

    code, output = run_smoke(stack, scenarios=["no-category"])

    print("[red: illegal category]")
    print(output)
    assert code != 0
    assert "FAIL  questions: every main question carries a legal category" in output
    assert "category='bogus'" in output


def test_a_category_aggregate_mismatch_is_red() -> None:
    stack = FakeStack(aggregate_bump=1)

    code, output = run_smoke(stack, scenarios=["golden"])

    print("[red: aggregate mismatch]")
    print(output)
    assert code != 0
    assert "FAIL  report: category aggregates match the turns" in output
    assert "count=" in output


def test_a_thin_category_with_the_wrong_comment_is_red() -> None:
    stack = FakeStack(thin_sample_comment="样本还行")

    code, output = run_smoke(stack, scenarios=["no-category"])

    print("[red: thin sample]")
    print(output)
    assert code != 0
    assert "FAIL  report: category aggregates match the turns" in output
    assert "thin sample" in output


def test_fixture_grounds_each_scenario() -> None:
    from better_resume.interview_engine.corpus import filter_corpus, load_corpus
    from better_resume.interview_engine.prompts import render_context
    from better_resume.resume_parser import HybridResumeParser, ResumeParseError

    parser = HybridResumeParser()

    golden = parser.parse(interview_smoke.build_resume_pdf())
    assert golden.warnings == []
    assert filter_corpus(load_corpus(None), golden.skills)
    assert interview_smoke.NO_CATEGORY_MARKER not in render_context(golden)

    with pytest.raises(ResumeParseError) as blank_error:
        parser.parse(interview_smoke.build_no_text_layer_pdf())
    assert blank_error.value.code == "text_layer_missing"

    unmatched = parser.parse(interview_smoke.build_unmatched_resume_pdf())
    assert unmatched.warnings == ["no_sections_detected", "no_contact_found"]
    assert filter_corpus(load_corpus(None), unmatched.skills) == []

    marked = parser.parse(interview_smoke.build_no_category_resume_pdf())
    assert marked.warnings == []
    assert filter_corpus(load_corpus(None), marked.skills)
    assert interview_smoke.NO_CATEGORY_MARKER in render_context(marked)


def test_degradation_codes_match_the_engine() -> None:
    from better_resume.interview_engine.question_service import CORPUS_NO_MATCH, RESUME_UNPARSABLE

    assert interview_smoke.RESUME_UNPARSABLE == RESUME_UNPARSABLE
    assert interview_smoke.CORPUS_NO_MATCH == CORPUS_NO_MATCH


def test_no_category_marker_matches_the_fake_vendor() -> None:
    from scripts import fake_openai

    assert interview_smoke.NO_CATEGORY_MARKER == fake_openai.NO_CATEGORY_MARKER


def test_real_mode_keeps_the_baseline_identity_and_filename() -> None:
    stack = FakeStack()

    code, output = run_smoke(stack, assert_mode=False)

    print("[green: real mode keeps the baseline identity and filename]")
    print(output)
    assert code == 0, output
    login = next(
        request for request in stack.requests if request.url.path == "/api/v1/auth/session"
    )
    assert json.loads(login.content) == {"user_id": "m2-smoke"}
    upload = next(request for request in stack.requests if request.url.path.endswith("/questions"))
    assert b'filename="cv.pdf"' in upload.content


def _db_snapshot(**overrides: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "degraded_reasons": [],
        "resume_warnings": [],
        "questions": [
            {
                "question_no": "1",
                "topic_no": 1,
                "follow_up_index": 0,
                "kind": "main",
                "category": "fundamentals",
            },
            {
                "question_no": "1-F1",
                "topic_no": 1,
                "follow_up_index": 1,
                "kind": "follow_up",
                "category": "fundamentals",
            },
        ],
    }
    snapshot.update(overrides)
    return snapshot


def test_a_matching_database_snapshot_is_green() -> None:
    def probe(session_id: str) -> dict[str, Any]:
        return _db_snapshot()

    code, output = run_smoke(FakeStack(), scenarios=["golden"], db_probe=probe)

    print("[green: matching database snapshot]")
    print(output)
    assert code == 0, output
    assert "[golden-path] PASS  db: session degradation is persisted" in output
    assert "[golden-path] PASS  db: question categories are legal and inherited" in output


def test_a_wrong_database_session_row_is_red() -> None:
    def probe(session_id: str) -> dict[str, Any]:
        return _db_snapshot(resume_warnings=["stale_warning"])

    code, output = run_smoke(FakeStack(), scenarios=["golden"], db_probe=probe)

    print("[red: database session row]")
    print(output)
    assert code != 0
    assert "[golden-path] FAIL  db: session degradation is persisted" in output
    assert "stale_warning" in output


def test_a_wrong_database_degraded_reason_is_red() -> None:
    def probe(session_id: str) -> dict[str, Any]:
        return _db_snapshot(degraded_reasons=["stale_reason"])

    code, output = run_smoke(FakeStack(), scenarios=["golden"], db_probe=probe)

    print("[red: database degraded reason]")
    print(output)
    assert code != 0
    assert "[golden-path] FAIL  db: session degradation is persisted" in output
    assert "stale_reason" in output


def test_a_database_follow_up_category_mismatch_is_red() -> None:
    def probe(session_id: str) -> dict[str, Any]:
        return _db_snapshot(
            questions=[
                {
                    "question_no": "1",
                    "topic_no": 1,
                    "follow_up_index": 0,
                    "kind": "main",
                    "category": "fundamentals",
                },
                {
                    "question_no": "1-F1",
                    "topic_no": 1,
                    "follow_up_index": 1,
                    "kind": "follow_up",
                    "category": "project",
                },
            ]
        )

    code, output = run_smoke(FakeStack(), scenarios=["golden"], db_probe=probe)

    print("[red: database follow-up inheritance]")
    print(output)
    assert code != 0
    assert "[golden-path] FAIL  db: question categories are legal and inherited" in output
    assert "follow-up category='project'" in output


def test_missing_docker_probe_is_reported_as_skipped() -> None:
    code, output = run_smoke(FakeStack(), scenarios=["golden"])

    print("[green: no docker probe]")
    print(output)
    assert code == 0, output
    assert "[golden-path] SKIPPED (no docker probe):" in output


def test_a_missing_session_row_from_a_working_probe_is_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_query(sql: str, session_id: str) -> list[str]:
        if sql == interview_smoke.SESSIONS_SQL:
            return []
        return ["1|1|0|main|fundamentals"]

    monkeypatch.setattr(interview_smoke, "_psql_query", fake_query)

    code, output = run_smoke(
        FakeStack(), scenarios=["golden"], db_probe=interview_smoke.probe_db_rows
    )

    print("[red: working probe, no session row]")
    print(output)
    assert code != 0, output
    assert "[golden-path] FAIL  db: session row is persisted" in output
    assert "[golden-path] SKIPPED" not in output


def test_an_unavailable_probe_is_skipped_with_the_real_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_query(sql: str, session_id: str) -> list[str] | None:
        return None

    monkeypatch.setattr(interview_smoke, "_psql_query", fake_query)

    code, output = run_smoke(
        FakeStack(), scenarios=["golden"], db_probe=interview_smoke.probe_db_rows
    )

    print("[green: probe unavailable]")
    print(output)
    assert code == 0, output
    assert "[golden-path] SKIPPED (docker/psql probe unavailable):" in output


def test_a_second_finish_with_a_different_score_is_red() -> None:
    stack = FakeStack()
    stack.second_finish_bump = 5.0

    code, output = run_smoke(stack, scenarios=["golden"])

    print("[red: second finish changes the score]")
    print(output)
    assert code != 0
    assert "[golden-path] FAIL  report: a second finish returns the same score" in output
    assert "first=75.0 second=80.0" in output


def test_real_mode_reports_a_rate_limit_retry() -> None:
    stack = FakeStack(answer_rate_limited_once=True)

    code, output = run_smoke(stack, assert_mode=False)

    print("[green: real mode reports the rate-limit retry]")
    print(output)
    assert code == 0, output
    assert "[golden-path] retry answer 1: submitted: HTTP 429" in output


def test_contract_constants_match_the_engine() -> None:
    import inspect

    from better_resume.interview_engine.categories import DISPLAY_ORDER, QuestionCategory
    from better_resume.interview_engine.flow_store import FlowStateStore
    from better_resume.interview_engine.report_service import (
        DIMENSION_LABELS,
        MIN_SCORED_PER_CATEGORY,
        THIN_SAMPLE_COMMENT,
    )

    flow_default = inspect.signature(FlowStateStore.initialize).parameters["max_follow_up"].default

    assert flow_default == interview_smoke.MAX_FOLLOW_UP
    assert tuple(item.value for item in DISPLAY_ORDER) == interview_smoke.LEGAL_CATEGORIES
    assert tuple(item.value for item in QuestionCategory) == interview_smoke.LEGAL_CATEGORIES
    assert tuple(DIMENSION_LABELS) == interview_smoke.DIMENSION_KEYS
    assert MIN_SCORED_PER_CATEGORY == interview_smoke.MIN_SCORED_PER_CATEGORY
    assert THIN_SAMPLE_COMMENT == interview_smoke.THIN_SAMPLE_COMMENT


def test_psql_query_sends_the_sql_on_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """psql -c does not interpolate :'sid'; the SQL has to ride the stdin pipe."""

    class _Result:
        returncode = 0
        stdout = ""

    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> _Result:
        calls.append((list(argv), kwargs))
        return _Result()

    class _Boundary:
        run = staticmethod(fake_run)
        SubprocessError = OSError

    class _Shutil:
        which = staticmethod(lambda _name: "/usr/bin/docker")

    monkeypatch.setattr(interview_smoke, "subprocess", _Boundary)
    monkeypatch.setattr(interview_smoke, "shutil", _Shutil)

    rows = interview_smoke._psql_query(interview_smoke.SESSIONS_SQL, "missing-id")

    assert rows == []
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert "-c" not in argv, "-c mode does not interpolate :'sid'; the SQL must not ride argv"
    assert "sid=missing-id" in argv
    assert kwargs["input"] == interview_smoke.SESSIONS_SQL
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == 30
