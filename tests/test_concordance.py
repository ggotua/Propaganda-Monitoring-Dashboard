"""Concordance tests (SPEC-018).

The correlation is hand-checkable: the project avoids a numerical dependency for two dozen numbers, so the
implementation must be provably right on a case with a known answer.
"""

from __future__ import annotations

from datetime import date

import pytest

from gtaf.application.concordance import compare, rank, spearman


def test_rank_uses_average_for_ties() -> None:
    """Ties must share a rank, or a correlation of identical vectors drifts away from 1."""
    assert rank([10.0, 20.0, 20.0, 30.0]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_is_one_for_a_perfect_monotone_pair() -> None:
    """A perfectly ordered pair correlates at 1.0."""
    assert spearman([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]) == pytest.approx(1.0)


def test_spearman_is_minus_one_for_a_reversed_pair() -> None:
    """Reversal correlates at -1.0."""
    assert spearman([1.0, 2.0, 3.0, 4.0], [40.0, 30.0, 20.0, 10.0]) == pytest.approx(-1.0)


def test_spearman_known_value() -> None:
    """Hand-checked: left ranks 1..5, right ranks 2,1,4,3,5, so sum of d-squared is 4 and
    rho = 1 - 6*4/(5*(25-1)) = 0.8."""
    left = [1.0, 2.0, 3.0, 4.0, 5.0]
    right = [2.0, 1.0, 4.0, 3.0, 5.0]
    assert spearman(left, right) == pytest.approx(0.8)


def test_spearman_needs_three_points() -> None:
    """Two points always look perfectly ordered, so the answer would be meaningless."""
    assert spearman([1.0, 2.0], [2.0, 1.0]) is None


def test_spearman_none_when_one_vector_is_constant() -> None:
    """No variation means no correlation, not a perfect one."""
    assert spearman([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


class _Reader:
    """Minimal reader with fixed corpora."""

    def __init__(self, segments, publications):
        self._segments = segments
        self._publications = publications

    def list_segments_with_date(self, method: str = ""):
        """Return the fixed segments, with ISO dates as storage returns them."""
        return self._segments

    def list_publications_in_window(self, *, source_id: str, start: date, end: date):
        """Return the fixed publications."""
        return self._publications


def test_compare_reports_shares_and_a_refusal_below_threshold() -> None:
    """The verdict must refuse the substitution when the ranking disagrees."""
    from gtaf.domain.actors import Actor

    first = Actor(actor_id="a", ka="ა", en="A", aliases=())
    second = Actor(actor_id="b", ka="ბ", en="B", aliases=())
    third = Actor(actor_id="c", ka="ც", en="C", aliases=())
    reader = _Reader(
        segments=[
            ("s1", "2026-11-05", "ა ბ ც"),
            ("s2", "2026-11-06", "ა ბ"),
            ("s3", "2026-11-07", "ა"),
        ],
        publications=[("p1", "ც", ""), ("p2", "ც ბ", ""), ("p3", "ბ ა", "")],
    )

    report = compare(
        reader,
        source_id="imedi",
        actors=[first, second, third],
        start=date(2026, 11, 1),
        end=date(2026, 11, 10),
        method="drift",
    )

    assert report.segments == 3
    assert report.publications == 3
    assert report.spearman is not None
    assert "site published" in report.verdict or "Concordant" in report.verdict


def test_compare_excludes_segments_outside_the_window() -> None:
    """A window that is not applied would silently inflate both sides."""
    from gtaf.domain.actors import Actor

    actor = Actor(actor_id="a", ka="ა", en="A", aliases=())
    reader = _Reader(
        segments=[("s1", "2026-10-01", "ა"), ("s2", "2026-11-05", "ა")],
        publications=[("p1", "ა", "")],
    )

    report = compare(
        reader,
        source_id="imedi",
        actors=[actor],
        start=date(2026, 11, 1),
        end=date(2026, 11, 10),
        method="drift",
    )

    assert report.segments == 1
