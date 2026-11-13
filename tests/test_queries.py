"""Workbench query tests (SPEC-008 FR-3…FR-5).

The rule under test is the one from TOPIC-EVAL §3: a share is computed over **every** segment in the
slice, so the outlier rate cannot be hidden. Queries are tested against a real migrated DuckDB.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from gtaf.application import queries
from gtaf.infrastructure.db import connect
from gtaf.infrastructure.repository import DuckDBRepository


@pytest.fixture
def populated_db(initialized_db: Path) -> Path:
    """A database with one channel, one video, three segments and a two-topic run."""
    from gtaf.domain.collector import CaptionCue
    from gtaf.domain.models import Channel, Programme, Video
    from gtaf.domain.topics import TopicAssignment, TopicSummary

    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        repo.upsert_channel(
            Channel(channel_id="imedi", name_en="Imedi", name_ka=None, youtube_handle="@tvimedi")
        )
        repo.upsert_channel(
            Channel(channel_id="gpb", name_en="GPB", name_ka=None, youtube_handle="@gpb")
        )
        repo.upsert_programme(
            Programme(
                programme_id="imedi_news",
                channel_id="imedi",
                name_en="News",
                name_ka=None,
                type="news",
                title_patterns=("ქრონიკა",),
            )
        )
        repo.upsert_video(
            Video(
                video_id="v1",
                channel_id="imedi",
                programme_id="imedi_news",
                published_at=datetime(2026, 11, 1, 19, 0),
                broadcast_date_local=date(2026, 11, 1),
                title="ქრონიკა",
                duration_s=1800,
                caption_kind="auto",
                caption_lang="ka",
                status="captioned",
            ),
            (CaptionCue(0, 0.0, 2.0, "a"),),
        )
        conn.execute(
            "INSERT INTO segments (segment_id, video_id, start_s, end_s, text, title_ka, title_en, "
            "seg_method, seg_version) VALUES "
            "('v1:0', 'v1', 0, 90, 'text a', NULL, NULL, 'fixed', '1'), "
            "('v1:1', 'v1', 90, 180, 'text b', NULL, NULL, 'fixed', '1'), "
            "('v1:2', 'v1', 180, 270, 'text c', NULL, NULL, 'fixed', '1')"
        )
        run_id = repo.start_run("topics", "{}")
        repo.replace_topic_results(
            run_id,
            (
                TopicAssignment("v1:0", 0),
                TopicAssignment("v1:1", 0),
                TopicAssignment("v1:2", -1),
            ),
            (
                TopicSummary(0, "სასამართლო", None, ("სასამართლო",), 2),
                TopicSummary(-1, "unclassified", None, (), 1),
            ),
            "test-1",
        )
        repo.finish_run(run_id, status="ok", n_items=3, watermark=None, error=None)
    finally:
        conn.close()
    return initialized_db


def test_overview_counts(populated_db: Path) -> None:
    """FR-1: headline counts come straight from the tables."""
    conn = connect(populated_db, read_only=True)
    try:
        overview = queries.corpus_overview(conn)
    finally:
        conn.close()
    assert overview.videos == 1
    assert overview.segments == 3
    assert overview.topics == 2  # one real topic plus the outlier bucket
    assert overview.first_date == date(2026, 11, 1)
    assert overview.clusters == 1


def test_only_channels_with_videos_are_offered(populated_db: Path) -> None:
    """A channel with no videos must not appear: an empty option reads as "broadcasts nothing"."""
    conn = connect(populated_db, read_only=True)
    try:
        options = queries.channel_options(conn)
    finally:
        conn.close()
    assert [option.channel_id for option in options] == ["imedi"]
    assert options[0].n_videos == 1


def test_topic_shares_include_outliers_in_denominator(populated_db: Path) -> None:
    """FR-4: shares are over all segments, and the outlier bucket is its own entry."""
    conn = connect(populated_db, read_only=True)
    try:
        shares = queries.topic_shares(conn)
    finally:
        conn.close()

    by_id = {share.topic_id: share for share in shares}
    assert by_id[0].n_segments == 2
    assert by_id[-1].n_segments == 1
    assert by_id[0].share == pytest.approx(2 / 3)
    assert by_id[-1].share == pytest.approx(1 / 3)
    # Nowhere near 1.0 only if outliers were excluded; with them included the shares sum to 1.
    assert sum(share.share for share in shares) == pytest.approx(1.0)


def test_shares_respect_channel_filter(populated_db: Path) -> None:
    """FR-2: a filter restricts every figure."""
    conn = connect(populated_db, read_only=True)
    try:
        assert queries.topic_shares(conn, channel_id="imedi")
        assert queries.topic_shares(conn, channel_id="gpb") == ()
    finally:
        conn.close()


def test_empty_slice_returns_nothing(populated_db: Path) -> None:
    """FR-5: an out-of-range date must yield no rows, so the UI can say "no data"."""
    conn = connect(populated_db, read_only=True)
    try:
        shares = queries.topic_shares(conn, since=date(2027, 1, 1))
    finally:
        conn.close()
    assert shares == ()


def test_coverage_by_channel(populated_db: Path) -> None:
    """FR-3: the per-channel chart must expose clustered vs total for each channel."""
    conn = connect(populated_db, read_only=True)
    try:
        rows = queries.topic_share_by_channel(conn)
    finally:
        conn.close()
    assert rows == (("imedi", 2, 3),)
