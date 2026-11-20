"""Co-occurrence network tests (SPEC-012).

The rules that matter: a pair is counted once per segment, a pair has one canonical form, thin pairs are
dropped, and Jaccard never stands alone without its denominators.
"""

from __future__ import annotations

from gtaf.domain.networks import PairStat, co_occurrence, top_by_jaccard


def test_empty_corpus() -> None:
    """No segments, no pairs."""
    assert co_occurrence([]) == ()


def test_single_actor_segments_produce_no_pairs() -> None:
    """A segment mentioning one person cannot contribute an edge."""
    assert co_occurrence([["a"], ["b"], ["a"]]) == ()


def test_pair_is_counted_once_per_segment() -> None:
    """Two segments mentioning both actors is a count of two, not of the mentions inside them."""
    stats = co_occurrence([["a", "b"], ["a", "b"], ["a"]], min_segments=1)

    assert len(stats) == 1
    assert stats[0].segments == 2
    assert stats[0].a_segments == 3
    assert stats[0].b_segments == 2


def test_repeated_name_in_one_segment_is_not_extra_evidence() -> None:
    """`['a','a','b']` is one segment about both, not two observations."""
    stats = co_occurrence([["a", "a", "b"]], min_segments=1)

    assert stats[0].segments == 1


def test_no_self_pairs() -> None:
    """An actor cannot co-occur with itself."""
    assert co_occurrence([["a", "a", "a"]], min_segments=1) == ()


def test_pair_has_one_canonical_form() -> None:
    """Order of appearance must not create two rows for the same pair."""
    stats = co_occurrence([["b", "a"], ["a", "b"]], min_segments=1)

    assert len(stats) == 1
    assert (stats[0].a, stats[0].b) == ("a", "b")
    assert stats[0].segments == 2


def test_min_segments_filters_thin_pairs() -> None:
    """A pair seen once is dropped when the floor is two; a pair seen twice survives."""
    assert co_occurrence([["a", "b"], ["c", "d"]], min_segments=2) == ()
    kept = co_occurrence([["a", "b"], ["a", "b"], ["c", "d"]], min_segments=2)
    assert [(stat.a, stat.b) for stat in kept] == [("a", "b")]


def test_jaccard_uses_both_denominators() -> None:
    """`both / (a + b - both)`: a=3, b=2, both=2 → 2/3."""
    stats = co_occurrence([["a", "b"], ["a", "b"], ["a"]], min_segments=1)

    assert stats[0].jaccard == 0.667


def test_jaccard_is_one_when_always_together() -> None:
    """Two actors who only ever appear together have Jaccard 1.0."""
    stats = co_occurrence([["a", "b"], ["a", "b"]], min_segments=1)

    assert stats[0].jaccard == 1.0


def test_ordering_is_deterministic() -> None:
    """Same input, same order: no dependency on set iteration."""
    data = [["a", "b"], ["c", "d"], ["a", "b"], ["a", "c"]]
    first = co_occurrence(data, min_segments=1)
    second = co_occurrence(data, min_segments=1)

    assert [(s.a, s.b, s.segments) for s in first] == [(s.a, s.b, s.segments) for s in second]


def test_top_by_jaccard_ignores_thin_pairs() -> None:
    """A pair seen once has Jaccard 1.0 — the opposite of evidence — so it is excluded."""
    stats = (
        PairStat("a", "b", segments=1, a_segments=10, b_segments=10, jaccard=1.0),
        PairStat("c", "d", segments=6, a_segments=8, b_segments=9, jaccard=0.545),
    )
    ranked = top_by_jaccard(stats, limit=5, min_segments=3)

    assert [(stat.a, stat.b) for stat in ranked] == [("c", "d")]


def test_top_by_jaccard_orders_by_concentration() -> None:
    """Higher Jaccard first, then by shared segments."""
    stats = (
        PairStat("a", "b", segments=5, a_segments=20, b_segments=20, jaccard=0.143),
        PairStat("c", "d", segments=4, a_segments=4, b_segments=5, jaccard=0.8),
    )
    ranked = top_by_jaccard(stats, limit=2, min_segments=2)

    assert [(stat.a, stat.b) for stat in ranked] == [("c", "d"), ("a", "b")]


class FakeReader:
    """Reader with one video containing several segments."""

    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        self.rows = rows

    def list_segments(self, method: str | None = None) -> tuple[tuple[str, str], ...]:
        """Return segment text only."""
        return tuple((segment_id, text) for segment_id, _video, text in self.rows)

    def list_segments_with_video(
        self, method: str | None = None
    ) -> tuple[tuple[str, str, str], ...]:
        """Return segments with their video."""
        return tuple(self.rows)


def test_video_unit_groups_segments_of_one_broadcast() -> None:
    """Measured need (D-030): two actors usually appear in different segments of the same bulletin."""
    from gtaf.application.networks import build_network
    from gtaf.domain.actors import Actor

    first = Actor("first", "სააკაშვილი", "First")
    second = Actor("second", "კობახიძე", "Second")
    reader = FakeReader(
        [
            ("s1", "v1", "სააკაშვილი"),
            ("s2", "v1", "კობახიძე"),
            ("s3", "v2", "სააკაშვილი"),
            ("s4", "v2", "კობახიძე"),
        ]
    )

    segment_level = build_network(
        reader, (first, second), method="drift", unit="segment", min_segments=1
    )
    video_level = build_network(reader, (first, second), method="drift", unit="video", min_segments=2)

    assert segment_level.pairs == ()  # never in the same segment
    assert video_level.analysed_units == 2
    assert video_level.units_with_two_or_more == 2
    assert video_level.pairs[0].segments == 2


def test_unknown_unit_is_rejected() -> None:
    """A typo in the unit must fail loudly rather than silently analyse segments."""
    from gtaf.application.networks import build_network

    try:
        build_network(FakeReader([]), (), method="drift", unit="scene")
    except ValueError as exc:
        assert "unknown unit" in str(exc)
    else:
        raise AssertionError("expected ValueError")
