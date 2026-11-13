"""Collection pacing and run history (SPEC-010).

The corpus grows in daily batches because the caption endpoint rate-limits (D-018). This module
decides *what to collect next* from the database alone — no network, no clock beyond "today", no
writes — so the policy is testable offline and the scheduled script stays trivial.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

# Measured: ~260 caption payload downloads before HTTP 429, with a cool-down longer than two hours
# (D-018). 200 leaves margin for listing requests and per-video retries.
DEFAULT_DAILY_BUDGET = 200

# One batch is deliberately smaller than the budget: a batch that hits the limit mid-channel wastes
# the remaining capacity, because the run stops rather than partially recording a channel.
DEFAULT_BATCH_LIMIT = 120


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
class Decision:
    """What the scheduler should do next.

    Attributes:
        collect: True when collection should run now.
        channel_id: Channel to collect, when ``collect`` is True.
        limit: Videos to ask for, capped by the remaining budget.
        collected_today: Videos recorded today, for the log line.
        budget: The daily budget in force.
        reason: Human-readable justification, printed verbatim.
    """

    collect: bool
    channel_id: str | None
    limit: int
    collected_today: int
    budget: int
    reason: str


def _as_int(value: object) -> int:
    """Coerce a driver value to int.

    Args:
        value: Raw value from a row.

    Returns:
        The integer value.
    """
    return value if isinstance(value, int) else int(str(value))


def collected_today(conn: SqlConnection, *, today: date | None = None) -> int:
    """Return how many videos were first stored today.

    Args:
        conn: Read-only connection.
        today: Date to count, defaulting to the current UTC date.

    Returns:
        Count of videos whose ``first_seen_at`` falls on that date.

    Notes:
        UTC is used because ``first_seen_at`` is stored as a naive UTC instant (D-009); local
        midnight would shift the budget boundary by four hours in Tbilisi.
    """
    day = today or datetime.now(UTC).date()
    row = conn.execute(
        "SELECT count(*) FROM videos WHERE CAST(first_seen_at AS DATE) = ?", [day]
    ).fetchone()
    return _as_int(row[0]) if row else 0


def channel_totals(
    conn: SqlConnection, configured: Sequence[tuple[str, str]]
) -> tuple[tuple[str, str, int], ...]:
    """Return ``(channel_id, name_en, videos)`` for every configured channel.

    Args:
        conn: Read-only connection.
        configured: ``(channel_id, name_en)`` pairs from the corpus configuration.

    Returns:
        Channels ordered by stored video count, then id, **including channels with no rows in the
        database**.

    Notes:
        The population must come from the configuration, not from the `channels` table: a channel
        that has never been collected has no row there, and reading only the database made the
        scheduler pick the best-covered channel first — measured on 2026-11-13, when five of six
        channels had zero videos.
    """
    rows = conn.execute(
        "SELECT channel_id, count(*) FROM videos GROUP BY 1"
    ).fetchall()
    counts = {str(row[0]): _as_int(row[1]) for row in rows}
    totals = [
        (channel_id, name_en, counts.get(channel_id, 0)) for channel_id, name_en in configured
    ]
    totals.sort(key=lambda item: (item[2], item[0]))
    return tuple(totals)


def stale_runs(conn: SqlConnection, *, now: datetime | None = None, hours: int = 6) -> int:
    """Count runs left in ``running`` state longer than ``hours``.

    Args:
        conn: Read-only connection.
        now: Override for the current instant, for tests.
        hours: Age beyond which a run is considered abandoned.

    Returns:
        Number of stale runs.

    Notes:
        A killed process cannot update its own run row, so the row stays `running` forever. That
        is a silent lie in the run history: measured on 2026-11-13, the killed backfill left one
        behind. The scheduler reports it rather than pretending the run is still going.
    """
    moment = now or datetime.now(UTC).replace(tzinfo=None)
    cutoff = moment - timedelta(hours=hours)
    row = conn.execute(
        "SELECT count(*) FROM runs WHERE status = 'running' AND started_at < ?", [cutoff]
    ).fetchone()
    return _as_int(row[0]) if row else 0


def next_batch(
    conn: SqlConnection,
    configured: Sequence[tuple[str, str]],
    *,
    budget: int = DEFAULT_DAILY_BUDGET,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
    today: date | None = None,
) -> Decision:
    """Decide whether to collect now, and what.

    Args:
        conn: Read-only connection.
        configured: Active ``(channel_id, name_en)`` pairs from the configuration.
        budget: Maximum videos to collect per day.
        batch_limit: Preferred batch size.
        today: Date override, for tests.

    Returns:
        The decision, including a reason suitable for a log line.

    Notes:
        Selection is round-robin **by coverage**: the least-covered configured channel goes first,
        so a multi-week backfill spreads across channels instead of exhausting one. That is what an
        agenda comparison will eventually need.
    """
    done = collected_today(conn, today=today)
    stale = stale_runs(conn)
    stale_note = f"; {stale} run(s) left in 'running' state" if stale else ""

    if done >= budget:
        return Decision(
            collect=False,
            channel_id=None,
            limit=0,
            collected_today=done,
            budget=budget,
            reason=f"daily budget reached ({done}/{budget}){stale_note}; wait for the next day",
        )

    channels = channel_totals(conn, configured)
    if not channels:
        return Decision(
            collect=False,
            channel_id=None,
            limit=0,
            collected_today=done,
            budget=budget,
            reason="no active channels configured",
        )

    channel_id, name_en, count = channels[0]
    remaining = budget - done
    limit = min(batch_limit, remaining)
    return Decision(
        collect=True,
        channel_id=channel_id,
        limit=limit,
        collected_today=done,
        budget=budget,
        reason=(
            f"{name_en} has the fewest of the configured channels ({count} videos); "
            f"{remaining} of {budget} left today{stale_note}"
        ),
    )


def recent_runs(conn: SqlConnection, *, limit: int = 20) -> tuple[tuple[object, ...], ...]:
    """Return recent runs, newest first.

    Args:
        conn: Read-only connection.
        limit: Maximum rows.

    Returns:
        Rows of ``(run_id, stage, status, started_at, n_items, watermark, error)``.
    """
    rows = conn.execute(
        """
        SELECT run_id, stage, status, started_at, n_items, watermark, error
        FROM runs ORDER BY started_at DESC LIMIT ?
        """,
        [limit],
    ).fetchall()
    return tuple(tuple(row) for row in rows)
