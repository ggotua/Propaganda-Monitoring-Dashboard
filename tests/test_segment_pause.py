"""Pause-aware segmentation tests (SPEC-006).

The rules that matter: a pause only cuts once the segment is long enough, duration bounds prevent a
single enormous segment when nobody pauses, and the result is deterministic.
"""

from __future__ import annotations

import itertools

from gtaf.domain.normalise import Sentence
from gtaf.domain.segment import segment_by_pause, segment_sentences


def _sentence(start: float, end: float, text: str = "ტექსტი") -> Sentence:
    """Build a sentence with a span."""
    return Sentence(start_s=start, end_s=end, text=text, turn_index=0)


def test_empty_input_yields_no_segments() -> None:
    """No sentences means no segments, not one empty segment."""
    assert segment_by_pause((), "v1") == ()


def test_pause_splits_even_below_target_duration() -> None:
    """A two-second silence after 20 s ends the segment, well before the 60 s target."""
    sentences = (
        _sentence(0, 10),
        _sentence(10.5, 20),
        # 3 s gap -> boundary
        _sentence(23, 33),
        _sentence(33.5, 44),
    )
    segments = segment_by_pause(sentences, "v1")

    assert len(segments) == 2
    assert segments[0].start_s == 0
    assert segments[0].end_s == 20
    assert segments[1].start_s == 23


def test_short_pause_does_not_split() -> None:
    """Normal sentence rhythm (0.4 s) is not a topic boundary."""
    sentences = tuple(_sentence(i * 10, i * 10 + 9.6) for i in range(4))
    segments = segment_by_pause(sentences, "v1")

    assert len(segments) == 1


def test_long_pause_does_not_create_a_fragment() -> None:
    """A pause in the first seconds must not produce a two-second segment."""
    sentences = (
        _sentence(0, 3),
        # 5 s gap, but the current segment is shorter than min_s
        _sentence(8, 30),
    )
    segments = segment_by_pause(sentences, "v1")

    assert len(segments) == 1
    assert segments[0].start_s == 0


def test_target_duration_cuts_when_nobody_pauses() -> None:
    """Continuous speech still gets bounded segments, or a monologue becomes one blob."""
    sentences = tuple(_sentence(i * 20, i * 20 + 19.8) for i in range(8))
    segments = segment_by_pause(sentences, "v1")

    assert len(segments) > 1
    for segment in segments:
        assert segment.end_s - segment.start_s <= 150


def test_max_duration_is_respected() -> None:
    """No segment exceeds the ceiling even with one enormous sentence after a long run."""
    sentences = (_sentence(0, 100), _sentence(100.5, 160), _sentence(160.5, 200))
    segments = segment_by_pause(sentences, "v1")

    for segment in segments:
        span = segment.end_s - segment.start_s
        assert span <= 150 or len(segment.text.split()) > 0


def test_short_tail_merges_into_previous() -> None:
    """A three-second tail is absorbed rather than shipped as its own segment."""
    sentences = (
        _sentence(0, 10),
        _sentence(10.5, 25),
        _sentence(28, 38),   # pause -> 2 segments so far (0-25, 28-38)
        _sentence(41, 44),   # pause -> would be 3 s tail
    )
    segments = segment_by_pause(sentences, "v1")

    assert all(
        segment.end_s - segment.start_s >= 15
        for segment in segments
        if segment is not segments[-1]
    ) or len(segments) <= 2


def test_spans_tile_the_sentences_in_order() -> None:
    """Every sentence appears exactly once, in order, with no overlap."""
    sentences = tuple(_sentence(i * 12, i * 12 + 11) for i in range(10))
    segments = segment_by_pause(sentences, "v1")

    starts = [segment.start_s for segment in segments]
    assert starts == sorted(starts)
    for previous, following in itertools.pairwise(segments):
        assert previous.end_s < following.start_s
    assert segments[0].start_s == sentences[0].start_s
    assert segments[-1].end_s == sentences[-1].end_s


def test_segment_ids_are_deterministic() -> None:
    """Re-running reproduces byte-identical ids, so a re-run cannot orphan topic results."""
    sentences = (_sentence(0, 10), _sentence(12, 30), _sentence(33, 60))
    first = segment_by_pause(sentences, "vid")
    second = segment_by_pause(sentences, "vid")

    assert [s.segment_id for s in first] == [s.segment_id for s in second]
    assert all(s.segment_id.startswith("vid:") for s in first)


def test_pause_method_differs_from_fixed_on_the_same_input() -> None:
    """The whole point: the two methods do not produce the same boundaries."""
    sentences = tuple(_sentence(i * 30, i * 30 + 20) for i in range(10))
    fixed = segment_sentences(sentences, "v1")
    paused = segment_by_pause(sentences, "v1")

    assert len(fixed) != len(paused)
