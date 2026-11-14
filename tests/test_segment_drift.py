"""Drift segmentation tests (SPEC-006).

Drift segmentation cuts where the text stops being about the same thing. The domain function stays
pure
by taking a similarity series and a threshold, so these tests pin the cutting rules without a model.
"""

from __future__ import annotations

from itertools import pairwise

from gtaf.domain.normalise import Sentence
from gtaf.domain.segment import segment_by_drift


def _sentence(start: float, end: float, text: str = "ტექსტი") -> Sentence:
    """Build a sentence with a span."""
    return Sentence(start_s=start, end_s=end, text=text, turn_index=0)


def test_empty_input() -> None:
    """No sentences, no segments, no error about similarities."""
    assert segment_by_drift((), (), "v1", threshold=0.5) == ()


def test_misaligned_similarities_are_rejected() -> None:
    """A silent misalignment would cut at the wrong sentence, so it must raise."""
    sentences = (_sentence(0, 10), _sentence(10, 20))
    try:
        segment_by_drift(sentences, (0.9, 0.8), "v1", threshold=0.85)
    except ValueError as exc:
        assert "need 1 similarities" in str(exc)
    else:
        raise AssertionError("expected ValueError for misaligned similarities")


def test_drop_below_threshold_cuts_after_minimum_length() -> None:
    """A drop at 25 s splits, because both sides are long enough to stand alone.

    The tail must exceed ``min_s`` or it is merged back — that merge is a separate, intended rule,
    so
    this test keeps the tail long rather than asserting a fragment.
    """
    sentences = (_sentence(0, 10), _sentence(10, 25), _sentence(25, 45))
    segments = segment_by_drift(sentences, (0.9, 0.2), "v1", threshold=0.5)

    assert len(segments) == 2
    assert segments[0].end_s == 25
    assert segments[1].start_s == 25


def test_drop_ignored_before_minimum_length() -> None:
    """A drop two seconds in does not create a fragment."""
    sentences = (_sentence(0, 2), _sentence(2, 30))
    segments = segment_by_drift(sentences, (0.1,), "v1", threshold=0.5)

    assert len(segments) == 1


def test_flat_similarity_does_not_cut() -> None:
    """No drop means one segment, until the target length is reached."""
    sentences = tuple(_sentence(i * 10, i * 10 + 10) for i in range(4))
    segments = segment_by_drift(sentences, (0.9, 0.9, 0.9), "v1", threshold=0.5)

    assert len(segments) == 1


def test_target_length_cuts_even_without_a_drop() -> None:
    """A long uniform passage is still bounded, so segments stay comparable in size."""
    sentences = tuple(_sentence(i * 20, i * 20 + 20) for i in range(8))
    segments = segment_by_drift(sentences, tuple([0.9] * 7), "v1", threshold=0.5)

    assert len(segments) > 1


def test_max_length_is_respected() -> None:
    """No segment exceeds the ceiling."""
    sentences = tuple(_sentence(i * 30, i * 30 + 30) for i in range(10))
    segments = segment_by_drift(sentences, tuple([0.9] * 9), "v1", threshold=0.5)

    for segment in segments:
        assert segment.end_s - segment.start_s <= 150


def test_spans_tile_in_order() -> None:
    """Every sentence is used once, in order, without overlap."""
    sentences = tuple(_sentence(i * 12, i * 12 + 12) for i in range(8))
    similarities = (0.9, 0.2, 0.9, 0.9, 0.1, 0.9, 0.2)
    segments = segment_by_drift(sentences, similarities, "v1", threshold=0.5)

    assert segments[0].start_s == 0
    assert segments[-1].end_s == sentences[-1].end_s
    for previous, following in pairwise(segments):
        assert previous.end_s <= following.start_s


def test_ids_are_deterministic() -> None:
    """Re-running reproduces the same ids, so topics are not orphaned by a rebuild."""
    sentences = tuple(_sentence(i * 15, i * 15 + 15) for i in range(6))
    similarities = (0.9, 0.1, 0.9, 0.1, 0.9)
    first = segment_by_drift(sentences, similarities, "vid", threshold=0.5)
    second = segment_by_drift(sentences, similarities, "vid", threshold=0.5)

    assert [s.segment_id for s in first] == [s.segment_id for s in second]
