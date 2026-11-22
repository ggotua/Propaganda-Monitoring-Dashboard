"""Daily series over topics and actor mentions (SPEC-015).

Pure aggregation: rows of ``(date, key, count)`` in, a matrix out. The analytical caution lives in
:func:`reportability`, which refuses to call a series a trend when the corpus cannot support one — this
corpus covers eleven days, and G-4 requires three complete reporting windows for a trend claim.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DayCell:
    """One date and its share of that day's segments.

    Attributes:
        date: Broadcast date.
        share: Count divided by that day's total, so a day with more output does not look like a spike.
    """

    date: str
    share: float


@dataclass(frozen=True, slots=True)
class Series:
    """One key's daily series.

    Attributes:
        key: Topic id or actor id, as a string.
        total: Total count across the period.
        days: Cells ordered by date, including days where the key was absent (share 0.0).
    """

    key: str
    total: int
    days: tuple[DayCell, ...]


def pivot(
    rows: Iterable[tuple[str, str, int]],
    *,
    top: int = 8,
    dates: Sequence[str] | None = None,
) -> tuple[tuple[Series, ...], tuple[str, ...]]:
    """Pivot ``(date, key, count)`` rows into per-key series.

    Args:
        rows: ``(date, key, count)`` triples.
        top: How many keys to keep, by total count.
        dates: The full date list. When omitted it is derived from the rows, which **drops days where no
            key occurs** — the bug this parameter exists to prevent (measured 2026-11-22: the actor series
            showed nine days instead of ten because no known actor was mentioned on the last one).

    Returns:
        ``(series, dates)`` — series ordered by total then key, and the sorted date list.

    Notes:
        Every kept key gets a cell for **every** date, including zeros. A missing day must render as a gap
        with a zero, not as a shorter row — otherwise a reader compares lists of different lengths and sees
        a trend where there is only an absence.
    """
    totals: dict[str, int] = defaultdict(int)
    by_key: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    daily_totals: dict[str, int] = defaultdict(int)

    for day, key, count in rows:
        totals[key] += count
        by_key[key][day] += count
        daily_totals[day] += count

    resolved = (
        tuple(sorted(daily_totals)) if dates is None else tuple(sorted(dates))
    )
    kept = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:top]

    series = []
    for key, total in kept:
        cells = tuple(
            DayCell(
                date=day,
                share=(by_key[key].get(day, 0) / daily_totals[day]) if daily_totals[day] else 0.0,
            )
            for day in resolved
        )
        series.append(Series(key=key, total=total, days=cells))
    return tuple(series), resolved


def reportability(
    dates: Sequence[str],
    daily_totals: dict[str, int],
    *,
    min_per_day: int = 50,
    min_days: int = 3,
) -> tuple[bool, tuple[str, ...]]:
    """Decide whether the daily series may be described at all, and say why not.

    Args:
        dates: Dates covered.
        daily_totals: Segments per date.
        min_per_day: Thin days distort shares, because one segment can move them by percentage points.
        min_days: Fewer than three points cannot show a shape.

    Returns:
        ``(ok, reasons)`` — reasons are empty when the series is reportable.

    Notes:
        This gates **description**, not trends. A trend needs three complete reporting windows (G-4); this
        corpus has one period, so even a passing series may only be described as "what the coverage looked
        like", never as rising or falling.
    """
    reasons: list[str] = []
    thin = [day for day in dates if daily_totals.get(day, 0) < min_per_day]
    if thin:
        reasons.append(
            f"{len(thin)} day(s) have fewer than {min_per_day} segments: {', '.join(thin[:5])}"
        )
    if len(dates) < min_days:
        reasons.append(f"only {len(dates)} day(s) covered; at least {min_days} are needed for a shape")
    return (not reasons, tuple(reasons))
