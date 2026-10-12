"""Validate the bundled fundamentals corpus (D23).

Structure and quotas only: the corpus is data shipped with the package, so a build that drops
the file, breaks its JSON or starves a topic must fail here rather than at question time.

Run from apps/api:
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
    """Every reason this corpus must not ship; empty means it is good to go."""
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
    except Exception as error:  # noqa: BLE001 - the loader already names the offending file
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
