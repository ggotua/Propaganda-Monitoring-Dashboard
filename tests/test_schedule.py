"""Pacing decision tests (SPEC-010 section 2).

The decision function reads the database and writes nothing, so these run against a real migrated
DuckDB with seeded counts.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from gtaf.application.schedule import (
    channel_totals,
    collected_today,
    next_batch,
    recent_runs,
    stale_runs,
)
from gtaf.infrastructure.db import connect
from gtaf.infrastructure.repository import DuckDBRepository

TODAY = date(2026, 12, 1)

# The schedule decides over the CONFIGURED channels, not over rows currently in the database: a
# channel never collected has no row, and reading only the database picked the best-covered channel
# first (measured 2026-11-13, five of six channels at zero videos).
CONFIGURED = (("imedi", "IMEDI"), ("gpb", "GPB"), ("postv", "POSTV"))


def _seed(initialized_db: Path, channel_counts: dict[str, int], *, today: int = 0) -> Path:
    """Create channels with N videos each, plus ``today`` videos first seen today."""
    from gtaf.domain.collector import CaptionCue
    from gtaf.domain.models import Channel, Video

    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        for channel_id, count in channel_counts.items():
            repo.upsert_channel(
                Channel(
                    channel_id=channel_id,
                    name_en=channel_id.upper(),
                    name_ka=None,
                    youtube_handle=f"@{channel_id}",
                )
            )
            for n in range(count):
                repo.upsert_video(
                    Video(
                        video_id=f"{channel_id}{n}",
                        channel_id=channel_id,
                        programme_id=None,
                        published_at=datetime(2026, 11, 1, 19, 0),
                        broadcast_date_local=date(2026, 11, 1),
                        title="t",
                        duration_s=600,
                        caption_kind="auto",
                        caption_lang="ka",
                        status="captioned",
                    ),
                    (CaptionCue(0, 0.0, 2.0, "a"),),
                )
        if today:
            # Push the first few rows' first_seen_at to TODAY, leaving the rest at the real current
            # date so the two are distinguishable.
            conn.execute(
                "UPDATE videos SET first_seen_at = ? WHERE video_id IN "
                "(SELECT video_id FROM videos LIMIT ?)",
                [datetime.combine(TODAY, datetime.min.time()), today],
            )
    finally:
        conn.close()
    return initialized_db


def test_budget_reached_means_wait(initialized_db: Path) -> None:
    """FR-2: at budget, no channel is proposed."""
    db = _seed(initialized_db, {"imedi": 3}, today=3)
    conn = connect(db, read_only=True)
    try:
        decision = next_batch(conn, CONFIGURED, budget=3, today=TODAY)
    finally:
        conn.close()

    assert decision.collect is False
    assert decision.channel_id is None
    assert "budget reached" in decision.reason


def test_least_covered_channel_is_chosen(initialized_db: Path) -> None:
    """FR-3/FR-5: the channel with fewest videos goes next, including one not yet collected."""
    db = _seed(initialized_db, {"imedi": 5, "gpb": 2})
    conn = connect(db, read_only=True)
    try:
        decision = next_batch(conn, CONFIGURED, budget=200, batch_limit=120, today=TODAY)
    finally:
        conn.close()

    assert decision.collect is True
    # postv has no rows at all, so it is the least covered and must win.
    assert decision.channel_id == "postv"


def test_limit_is_capped_by_remaining_budget(initialized_db: Path) -> None:
    """FR-4: the proposed batch never exceeds what the budget allows."""
    db = _seed(initialized_db, {"imedi": 3}, today=3)
    conn = connect(db, read_only=True)
    try:
        decision = next_batch(conn, CONFIGURED, budget=5, batch_limit=120, today=TODAY)
    finally:
        conn.close()

    assert decision.collect is True
    assert decision.limit == 2


def test_counts_are_measured(initialized_db: Path) -> None:
    """The budget is based on real first_seen_at rows, not on a counter.

    Note: seeding writes rows with the *current* UTC date, so ``TODAY`` is deliberately a different
    date. Using the real today made this test count the seeding itself — a bug this test found.
    """
    db = _seed(initialized_db, {"imedi": 4, "gpb": 1}, today=4)
    conn = connect(db, read_only=True)
    try:
        assert collected_today(conn, today=TODAY) == 4
        # The remaining row keeps the real current date, so it is not counted under TODAY.
        assert collected_today(conn) == 1
        counts = {row[0]: row[2] for row in channel_totals(conn, CONFIGURED)}
        assert counts == {"imedi": 4, "gpb": 1, "postv": 0}
    finally:
        conn.close()


def test_no_active_channels_is_not_a_collection(initialized_db: Path) -> None:
    """An empty configuration must not produce a collect decision."""
    conn = connect(initialized_db, read_only=True)
    try:
        decision = next_batch(conn, (), budget=200, today=TODAY)
    finally:
        conn.close()

    assert decision.collect is False
    assert "no active channels" in decision.reason


def test_decision_writes_nothing(initialized_db: Path) -> None:
    """FR-7: the scheduler's decision step is read-only."""
    db = _seed(initialized_db, {"imedi": 2})
    conn = connect(db, read_only=True)
    try:
        next_batch(conn, CONFIGURED, today=TODAY)
        rows = conn.execute("SELECT count(*) FROM videos").fetchone()
        runs = conn.execute("SELECT count(*) FROM runs").fetchone()
    finally:
        conn.close()

    assert rows is not None and rows[0] == 2
    assert runs is not None and runs[0] == 0


def test_stale_running_runs_are_counted(initialized_db: Path) -> None:
    """A killed process leaves a `running` row forever; the scheduler must report it, not trust
    it."""
    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        run_id = repo.start_run("collect", "{}")
        conn.execute(
            "UPDATE runs SET started_at = ? WHERE run_id = ?",
            [datetime(2026, 1, 1, 0, 0), run_id],
        )
    finally:
        conn.close()

    conn = connect(initialized_db, read_only=True)
    try:
        assert stale_runs(conn, now=datetime(2026, 1, 1, 12, 0)) == 1
        assert stale_runs(conn, now=datetime(2026, 1, 1, 1, 0)) == 0
        decision = next_batch(conn, CONFIGURED, today=TODAY)
    finally:
        conn.close()

    assert "left in 'running' state" in decision.reason


def test_recent_runs_are_newest_first(initialized_db: Path) -> None:
    """FR-6: run history is available for operations."""
    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        first = repo.start_run("collect", "{}")
        repo.finish_run(first, status="ok", n_items=5, watermark=None, error=None)
        second = repo.start_run("topics", "{}")
        repo.finish_run(second, status="failed", n_items=0, watermark=None, error="boom")
    finally:
        conn.close()

    conn = connect(initialized_db, read_only=True)
    try:
        rows = recent_runs(conn, limit=10)
    finally:
        conn.close()

    assert len(rows) == 2
    assert rows[0][1] == "topics"
    assert rows[0][2] == "failed"
    assert rows[1][1] == "collect"
