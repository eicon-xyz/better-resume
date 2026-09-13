"""M4-T1: sentence-pool merge (AstTranscriptionAssembler ported from the old Java class).

Input: xunfei-style incremental packets (seg_id / pgs apd|rpl / rg / bg / ed / final).
Output: the three-level snapshot (full / committed / live) plus a monotonic revision.
"""

from __future__ import annotations

import pytest

from better_resume.media import AstPacket, AstTranscriptionAssembler, PgsKind, SentencePool


@pytest.fixture
def assembler() -> AstTranscriptionAssembler:
    return AstTranscriptionAssembler()


def packet(text: str, **kwargs: object) -> AstPacket:
    return AstPacket(text=text, **kwargs)  # type: ignore[arg-type]


def test_append_grows_the_sentence_and_keeps_committed_empty(
    assembler: AstTranscriptionAssembler,
) -> None:
    first = assembler.apply(packet("今天", seg_id=1, pgs=PgsKind.APPEND))
    second = assembler.apply(packet("天气不错", seg_id=1, pgs=PgsKind.APPEND))

    assert first.display == "今天"
    assert first.committed == ""
    assert first.live == "今天"
    assert second.display == "今天天气不错"
    assert second.live == second.display
    assert second.revision > first.revision


def test_append_creates_the_segment_when_unknown(assembler: AstTranscriptionAssembler) -> None:
    update = assembler.apply(packet("新段", seg_id=7, pgs=PgsKind.APPEND))

    assert update.segment_id == 7
    assert assembler.pool.segment_ids() == [7]


def test_replace_removes_the_range_then_writes(assembler: AstTranscriptionAssembler) -> None:
    assembler.apply(packet("你好世界", seg_id=1, pgs=PgsKind.APPEND))
    update = assembler.apply(packet("地球", seg_id=1, pgs=PgsKind.REPLACE, rg=(2, 4)))

    assert update.display == "你好地球"


def test_replace_clamps_out_of_range_indexes(assembler: AstTranscriptionAssembler) -> None:
    assembler.apply(packet("短", seg_id=1, pgs=PgsKind.APPEND))

    update = assembler.apply(packet("很长的一段文本", seg_id=1, pgs=PgsKind.REPLACE, rg=(0, 999)))

    assert update.display == "很长的一段文本"


def test_replace_without_rg_replaces_the_whole_segment(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("旧文本", seg_id=1, pgs=PgsKind.APPEND))

    update = assembler.apply(packet("新文本", seg_id=1, pgs=PgsKind.REPLACE))

    assert update.display == "新文本"


def test_time_overlap_and_prefix_evolution_reuse_the_same_segment(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("我负责了订单", seg_id=1, bg=0, ed=1000))
    update = assembler.apply(packet("我负责了订单写入链路", bg=100, ed=1100))

    assert assembler.pool.segment_ids() == [1]
    assert update.display == "我负责了订单写入链路"


def test_low_time_overlap_creates_a_new_segment(assembler: AstTranscriptionAssembler) -> None:
    assembler.apply(packet("第一句很长的一句话", seg_id=1, bg=0, ed=2000))
    update = assembler.apply(packet("第二句很长的一句话", bg=5000, ed=7000))

    assert assembler.pool.segment_ids() == [1, 2]
    assert update.display == "第一句很长的一句话第二句很长的一句话"


def test_unrelated_text_creates_a_new_segment_even_with_overlap(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("我负责了订单写入", seg_id=1, bg=0, ed=1000))
    update = assembler.apply(packet("完全不同的另一句话", bg=100, ed=1100))

    assert assembler.pool.segment_ids() == [1, 2]
    assert update.display.endswith("完全不同的另一句话")


def test_one_packet_containing_the_other_counts_as_evolution(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("压测用 locust 模拟峰值", seg_id=1, bg=0, ed=1000))
    update = assembler.apply(packet("压测用 locust", bg=0, ed=900))

    assert assembler.pool.segment_ids() == [1]
    assert update.display == "压测用 locust"


def test_missing_times_fall_back_to_the_open_segment(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("没有时间戳的第一段", seg_id=1))
    update = assembler.apply(packet("没有时间戳的第一段继续"))

    assert assembler.pool.segment_ids() == [1]
    assert update.display == "没有时间戳的第一段继续"


