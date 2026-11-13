"""Workbench render test (SPEC-008 §7).

`AppTest` runs the actual page script headlessly, so this asserts the UI renders with real data rather
than merely importing. The database is a fixture, injected through `GTAF_DB`.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

from gtaf.infrastructure.db import connect
from gtaf.infrastructure.repository import DuckDBRepository

APP = str(Path(__file__).resolve().parents[1] / "src" / "gtaf" / "presentation" / "app.py")


@pytest.fixture
def app_db(initialized_db: Path, monkeypatch) -> Path:
    """Seed a small database and point the app at it."""
    from gtaf.domain.collector import CaptionCue
    from gtaf.domain.models import Channel, Video
    from gtaf.domain.topics import TopicAssignment, TopicSummary

    conn = connect(initialized_db)
    try:
        repo = DuckDBRepository(conn)
        repo.upsert_channel(
            Channel(channel_id="imedi", name_en="Imedi", name_ka=None, youtube_handle="@tvimedi")
        )
        repo.upsert_video(
            Video(
                video_id="v1",
                channel_id="imedi",
                programme_id=None,
                published_at=datetime(2026, 11, 1, 19, 0),
                broadcast_date_local=date(2026, 11, 1),
                title="ქრონიკა",
                duration_s=600,
                caption_kind="auto",
                caption_lang="ka",
                status="captioned",
            ),
            (CaptionCue(0, 0.0, 2.0, "a"),),
        )
        conn.execute(
            "INSERT INTO segments (segment_id, video_id, start_s, end_s, text, title_ka, title_en, "
            "seg_method, seg_version) VALUES "
            "('v1:0','v1',0,90,'a',NULL,NULL,'fixed','1'),"
            "('v1:1','v1',90,180,'b',NULL,NULL,'fixed','1'),"
            "('v1:2','v1',180,270,'c',NULL,NULL,'fixed','1')"
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

    monkeypatch.setenv("GTAF_DB", str(initialized_db))
    return initialized_db


def test_page_renders_without_error(app_db: Path) -> None:
    """The page executes and produces metrics rather than an exception."""
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()

    assert not app.exception, [str(e) for e in app.exception]
    labels = [metric.label for metric in app.metric]
    assert "Videos" in labels
    assert "Unclassified" in labels


def test_unclassified_metric_states_the_outlier_rate(app_db: Path) -> None:
    """FR-3: the outlier rate is on the page, as a metric — not only in a document."""
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()

    metric = next(m for m in app.metric if m.label == "Unclassified")
    assert metric.value == "33.3%"


def test_methodology_note_is_present(app_db: Path) -> None:
    """FR-6: the caveats live in the page, reachable without a browser trip to a wiki."""
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()

    markdown = " ".join(str(block.value) for block in app.markdown)
    assert "Methodology and caveats" in markdown or "unclassified" in markdown.lower()


def test_page_shows_an_error_when_database_is_missing(monkeypatch, tmp_path: Path) -> None:
    """A missing database must produce a legible message, not a traceback (FR-7)."""
    monkeypatch.setenv("GTAF_DB", str(tmp_path / "absent.duckdb"))
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.error or app.warning
