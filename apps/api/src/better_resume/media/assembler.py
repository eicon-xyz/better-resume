"""Sentence-pool merge: xunfei AST incremental packets -> three-level text (§4.4 port).

The old project kept this in a private inner class so the WS layer never sees pgs/rg/bg/ed.
Same boundary here: the dirty details live in this module and callers only get a
TranscriptUpdate. Rules kept from the original:

* apd appends, rpl deletes the rg interval first;
* packets **without** pgs are matched against open sentences by time overlap (>= 0.6) plus
  text evolution (common prefix >= 0.8, or one text containing the other);
* the append path merges repeated tails so a re-sent packet never duplicates words;
* final freezes a sentence: committed text is the prefix of the display text, live is the rest.
"""

from __future__ import annotations

from .models import AstPacket, PgsKind, Sentence, TranscriptUpdate

OVERLAP_THRESHOLD = 0.6
PREFIX_RATIO = 0.8
#: A single repeated character is far more often real content than a re-sent tail
#: (今天 + 天气不错 must stay 今天天气不错), so only overlaps of at least
#: MIN_OVERLAP characters count as duplicated audio.
MIN_OVERLAP = 2


def merge_overlap(existing: str, incoming: str) -> str:
    """Append incoming, dropping the repeated overlap (the old tail merge)."""
    if not existing:
        return incoming
    if not incoming:
        return existing
    if incoming in existing:
        return existing  # nothing new arrived
    if existing in incoming:
        return incoming  # the new packet supersedes the old text
    limit = min(len(existing), len(incoming))
    for size in range(limit, MIN_OVERLAP - 1, -1):
        if existing.endswith(incoming[:size]):
            return existing + incoming[size:]
    return existing + incoming


def evolves(existing: str, incoming: str) -> bool:
    """True when the two texts look like the same sentence at different moments."""
    if not existing or not incoming:
        return False
    if existing in incoming or incoming in existing:
        return True
    shared = 0
    for left, right in zip(existing, incoming, strict=False):
        if left != right:
            break
        shared += 1
    return shared / max(len(existing), len(incoming)) >= PREFIX_RATIO


def time_overlap(sentence: Sentence, packet: AstPacket) -> float:
    """Overlap ratio of the two time spans, normalised by the shorter one."""
    if sentence.bg is None or sentence.ed is None or packet.bg is None or packet.ed is None:
        return 0.0
    span_existing = sentence.ed - sentence.bg
    span_packet = packet.ed - packet.bg
    if span_existing <= 0 or span_packet <= 0:
        return 0.0
    overlap = min(sentence.ed, packet.ed) - max(sentence.bg, packet.bg)
    if overlap <= 0:
        return 0.0
    return overlap / min(span_existing, span_packet)


class SentencePool:
    """Ordered sentence store keyed by seg_id (the old TreeMap<Integer, Sentence>)."""

    def __init__(self) -> None:
        self._sentences: dict[int, Sentence] = {}

    def segment_ids(self) -> list[int]:
        return sorted(self._sentences)

    def text_of(self, seg_id: int) -> str | None:
        sentence = self._sentences.get(seg_id)
        return None if sentence is None else sentence.text

    def get(self, seg_id: int) -> Sentence | None:
        return self._sentences.get(seg_id)

    def next_segment_id(self) -> int:
        return max(self._sentences) + 1 if self._sentences else 1

    def ordered(self) -> list[Sentence]:
        return [self._sentences[seg_id] for seg_id in self.segment_ids()]

    def upsert(
        self,
        seg_id: int,
        text: str,
        *,
        bg: int | None = None,
        ed: int | None = None,
    ) -> Sentence:
        sentence = self._sentences.get(seg_id)
        if sentence is None:
            sentence = Sentence(seg_id=seg_id, text=text, bg=bg, ed=ed)
        else:
            sentence.text = text
            if bg is not None:
                sentence.bg = bg
            if ed is not None:
                sentence.ed = ed
        self._sentences[seg_id] = sentence
        return sentence

    def append(
        self, seg_id: int, text: str, *, bg: int | None = None, ed: int | None = None
    ) -> Sentence:
        existing = self._sentences.get(seg_id)
        merged = merge_overlap(existing.text, text) if existing is not None else text
        return self.upsert(seg_id, merged, bg=bg, ed=ed)

    def replace_range(self, seg_id: int, start: int, end: int, text: str) -> Sentence:
        current = self.text_of(seg_id) or ""
        left = current[: max(0, min(start, len(current)))]
        right = current[max(0, min(end, len(current))) :]
        return self.upsert(seg_id, left + text + right)

    def commit(self, seg_id: int) -> bool:
        sentence = self._sentences.get(seg_id)
        if sentence is None:
            return False
        sentence.committed = True
        return True

    def clear(self) -> None:
        self._sentences.clear()

    def display_text(self) -> str:
        return "".join(sentence.text for sentence in self.ordered())

    def committed_text(self) -> str:
        return "".join(sentence.text for sentence in self.ordered() if sentence.committed)


