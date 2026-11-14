"""Analytical queries for the workbench (SPEC-008).

Pure SQL over a read-only connection, returning plain rows rather than DataFrames: the presentation
layer decides how to display, and these functions stay testable without Streamlit or Plotly.

Every function here is built around one rule from `TOPIC-EVAL.md` §3: **the outlier rate travels
with the numbers**. A topic share without its coverage denominator is a misleading figure, so the
queries return what is needed to state both.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from gtaf.domain.topics import OUTLIER_TOPIC_ID


class SqlCursor(Protocol):
    """Minimal cursor protocol."""

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return all remaining rows."""
        ...

    def fetchone(self) -> tuple[object, ...] | None:
        """Return the next row, or None."""
        ...


class SqlConnection(Protocol):
    """Minimal read-only connection protocol."""

    def execute(self, query: str, parameters: object | None = None) -> SqlCursor:
        """Execute a query."""
        ...


@dataclass(frozen=True, slots=True)
class CorpusOverview:
    """Headline counts for the workbench sidebar.

    Attributes:
        videos: Videos stored.
        segments: Segments stored.
        topics: Topics in the latest run, including the outlier bucket.
        first_date: Earliest broadcast date.
        last_date: Latest broadcast date.
        clusters: Channels represented.
    """

    videos: int
    segments: int
    topics: int
    first_date: date | None
    last_date: date | None
    clusters: int


@dataclass(frozen=True, slots=True)
class TopicShare:
    """One topic's size and share, with coverage stated.

    Attributes:
        topic_id: Topic identifier, ``-1`` for outliers.
        label: Georgian label — an LLM-generated name when SPEC-005 labelled the run, else a
            keyword.
        keywords: Top terms.
        n_segments: Segments in this topic.
        share: Share of **all** segments, outliers included in the denominator.
        label_en: English label when the run was labelled bilingually, else None.
    """

    topic_id: int
    label: str
    keywords: tuple[str, ...]
    n_segments: int
    share: float
    label_en: str | None = None


@dataclass(frozen=True, slots=True)
class ChannelOption:
    """A channel available for filtering.

    Attributes:
        channel_id: Slug.
        name_en: Display name.
        n_videos: Videos for this channel.
    """

    channel_id: str
    name_en: str
    n_videos: int


def _as_int(value: object) -> int:
    """Coerce a driver value (int or numeric string) to int.

    Args:
        value: Raw value from a row.

    Returns:
        The integer value.
    """
    return value if isinstance(value, int) else int(str(value))


def _as_date(value: object) -> date | None:
    """Coerce a driver value to a date, or None.

    Args:
        value: Raw value from a row.

    Returns:
        A ``date`` when the driver returned one, otherwise None.
    """
    return value if isinstance(value, date) else None


def corpus_overview(conn: SqlConnection) -> CorpusOverview:
    """Return headline counts.

    Args:
        conn: Read-only connection.

    Returns:
        Counts across the current corpus.
    """
    videos = conn.execute("SELECT count(*) FROM videos").fetchone()
    segments = conn.execute("SELECT count(*) FROM segments").fetchone()
    topics = conn.execute("SELECT count(*) FROM topics").fetchone()
    span = conn.execute(
        "SELECT min(broadcast_date_local), max(broadcast_date_local), "
        "count(DISTINCT channel_id) FROM videos"
    ).fetchone()
    return CorpusOverview(
        videos=_as_int(videos[0]) if videos else 0,
        segments=_as_int(segments[0]) if segments else 0,
        topics=_as_int(topics[0]) if topics else 0,
        first_date=_as_date(span[0]) if span else None,
        last_date=_as_date(span[1]) if span else None,
        clusters=_as_int(span[2]) if span else 0,
    )


def channel_options(conn: SqlConnection) -> tuple[ChannelOption, ...]:
    """Return channels that actually have videos, with counts.

    Args:
        conn: Read-only connection.

    Returns:
        Channels ordered by name.

    Notes:
        Only channels with videos appear. A filter offering six channels when five have data invites
        the reader to conclude the empty one broadcasts nothing.
    """
    rows = conn.execute(
        """
        SELECT c.channel_id, c.name_en, count(v.video_id) AS n
        FROM channels c
        JOIN videos v ON v.channel_id = c.channel_id
        GROUP BY 1, 2
        ORDER BY c.name_en
        """
    ).fetchall()
    return tuple(
        ChannelOption(channel_id=str(row[0]), name_en=str(row[1]), n_videos=_as_int(row[2]))
        for row in rows
    )


