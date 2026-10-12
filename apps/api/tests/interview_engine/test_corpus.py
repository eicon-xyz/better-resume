"""T3/T4: corpus loader (loud on bad data) and skill-tag filtering (D23 / Q14 / Q19)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from better_resume.interview_engine.corpus import (
    CorpusEntry,
    CorpusError,
    filter_corpus,
    load_corpus,
)

ENTRY = {
    "id": "redis-cache-avalanche",
    "topic": "Redis",
    "question": "缓存雪崩、击穿、穿透分别是什么？各自的缓解手段是什么？",
    "source_url": "https://redis.io/docs/latest/develop/reference/client-side-caching/",
    "fetched_at": "2026-10-11",
}


def write_corpus(path: Path, entries: list[dict] | None = None, *, version: object = 1) -> Path:
    payload = {"version": version, "entries": entries if entries is not None else [ENTRY]}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def entry(entry_id: str, topic: str) -> CorpusEntry:
    return CorpusEntry(
        id=entry_id,
        topic=topic,
        question=f"{topic} 的考察题：请说明其中的原理与取舍。",
        source_url="https://example.com/reference",
        fetched_at="2026-10-11",
    )


def test_loads_a_well_formed_file(tmp_path: Path) -> None:
    path = write_corpus(tmp_path / "questions.json")

    entries = load_corpus(path)

    assert [item.id for item in entries] == ["redis-cache-avalanche"]
    assert entries[0].topic == "Redis"
    assert entries[0].fetched_at == "2026-10-11"


def test_missing_file_raises_with_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"

    with pytest.raises(CorpusError) as error:
        load_corpus(missing)

    assert str(missing) in str(error.value)


def test_corrupt_json_raises_with_the_path(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(CorpusError) as error:
        load_corpus(path)

    assert str(path) in str(error.value)


def test_entry_violating_the_schema_raises(tmp_path: Path) -> None:
    # Plain http source and no fetched_at: both are release defects, not degradations.
    bad = {
        "id": "x",
        "topic": "Redis",
        "question": "缓存穿透怎么防？",
        "source_url": "http://example.com/x",
    }
    path = write_corpus(tmp_path / "questions.json", [bad])

    with pytest.raises(CorpusError):
        load_corpus(path)


def test_unknown_version_raises(tmp_path: Path) -> None:
    path = write_corpus(tmp_path / "questions.json", version=99)

    with pytest.raises(CorpusError):
        load_corpus(path)


def test_skill_tag_selects_matching_topics() -> None:
    entries = [entry("r1", "Redis"), entry("r2", "Redis"), entry("p1", "Python")]

    picked = filter_corpus(entries, ["Redis", "FastAPI"], limit=10)

    assert [item.id for item in picked] == ["r1", "r2"]


def test_java_skill_does_not_pull_javascript() -> None:
    entries = [entry("j1", "Java"), entry("js1", "JavaScript")]

    picked = filter_corpus(entries, ["Java"], limit=10)

    assert [item.id for item in picked] == ["j1"]


def test_no_match_returns_empty_without_raising() -> None:
    entries = [entry("r1", "Redis")]

    assert filter_corpus(entries, ["COBOL"], limit=10) == []


def test_limit_keeps_file_order_and_is_stable() -> None:
    entries = [entry(f"r{index}", "Redis") for index in range(5)]

    first = filter_corpus(entries, ["Redis"], limit=2)
    second = filter_corpus(entries, ["Redis"], limit=2)

    assert [item.id for item in first] == ["r0", "r1"]
    assert [item.id for item in second] == ["r0", "r1"]


def test_common_skill_spellings_reach_their_topic() -> None:
    entries = [entry("k1", "Kafka"), entry("d1", "Docker"), entry("r1", "Redis")]

    assert [item.id for item in filter_corpus(entries, ["消息队列"], limit=5)] == ["k1"]
    assert [item.id for item in filter_corpus(entries, ["K8s"], limit=5)] == ["d1"]
    assert [item.id for item in filter_corpus(entries, ["缓存"], limit=5)] == ["r1"]


def test_non_positive_limit_returns_nothing() -> None:
    entries = [entry("r1", "Redis")]

    assert filter_corpus(entries, ["Redis"], limit=0) == []


def packaged_entries() -> list[CorpusEntry]:
    return load_corpus()


def test_the_packaged_corpus_meets_the_structure_and_quota_rules() -> None:
    from collections import Counter

    entries = packaged_entries()

    assert 100 <= len(entries) <= 150
    assert len({entry.id for entry in entries}) == len(entries)
    assert len({entry.question for entry in entries}) == len(entries)
    topics = Counter(entry.topic for entry in entries)
    assert len(topics) >= 8
    assert min(topics.values()) >= 8
    assert len({entry.source_url for entry in entries}) >= 12
    assert all(entry.source_url.startswith("https://") for entry in entries)
    assert all(entry.fetched_at for entry in entries)


def test_the_validator_reports_a_bad_corpus() -> None:
    """The checker itself must go red on known-bad input (D22)."""
    from scripts.check_corpus import MIN_ENTRIES, problems

    thin = [entry(f"id-{index}", "Redis") for index in range(MIN_ENTRIES)]
    thin[1] = entry("id-0", "Redis")  # duplicate id and duplicate question

    found = problems(thin)

    assert any("duplicate ids" in problem for problem in found)
    assert any("topics" in problem for problem in found)
    assert any("distinct sources" in problem for problem in found)


def test_the_validator_accepts_the_packaged_corpus() -> None:
    from scripts.check_corpus import problems

    assert problems(packaged_entries()) == []
