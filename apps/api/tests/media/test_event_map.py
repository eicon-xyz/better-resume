"""P8 / media-01: the update -> event rule exists once, and it covers more than one sentence."""

from __future__ import annotations

from pathlib import Path

from better_resume.media import adapters
from better_resume.media.assembler import AstTranscriptionAssembler
from better_resume.media.event_map import TranscriptEventMapper
from better_resume.media.models import AstPacket


def test_two_sentences_commit_once_each_and_never_repeat_text() -> None:
    """The rule the two adapters used to carry twice.

    The only end-to-end test for the default channel feeds a single-sentence script, so multi
    sentence slicing was not pinned anywhere: one copy could be edited and the suite stayed green.
    """
    mapper = TranscriptEventMapper()
    assembler = AstTranscriptionAssembler()
    packets = [
        AstPacket(text="我负责", seg_id=1),
        AstPacket(text="我负责了订单写入链路的重构。", seg_id=1, final=True),
        AstPacket(text="第二句话", seg_id=2),
        AstPacket(text="第二句话。", seg_id=2, final=True),
    ]

    seen: list[tuple[str, str]] = []
    for packet in packets:
        seen.extend((event.kind, event.text) for event in mapper.events(assembler.apply(packet)))

    assert seen == [
        ("replace", "我负责"),
        ("archive", "我负责了订单写入链路的重构。"),
        ("replace", "第二句话"),
        ("archive", "第二句话。"),
    ]


def test_a_repeated_final_packet_does_not_re_archive() -> None:
    """The memory half of the rule: a client must not see the same sentence twice."""
    mapper = TranscriptEventMapper()
    assembler = AstTranscriptionAssembler()
    final = AstPacket(text="我负责了订单写入链路的重构。", seg_id=1, final=True)

    first = mapper.events(assembler.apply(final))
    mapper.events(
        assembler.apply(AstPacket(text=" 我负责了订单写入链路的重构。", seg_id=1, final=True))
    )
    again = mapper.events(assembler.apply(final))

    assert [event.kind for event in first] == ["archive"]
    assert again == []


def test_the_adapters_do_not_carry_their_own_copy_again() -> None:
    """A second copy is how this started (P8 / media-01); the rule lives in event_map only."""
    directory = Path(adapters.__file__).parent

    for path in sorted(directory.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "update.committed[" not in source, f"{path.name} copied the mapping rule back in"