class AstTranscriptionAssembler:
    """Stateful merge of vendor packets; the only source of the three-level snapshot."""

    def __init__(self) -> None:
        self.pool = SentencePool()
        self._revision = 0
        self._last_display = ""

    @property
    def revision(self) -> int:
        return self._revision

    def reset(self) -> None:
        self.pool.clear()
        self._revision = 0
        self._last_display = ""

    def apply(self, packet: AstPacket) -> TranscriptUpdate:
        if not packet.text.strip():
            return self.snapshot()

        sentence = self._upsert(packet)
        if packet.final:
            self.pool.commit(sentence.seg_id)
        return self._build(segment_id=sentence.seg_id, final_packet=packet.final)

    def snapshot(self) -> TranscriptUpdate:
        return self._build(segment_id=None, final_packet=False)

    # ---- internals --------------------------------------------------------------

    def _upsert(self, packet: AstPacket) -> Sentence:
        if packet.pgs is PgsKind.APPEND:
            seg_id = packet.seg_id if packet.seg_id is not None else self.pool.next_segment_id()
            return self.pool.append(seg_id, packet.text, bg=packet.bg, ed=packet.ed)

        if packet.pgs is PgsKind.REPLACE:
            seg_id = packet.seg_id if packet.seg_id is not None else self.pool.next_segment_id()
            current = self.pool.text_of(seg_id) or ""
            start, end = packet.rg if packet.rg is not None else (0, len(current))
            return self.pool.replace_range(seg_id, start, end, packet.text)

        # No pgs: the vendor re-sent a sentence (possibly corrected). Match it before creating.
        matched = self._match_open_segment(packet)
        if matched is not None:
            return self.pool.upsert(matched.seg_id, packet.text, bg=packet.bg, ed=packet.ed)

        seg_id = packet.seg_id if packet.seg_id is not None else self.pool.next_segment_id()
        return self.pool.upsert(seg_id, packet.text, bg=packet.bg, ed=packet.ed)

    def _match_open_segment(self, packet: AstPacket) -> Sentence | None:
        for sentence in self.pool.ordered():
            if sentence.committed:
                continue
            if time_overlap(sentence, packet) >= OVERLAP_THRESHOLD and evolves(
                sentence.text, packet.text
            ):
                return sentence

        if packet.bg is None or packet.ed is None:
            # No timing information at all: only an unambiguous evolution may match.
            open_sentences = [s for s in self.pool.ordered() if not s.committed]
            if len(open_sentences) == 1 and evolves(open_sentences[0].text, packet.text):
                return open_sentences[0]
        return None

    def _build(self, *, segment_id: int | None, final_packet: bool) -> TranscriptUpdate:
        display = self.pool.display_text()
        committed = self.pool.committed_text()
        live = display[len(committed) :] if committed and display.startswith(committed) else display
        changed = display != self._last_display
        if changed:
            self._revision += 1
            self._last_display = display
        return TranscriptUpdate(
            full=display,
            display=display,
            committed=committed,
            live=live,
            revision=self._revision,
            segment_id=segment_id,
            final_packet=final_packet,
            changed=changed,
        )
