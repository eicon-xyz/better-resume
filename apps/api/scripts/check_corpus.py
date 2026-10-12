"""校验随包发布的基础知识语料（D23）。

只查结构与配额：语料是随包发布的数据，所以丢文件、坏 JSON 或让某个主题挨饿的构建必须在这里
失败，而不是等到出题时才炸。

在 apps/api 下运行：
    uv run python scripts/check_corpus.py
"""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from better_resume.interview_engine.corpus import CorpusEntry, load_corpus  # noqa: E402

MIN_ENTRIES = 100
MAX_ENTRIES = 150
MIN_TOPICS = 8
MIN_PER_TOPIC = 8
MIN_SOURCES = 12


def problems(entries: Sequence[CorpusEntry]) -> list[str]:
    """这份语料不能发布的每一条理由；为空表示可以发布。"""
    found: list[str] = []
    if not MIN_ENTRIES <= len(entries) <= MAX_ENTRIES:
        found.append(f"entry count {len(entries)} is outside {MIN_ENTRIES}-{MAX_ENTRIES}")

    ids = [entry.id for entry in entries]
    duplicates = sorted({name for name, count in Counter(ids).items() if count > 1})
    if duplicates:
        found.append(f"duplicate ids: {', '.join(duplicates[:5])}")

    questions = Counter(entry.question for entry in entries)
    repeated = [text for text, count in questions.items() if count > 1]
    if repeated:
        found.append(f"duplicate questions: {repeated[0][:40]}")

    per_topic = Counter(entry.topic for entry in entries)
    if len(per_topic) < MIN_TOPICS:
        found.append(f"only {len(per_topic)} topics covered, expected at least {MIN_TOPICS}")
    thin = sorted(topic for topic, count in per_topic.items() if count < MIN_PER_TOPIC)
    if thin:
        found.append(f"topics below {MIN_PER_TOPIC} entries: {', '.join(thin)}")

    sources = {entry.source_url for entry in entries}
    if len(sources) < MIN_SOURCES:
        found.append(f"only {len(sources)} distinct sources, expected at least {MIN_SOURCES}")
    if any(not entry.source_url.startswith("https://") for entry in entries):
        found.append("every source_url must be https")

    return found


def main() -> int:
    try:
        entries = load_corpus()
    except Exception as error:  # noqa: BLE001 - loader 已点名出问题的文件
        print(f"corpus unreadable: {error}")
        return 1

    found = problems(entries)
    topics = Counter(entry.topic for entry in entries)
    sources = len({entry.source_url for entry in entries})
    print(f"entries: {len(entries)} | topics: {len(topics)} | sources: {sources}")
    print("per topic: " + ", ".join(f"{topic} {count}" for topic, count in sorted(topics.items())))
    for problem in found:
        print(f"PROBLEM: {problem}")
    if found:
        return 1
    print("corpus ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
