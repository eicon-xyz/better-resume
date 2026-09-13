"""Real end-to-end interview smoke: upload a resume, answer, finish, print the report.

Needs a running API with a configured model key (BR_DEEPSEEK_API_KEY). Usage:

    uv run python scripts/interview_smoke.py [base_url]
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import sys

import httpx
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

CJK_FONT = "STSong-Light"

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
    ("Python、FastAPI、PostgreSQL、Redis、Docker", 10, False),
]

ANSWERS = [
    "我负责订单写入链路重构：先定位到写放大来自逐条 upsert，改成按主键排序的批量写入并加幂等键，"
    "P99 从 800ms 降到 120ms；补偿任务用定时扫描加去重表，线上重复写入从每天 200 条降到 0。",
    "压测用 locust 模拟峰值 3 倍流量，观察 P99、错误率和连接池等待；瓶颈在数据库连接数，"
    "把池大小和批大小做成可配并加了熔断降级，超时错误率从 1.2% 降到 0.05%。",
    "取舍上我优先保证正确性：先上幂等键再优化吞吐；代价是写入路径多一次查表，"
    "用 Redis 缓存热点键抵消，命中率 92%，整体仍是净收益。",
]


def build_resume_pdf() -> bytes:
    with contextlib.suppress(KeyError):  # already registered in this process
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


async def run(base_url: str) -> int:
    async with httpx.AsyncClient(base_url=base_url, timeout=180.0) as client:
        login = await client.post("/api/v1/auth/session", json={"user_id": "m2-smoke"})
        print("login:", login.status_code)

        session = (await client.post("/api/v1/interview/sessions", json={})).json()
        session_id = session["id"]
        print("session:", session_id, session["status"])

        generated = await client.post(
            f"/api/v1/interview/sessions/{session_id}/questions",
            files={"file": ("cv.pdf", build_resume_pdf(), "application/pdf")},
            data={"count": "3"},
        )
        generated.raise_for_status()
        batch = generated.json()
        print(
            f"questions: {len(batch['questions'])}  resume_score={batch['session']['resume_score']}"
        )
        for question in batch["questions"]:
            print(f"  {question['question_no']}. {question['text'][:60]}")

        asked = 0
        while asked < 6:
            view = (await client.get(f"/api/v1/interview/sessions/{session_id}/restore")).json()
            question_no = view["flow"]["current_question_no"]
            if question_no is None:
                break
            answer = ANSWERS[min(asked, len(ANSWERS) - 1)]
            submitted = await client.post(
                f"/api/v1/interview/sessions/{session_id}/answers",
                json={"question_no": question_no, "answer": answer, "request_id": f"smoke-{asked}"},
            )
            if submitted.status_code != 201:
                print("answer failed:", submitted.status_code, submitted.text[:200])
                return 1
            payload = submitted.json()
            print(
                f"answered {question_no}: score={payload['answer']['score']} "
                f"next={payload['next_action']} next_no={payload['next_question_no']} "
                f"reason={payload['answer']['follow_up_reason']}"
            )
            asked += 1
            if payload["next_action"] == "finished":
                break

        finished = await client.post(f"/api/v1/interview/sessions/{session_id}/finish")
        finished.raise_for_status()
        report = finished.json()
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

        again = (await client.post(f"/api/v1/interview/sessions/{session_id}/finish")).json()
        print("finish idempotent:", again["overall_score"] == report["overall_score"])
        return 0


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8040"
    raise SystemExit(asyncio.run(run(base)))