def topic_shares(
    conn: SqlConnection,
    *,
    channel_id: str | None = None,
    since: date | None = None,
    until: date | None = None,
) -> tuple[TopicShare, ...]:
    """Return topic sizes and shares for a filtered slice.

    Args:
        conn: Read-only connection.
        channel_id: Restrict to one channel, or None for all.
        since: Earliest broadcast date, inclusive.
        until: Latest broadcast date, inclusive.

    Returns:
        Topics ordered by size, largest first, with the outlier bucket included as its own entry.

    Notes:
        The denominator is **every segment in the slice**, not only clustered ones. A share computed
        over clustered segments alone would silently hide the 38.6 % the model could not place
        (`TOPIC-EVAL.md` §3).
    """
    clauses: list[str] = []
    parameters: list[object] = []
    if channel_id is not None:
        clauses.append("v.channel_id = ?")
        parameters.append(channel_id)
    if since is not None:
        clauses.append("v.broadcast_date_local >= ?")
        parameters.append(since)
    if until is not None:
        clauses.append("v.broadcast_date_local <= ?")
        parameters.append(until)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    total_row = conn.execute(
        f"""
        SELECT count(*)
        FROM res_topics r
        JOIN segments s ON s.segment_id = r.segment_id
        JOIN videos v ON v.video_id = s.video_id
        {where}
        """,
        parameters,
    ).fetchone()
    total = _as_int(total_row[0]) if total_row else 0
    if total == 0:
        return ()

    rows = conn.execute(
        f"""
        SELECT r.topic_id,
               coalesce(t.label_ka,
                        CASE WHEN r.topic_id = -1 THEN 'unclassified'
                             ELSE 'topic ' || r.topic_id END) AS label,
               t.label_en,
               t.keywords,
               count(*) AS n
        FROM res_topics r
        JOIN segments s ON s.segment_id = r.segment_id
        JOIN videos v ON v.video_id = s.video_id
        LEFT JOIN topics t ON t.topic_id = r.topic_id AND t.run_id = r.run_id
        {where}
        GROUP BY 1, 2, 3, 4
        ORDER BY n DESC
        """,
        parameters,
    ).fetchall()

    shares = []
    for topic_id, label, label_en, keywords, n in rows:
        raw_keywords = keywords if isinstance(keywords, (list, tuple)) else ()
        count = _as_int(n)
        shares.append(
            TopicShare(
                topic_id=_as_int(topic_id),
                label=str(label),
                keywords=tuple(str(word) for word in raw_keywords),
                n_segments=count,
                share=count / total,
                label_en=str(label_en) if label_en else None,
            )
        )
    return tuple(shares)


def topic_share_by_channel(
    conn: SqlConnection, *, channel_id: str | None = None
) -> tuple[tuple[str, int, int], ...]:
    """Return ``(channel, clustered, total)`` per channel.

    Args:
        conn: Read-only connection.
        channel_id: Restrict to one channel, or None for all.

    Returns:
        Rows ordered by channel name, for a coverage chart.

    Notes:
        This is the chart that makes the outlier rate visible per channel rather than as one global
        number, which is the point of SPEC-008 (`TOPIC-EVAL.md` §3, Q3).
    """
    where = "WHERE v.channel_id = ?" if channel_id is not None else ""
    parameters: list[object] = [OUTLIER_TOPIC_ID]
    if channel_id is not None:
        parameters.append(channel_id)
    rows = conn.execute(
        f"""
        SELECT v.channel_id,
               sum(CASE WHEN r.topic_id <> ? THEN 1 ELSE 0 END) AS clustered,
               count(*) AS total
        FROM res_topics r
        JOIN segments s ON s.segment_id = r.segment_id
        JOIN videos v ON v.video_id = s.video_id
        {where}
        GROUP BY 1
        ORDER BY 1
        """,
        parameters,
    ).fetchall()
    return tuple((str(row[0]), _as_int(row[1]), _as_int(row[2])) for row in rows)


def topic_method_versions(conn: SqlConnection) -> tuple[str, ...]:
    """Return the method versions present in the active topic assignment.

    Args:
        conn: Read-only connection.

    Returns:
        Distinct `res_topics.method_version` values, sorted. More than one means the assignment
        table mixes runs, which a report must not silently present as one result.
    """
    rows = conn.execute(
        "SELECT DISTINCT method_version FROM res_topics ORDER BY method_version"
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def segment_methods(conn: SqlConnection) -> tuple[str, ...]:
    """Return the segmentation methods present.

    Args:
        conn: Read-only connection.

    Returns:
        Distinct `segments.seg_method` values, sorted.
    """
    rows = conn.execute("SELECT DISTINCT seg_method FROM segments ORDER BY seg_method").fetchall()
    return tuple(str(row[0]) for row in rows)


def log_slice(logger: logging.Logger, **fields: object) -> None:
    """Record a filter change in the structured log.

    Args:
        logger: Target logger.
        **fields: Filter values.
    """
    logger.info("workbench.slice", extra={"fields": fields})
