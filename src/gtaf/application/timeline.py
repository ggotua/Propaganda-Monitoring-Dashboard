"""Agenda dynamics use case (SPEC-015).

Two series over the same period: how topics moved day to day, and how often each known actor was
mentioned. Both are counts, so both are publishable under G-6 — provided the denominator travels and no
trend is claimed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from gtaf.domain.actors import Actor, find_mentions, title_conflict
from gtaf.domain.timeline import Series, pivot, reportability


class TimelineReader(Protocol):
    """Source of segments with their broadcast date."""

    def list_segments_with_date(
        self, method: str | None = None
    ) -> tuple[tuple[str, str, str], ...]:
        """Return ``(segment_id, date_iso, text)`` triples."""
        ...


class TopicReader(Protocol):
    """Source of topic assignments per day."""

    def topic_counts_by_day(self) -> tuple[tuple[str, str, int], ...]:
        """Return ``(date_iso, topic_id, count)`` for the latest topics run."""
        ...


@dataclass(frozen=True, slots=True)
class TimelineResult:
    """A computed timeline.

    Attributes:
        kind: ``topics`` or ``actors``.
        series: Series, largest first.
        dates: Dates covered.
        daily_totals: Segments per date.
        reportable: Whether the series may be described.
        reasons: Why not, when it may not.
    """

    kind: str
    series: tuple[Series, ...]
    dates: tuple[str, ...]
    daily_totals: dict[str, int]
    reportable: bool
    reasons: tuple[str, ...]


def topic_timeline(reader: TopicReader, *, top: int = 8) -> TimelineResult:
    """Build the per-day topic series.

    Args:
        reader: Topic source.
        top: How many topics to keep.

    Returns:
        The timeline.
    """
    rows = reader.topic_counts_by_day()
    daily: dict[str, int] = defaultdict(int)
    for day, _topic, count in rows:
        daily[day] += count
    series, dates = pivot(rows, top=top, dates=tuple(daily))
    ok, reasons = reportability(dates, dict(daily))
    return TimelineResult(
        kind="topics",
        series=series,
        dates=dates,
        daily_totals=dict(daily),
        reportable=ok,
        reasons=reasons,
    )


def actor_timeline(
    reader: TimelineReader, actors: Sequence[Actor], *, method: str, top: int = 8
) -> TimelineResult:
    """Build the per-day actor mention series.

    Args:
        reader: Segment source with dates.
        actors: Dictionary.
        method: Segmentation to analyse.
        top: How many actors to keep.

    Returns:
        The timeline.

    Notes:
        Title-conflicted segments are excluded exactly as in the actor scan (D-031), so this series and the
        mention table cannot disagree about the same corpus.
    """
    counts: dict[tuple[str, str], int] = defaultdict(int)
    daily: dict[str, int] = defaultdict(int)

    for _segment_id, day, text in reader.list_segments_with_date(method):
        daily[day] += 1
        mentions = find_mentions(text, actors)
        if not mentions:
            continue
        if any(title_conflict(text, actor) for actor in actors):
            continue
        for mention in mentions:
            counts[(day, mention.actor_id)] += 1

    rows = [(day, actor_id, count) for (day, actor_id), count in counts.items()]
    series, dates = pivot(rows, top=top, dates=tuple(daily))
    ok, reasons = reportability(dates, dict(daily))
    return TimelineResult(
        kind="actors",
        series=series,
        dates=dates,
        daily_totals=dict(daily),
        reportable=ok,
        reasons=reasons,
    )
