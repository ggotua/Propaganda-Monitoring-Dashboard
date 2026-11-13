"""Report model (SPEC-009).

Builds a plain, renderer-agnostic description of a report from the same queries the workbench uses,
so the report and the page cannot disagree. No HTML here, and no I/O beyond the database read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from gtaf.application import queries
from gtaf.domain.topics import OUTLIER_TOPIC_ID


@dataclass(frozen=True, slots=True)
class ReportContext:
    """Everything a report needs, already computed.

    Attributes:
        title: Report title.
        generated_at: UTC timestamp of generation (the only non-deterministic field).
        channel_label: Channel name, or "All channels".
        since: Slice start, or None.
        until: Slice end, or None.
        overview: Corpus counts.
        shares: Topic shares for the slice, outliers included.
        coverage: ``(channel, clustered, total)`` rows.
        outlier_rate: Share of segments unclassified in this slice.
        segment_methods: Segmentation methods present, for the methodology block.
        topic_versions: Topic method versions present.
    """

    title: str
    generated_at: datetime
    channel_label: str
    since: date | None
    until: date | None
    overview: queries.CorpusOverview
    shares: tuple[queries.TopicShare, ...]
    coverage: tuple[tuple[str, int, int], ...]
    outlier_rate: float
    segment_methods: tuple[str, ...]
    topic_versions: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        """True when the slice has no classified segments."""
        return not self.shares


def build_report(
    conn: queries.SqlConnection,
    *,
    channel_id: str | None = None,
    since: date | None = None,
    until: date | None = None,
    now: datetime | None = None,
) -> ReportContext:
    """Assemble a report for a slice.

    Args:
        conn: Read-only connection.
        channel_id: Restrict to one channel, or None for all.
        since: Earliest broadcast date, inclusive.
        until: Latest broadcast date, inclusive.
        now: Generation timestamp, injectable so tests are deterministic.

    Returns:
        A fully computed report context.

    Notes:
        Topic shares are ordered by size then by topic id, so two runs over the same data produce
        the same body (SPEC-009 FR-8); only ``generated_at`` varies.
    """
    overview = queries.corpus_overview(conn)
    channels = queries.channel_options(conn)
    channel_label = "All channels"
    if channel_id is not None:
        channel_label = next(
            (option.name_en for option in channels if option.channel_id == channel_id), channel_id
        )

    shares = queries.topic_shares(conn, channel_id=channel_id, since=since, until=until)
    shares = tuple(sorted(shares, key=lambda share: (-share.share, share.topic_id)))
    outlier = next(
        (share for share in shares if share.topic_id == OUTLIER_TOPIC_ID), None
    )

    return ReportContext(
        title="Georgian TV agenda & framing — topic report",
        generated_at=now or datetime.now(),
        channel_label=channel_label,
        since=since,
        until=until,
        overview=overview,
        shares=shares,
        coverage=queries.topic_share_by_channel(conn, channel_id=channel_id),
        outlier_rate=outlier.share if outlier else 0.0,
        segment_methods=queries.segment_methods(conn),
        topic_versions=queries.topic_method_versions(conn),
    )
