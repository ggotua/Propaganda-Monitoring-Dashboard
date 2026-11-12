"""Repository and idempotency tests against a real DuckDB file (SPEC-002 FR-3).

These are the tests that make "re-running a window must not duplicate a row" a fact rather than an
intention.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from gtaf.domain.collector import CaptionCue
from gtaf.domain.models import Channel, Programme, Video
from gtaf.infrastructure.db import connect
from gtaf.infrastructure.repository import DuckDBRepository


def _video(video_id: str = "vid1", programme_id: str | None = "imedi_news") -> Video:
    """Build a video fixture."""
    return Video(
        video_id=video_id,
        channel_id="imedi",
        programme_id=programme_id,
        published_at=datetime(2026, 11, 1, 19, 0),
        broadcast_date_local=date(2026, 11, 1),
        title="ქრონიკა 19:00",
        duration_s=1800,
        caption_kind="auto",
        caption_lang="ka",
        status="captioned",
    )


def _seed(repo: DuckDBRepository) -> None:
    """Insert the channel and programme that the video fixtures reference.

    Required because DuckDB 2.0 enforces the schema's FOREIGN KEY constraints on write — which
    corrects an earlier assumption in SPEC-001 §5.2 that `REFERENCES` was documentation only.
    """
    repo.upsert_channel(
        Channel(channel_id="imedi", name_en="Imedi", name_ka=None, youtube_handle="@tvimedi")
    )
    repo.upsert_programme(
        Programme(
            programme_id="imedi_news",
            channel_id="imedi",
            name_en="Chronicle",
            name_ka="ქრონიკა",
            type="news",
            title_patterns=("ქრონიკა",),
        )
    )


def test_video_upsert_is_idempotent(initialized_db: Path) -> None:
    """FR-3: upserting the same video twice leaves one row and one cue set."""
    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        _seed(repo)
        cues = (CaptionCue(0, 0.0, 2.0, "a"), CaptionCue(1, 2.0, 4.0, "b"))
        repo.upsert_video(_video(), cues)
        repo.upsert_video(_video(), cues)

        videos = conn.execute("SELECT count(*) FROM videos").fetchone()
        captions = conn.execute("SELECT count(*) FROM captions").fetchone()
    finally:
        conn.close()
    assert videos is not None and videos[0] == 1
    assert captions is not None and captions[0] == 2


def test_upsert_replaces_cues_rather_than_appending(initialized_db: Path) -> None:
    """A changed cue set converges instead of accumulating duplicates."""
    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        _seed(repo)
        repo.upsert_video(_video(), (CaptionCue(0, 0.0, 2.0, "a"), CaptionCue(1, 2.0, 4.0, "b")))
        repo.upsert_video(_video(), (CaptionCue(0, 0.0, 3.0, "a"),))

        rows = conn.execute("SELECT idx, end_s, text FROM captions ORDER BY idx").fetchall()
    finally:
        conn.close()
    assert rows == [(0, 3.0, "a")]


def test_channel_and_programme_upsert(initialized_db: Path) -> None:
    """Config is mirrored into the database, including array patterns."""
    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        repo.upsert_channel(
            Channel(channel_id="imedi", name_en="Imedi", name_ka="იმედი", youtube_handle="@tvimedi")
        )
        programme = Programme(
            programme_id="imedi_news",
            channel_id="imedi",
            name_en="Chronicle",
            name_ka="ქრონიკა",
            type="news",
            title_patterns=("ქრონიკა",),
        )
        repo.upsert_programme(programme)
        repo.upsert_programme(programme)

        rows = conn.execute(
            "SELECT programme_id, type, title_patterns FROM programmes"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "imedi_news"
    assert rows[0][1] == "news"
    assert list(rows[0][2]) == ["ქრონიკა"]


def test_programme_for_unknown_channel_is_rejected_by_the_database(initialized_db: Path) -> None:
    """The FOREIGN KEY rejects a programme whose channel does not exist.

    This test previously asserted the opposite (that the row was silently created), on the belief
    that DuckDB did not enforce `REFERENCES`. It does, in 2.0.0 — so the belief was wrong and the
    schema is stronger than documented.
    """
    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        repo.upsert_channel(
            Channel(channel_id="imedi", name_en="Imedi", name_ka=None, youtube_handle="@tvimedi")
        )
        with pytest.raises(duckdb.Error):
            repo.upsert_programme(
                Programme(
                    programme_id="ghost_news",
                    channel_id="ghost",
                    name_en="Ghost",
                    name_ka=None,
                    type="news",
                    title_patterns=("x",),
                )
            )
        programmes = conn.execute("SELECT count(*) FROM programmes").fetchone()
        channels = conn.execute("SELECT count(*) FROM channels").fetchone()
    finally:
        conn.close()
    assert programmes is not None and programmes[0] == 0
    assert channels is not None and channels[0] == 1


def test_has_video_reports_presence(initialized_db: Path) -> None:
    """The resumability check must not report a stored video as absent."""
    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        _seed(repo)
        assert repo.has_video("vid1") is False
        repo.upsert_video(_video(), (CaptionCue(0, 0.0, 2.0, "a"),))
        assert repo.has_video("vid1") is True
    finally:
        conn.close()


def test_run_lifecycle(initialized_db: Path) -> None:
    """A run opens as `running` and finalises with status, counts and watermark (INV-8)."""
    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        run_id = repo.start_run("collect", '{"limit": 5}')
        running = conn.execute("SELECT status, finished_at FROM runs WHERE run_id = ?",
                               [run_id]).fetchone()
        repo.finish_run(run_id, status="ok", n_items=7, watermark="2026-11-01", error=None)
        finished = conn.execute(
            "SELECT status, n_items, watermark, finished_at FROM runs WHERE run_id = ?", [run_id]
        ).fetchone()
    finally:
        conn.close()
    assert running is not None
    assert running[0] == "running"
    assert running[1] is None
    assert finished is not None
    assert finished[0] == "ok"
    assert finished[1] == 7
    assert finished[2] == "2026-11-01"
    assert finished[3] is not None
