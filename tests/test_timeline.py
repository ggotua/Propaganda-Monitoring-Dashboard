"""Timeline tests (SPEC-015).

The rules that matter: a missing day renders as zero rather than a shorter row, shares use that day's
own denominator, and a thin series is refused a description instead of being smoothed into one.
"""

from __future__ import annotations

from gtaf.domain.timeline import pivot, reportability


def test_pivot_orders_by_total_then_key() -> None:
    """The biggest series come first, ties broken by key, so two runs agree."""
    rows = [("2026-11-01", "b", 3), ("2026-11-01", "a", 3), ("2026-11-02", "a", 1)]
    series, dates = pivot(rows, top=5)

    assert dates == ("2026-11-01", "2026-11-02")
    assert [item.key for item in series] == ["a", "b"]


def test_pivot_keeps_top_and_drops_the_rest() -> None:
    """A long tail is cut, and the cut is visible in the totals."""
    rows = [(f"day{index}", f"key{index}", index + 1) for index in range(10)]
    series, _ = pivot(rows, top=3)

    assert len(series) == 3
    assert series[0].total == 10


def test_missing_days_are_zero_filled() -> None:
    """A key absent on a date gets a 0.0 cell, so readers compare equal-length rows."""
    rows = [("2026-11-01", "a", 2), ("2026-11-03", "a", 2), ("2026-11-02", "b", 4)]
    series, dates = pivot(rows, top=5)
    by_key = {item.key: item for item in series}

    assert dates == ("2026-11-01", "2026-11-02", "2026-11-03")
    assert [cell.share for cell in by_key["a"].days] == [1.0, 0.0, 1.0]


def test_share_uses_that_day_as_denominator() -> None:
    """A busier day must not look like a spike: shares divide by that day's own total."""
    rows = [("d1", "a", 1), ("d2", "a", 5), ("d2", "b", 5)]
    series, _ = pivot(rows, top=5)
    by_key = {item.key: item for item in series}

    assert by_key["a"].days[0].share == 1.0
    assert by_key["a"].days[1].share == 0.5


def test_pivot_can_be_given_the_full_date_list() -> None:
    """Measured bug: without an explicit date list, a day with no key vanishes from the series."""
    rows = [("2026-11-01", "a", 2), ("2026-11-03", "a", 2)]
    series, dates = pivot(rows, top=5, dates=("2026-11-01", "2026-11-02", "2026-11-03"))

    assert dates == ("2026-11-01", "2026-11-02", "2026-11-03")
    assert [cell.date for cell in series[0].days] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert series[0].days[1].share == 0.0


def test_empty_input() -> None:
    """No rows, no series, no error."""
    series, dates = pivot([], top=5)
    assert series == ()
    assert dates == ()


def test_reportability_rejects_thin_days() -> None:
    """A day with a handful of segments moves shares by percentage points per segment."""
    ok, reasons = reportability(
        ("d1", "d2", "d3"), {"d1": 500, "d2": 3, "d3": 400}, min_per_day=50
    )

    assert ok is False
    assert "fewer than 50" in reasons[0]


def test_reportability_rejects_a_short_period() -> None:
    """Fewer than three points cannot show a shape."""
    ok, reasons = reportability(("d1", "d2"), {"d1": 500, "d2": 400}, min_per_day=50)

    assert ok is False
    assert "at least 3" in reasons[0]


def test_reportability_accepts_a_dense_period() -> None:
    """Enough days and enough segments per day: the series may be described."""
    dates = tuple(f"d{index}" for index in range(5))
    ok, reasons = reportability(dates, {day: 300 for day in dates})

    assert ok is True
    assert reasons == ()