def test_suffix_merge_avoids_duplicated_words(assembler: AstTranscriptionAssembler) -> None:
    assembler.apply(packet("今天天气", seg_id=1, pgs=PgsKind.APPEND))
    update = assembler.apply(packet("天气不错", seg_id=1, pgs=PgsKind.APPEND))

    assert update.display == "今天天气不错"


def test_suffix_merge_handles_full_containment(assembler: AstTranscriptionAssembler) -> None:
    assembler.apply(packet("你好", seg_id=1, pgs=PgsKind.APPEND))
    update = assembler.apply(packet("你好世界", seg_id=1, pgs=PgsKind.APPEND))

    assert update.display == "你好世界"


def test_final_commits_the_segment_and_live_drops_it(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("第一句", seg_id=1, pgs=PgsKind.APPEND))
    update = assembler.apply(packet("第一句。", seg_id=1, final=True))

    assert update.committed == "第一句。"
    assert update.live == ""
    assert update.final_packet is True
    assert update.display == "第一句。"


def test_committed_text_stays_while_the_next_segment_streams(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("第一句。", seg_id=1, final=True))
    update = assembler.apply(packet("第二句正在说", seg_id=2, pgs=PgsKind.APPEND))

    assert update.committed == "第一句。"
    assert update.live == "第二句正在说"
    assert update.display == "第一句。第二句正在说"


def test_out_of_order_segments_are_rendered_by_segment_id(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("第二段", seg_id=2, pgs=PgsKind.APPEND))
    update = assembler.apply(packet("第一段", seg_id=1, pgs=PgsKind.APPEND))

    assert update.display == "第一段第二段"


def test_revision_is_monotonic_and_duplicate_packets_do_not_bump_it(
    assembler: AstTranscriptionAssembler,
) -> None:
    first = assembler.apply(packet("重复", seg_id=1, pgs=PgsKind.APPEND))
    again = assembler.apply(packet("重复", seg_id=1, pgs=PgsKind.APPEND))

    assert again.revision == first.revision
    assert again.changed is False

    third = assembler.apply(packet("重复内容", seg_id=1, pgs=PgsKind.APPEND))
    assert third.revision > first.revision
    assert third.changed is True


def test_empty_and_whitespace_packets_change_nothing(
    assembler: AstTranscriptionAssembler,
) -> None:
    before = assembler.snapshot()
    after = assembler.apply(packet(""))
    spaces = assembler.apply(packet("   "))

    assert after.display == before.display == ""
    assert after.revision == before.revision
    assert spaces.revision == before.revision
    assert assembler.pool.segment_ids() == []


def test_punctuation_only_packet_is_kept(assembler: AstTranscriptionAssembler) -> None:
    update = assembler.apply(packet("。", seg_id=1, final=True))

    assert update.display == "。"
    assert update.committed == "。"


def test_append_after_final_keeps_the_segment_committed(
    assembler: AstTranscriptionAssembler,
) -> None:
    assembler.apply(packet("已经定稿", seg_id=1, final=True))
    update = assembler.apply(packet("的补充", seg_id=1, pgs=PgsKind.APPEND))

    assert update.committed == "已经定稿的补充"
    assert update.live == ""


def test_reset_clears_the_pool_and_the_revision(assembler: AstTranscriptionAssembler) -> None:
    assembler.apply(packet("有内容", seg_id=1, pgs=PgsKind.APPEND))

    assembler.reset()

    snapshot = assembler.snapshot()
    assert snapshot.display == ""
    assert snapshot.revision == 0
    assert assembler.pool.segment_ids() == []


def test_three_segments_accumulate_in_order(assembler: AstTranscriptionAssembler) -> None:
    for index, text in enumerate(["一。", "二。", "三。"], start=1):
        assembler.apply(packet(text, seg_id=index, final=True))

    snapshot = assembler.snapshot()
    assert snapshot.committed == "一。二。三。"
    assert snapshot.live == ""
    assert snapshot.display == "一。二。三。"


def test_pool_helpers_are_stable(assembler: AstTranscriptionAssembler) -> None:
    pool: SentencePool = assembler.pool
    assembler.apply(packet("内容", seg_id=3, pgs=PgsKind.APPEND))

    assert pool.segment_ids() == [3]
    assert pool.text_of(3) == "内容"
    assert pool.text_of(99) is None
    assert pool.commit(99) is False
