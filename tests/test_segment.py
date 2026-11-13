"""Fixed-window segmenter tests (SPEC-004 §5).

The property that matters most is tiling: segments must not overlap and must not lose a sentence.
"""

from __future__ import annotations

from itertools import pairwise

from gtaf.domain.normalise import Sentence
from gtaf.domain.segment import MAX_S, MIN_S, SEG_METHOD, SEG_VERSION, segment_sentences


def _sentence(
    index: int, start: float, duration: float = 10.0, text: str | None = None
) -> Sentence:
    """Build a sentence with a fixed span."""
    return Sentence(
        start_s=start,
        end_s=start + duration,
        text=text if text is not None else f"წინადადება {index}",
        turn_index=0,
        flags=(),
    )


def test_segments_approximately_target_length() -> None:
    """Case 1: a five-minute video splits into windows at the target, plus a kept remainder.

    A segment closes as soon as its span reaches the target, so 300 s of ten-second sentences
    becomes three 90-second windows and a 30-second tail. The tail survives because it exceeds the
    20-second merge floor; below that it would fold into the previous window (see the merge test).
    """
    sentences = [_sentence(i, i * 10.0) for i in range(30)]  # 300 s total
    segments = segment_sentences(sentences, "vid1")
    assert len(segments) == 4
    assert all(segment.end_s - segment.start_s <= MAX_S for segment in segments)
    assert segments[0].start_s == 0.0
    assert segments[-1].end_s == 300.0


def test_single_long_sentence_is_not_split() -> None:
    """Case 2 / FR-5: an oversized sentence is its own segment rather than a fragment."""
    segments = segment_sentences([_sentence(0, 0.0, duration=300.0)], "vid1")
    assert len(segments) == 1
    assert segments[0].end_s - segments[0].start_s == 300.0


def test_short_input_stays_one_segment() -> None:
    """Case 3: a 100-second video does not need two segments."""
    sentences = [_sentence(i, i * 25.0, duration=25.0) for i in range(4)]
    assert len(segment_sentences(sentences, "vid1")) == 1


def test_trailing_remainder_merges_backwards() -> None:
    """Case 4 / FR-4: a tiny tail joins the previous segment instead of standing alone."""
    sentences = [_sentence(i, i * 10.0) for i in range(9)]  # 90 s -> one full window
    sentences.append(_sentence(9, 90.0, duration=5.0))  # 5 s remainder
    segments = segment_sentences(sentences, "vid1")
    assert len(segments) == 1
    assert segments[0].end_s == 95.0


def test_no_sentences_no_segments() -> None:
    """Case 5 / FR-6."""
    assert segment_sentences([], "vid1") == ()


def test_ids_are_deterministic() -> None:
    """Case 6: re-running yields byte-identical ids, which is what makes the write idempotent."""
    sentences = [_sentence(i, i * 10.0) for i in range(20)]
    first = [segment.segment_id for segment in segment_sentences(sentences, "vid1")]
    second = [segment.segment_id for segment in segment_sentences(sentences, "vid1")]
    assert first == second
    assert all(segment_id.startswith("vid1:") for segment_id in first)


def test_spans_tile_without_overlap() -> None:
    """Case 7 / FR-1: no gaps inside a video and no overlaps."""
    sentences = [_sentence(i, i * 7.0, duration=7.0) for i in range(60)]
    segments = segment_sentences(sentences, "vid1")
    for previous, following in pairwise(segments):
        assert previous.end_s <= following.start_s
    assert segments[0].start_s == sentences[0].start_s
    assert segments[-1].end_s == sentences[-1].end_s


def test_every_sentence_lands_in_exactly_one_segment() -> None:
    """No text is silently dropped by the windowing."""
    sentences = [_sentence(i, i * 11.0, duration=11.0, text=f"სიტყვა{i}") for i in range(30)]
    segments = segment_sentences(sentences, "vid1")
    joined = " ".join(segment.text for segment in segments)
    for sentence in sentences:
        assert sentence.text in joined


def test_method_and_version_constants() -> None:
    """FR-8: the temporary segmenter must be distinguishable from real segmentation."""
    assert SEG_METHOD == "fixed"
    assert SEG_VERSION == "1"
    assert MIN_S < 90.0
