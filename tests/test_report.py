"""Report rendering tests (SPEC-009).

Rendering is a pure function, so these assert the properties the spec makes non-negotiable: no
remote references, the outlier rate stated twice, escaped corpus text, and no charts when empty.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pytest

from gtaf.application import queries
from gtaf.application.report import ReportContext, build_report
from gtaf.presentation.report_html import render_html

FIXED_NOW = datetime(2026, 11, 13, 9, 0)


def _context(shares: tuple[queries.TopicShare, ...] | None = None) -> ReportContext:
    """Build a report context directly, for renderer tests."""
    default_shares = (
        queries.TopicShare(0, "სასამართლო", ("სასამართლო", "პარტია"), 2, 2 / 3),
        queries.TopicShare(-1, "unclassified", (), 1, 1 / 3),
    )
    return ReportContext(
        title="Georgian TV agenda & framing — topic report",
        generated_at=FIXED_NOW,
        channel_label="Imedi",
        since=date(2026, 11, 1),
        until=date(2026, 11, 9),
        overview=queries.CorpusOverview(3, 3, 2, date(2026, 11, 1), date(2026, 11, 9), 1),
        shares=declared if (declared := shares) is not None else default_shares,
        coverage=(("imedi", 2, 3),),
        outlier_rate=1 / 3,
        segment_methods=("fixed",),
        topic_versions=("test-1",),
    )


def test_report_is_self_contained() -> None:
    """FR-1: no resource may be loaded from a remote host.

    Plotly's inlined JavaScript contains URL strings and `href="http…"` fragments *inside the script
    body*, so the check strips script contents and asserts that the remaining markup — the part the
    browser acts on — references nothing remote.
    """
    html = render_html(_context())
    markup = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    lowered_all = html.lower()

    # SVG/namespace identifiers (xmlns="http://www.w3.org/…") and the CDN URL inside Plotly's own
    # library banner are strings, not fetches. The check is therefore for resource-bearing
    # attributes in the markup, plus a positive assertion that the chart library really is embedded.
    remote_attr = re.compile(r"""(?:src|href)\s*=\s*["']https?://""", re.IGNORECASE)
    assert not remote_attr.search(markup)
    assert "@import" not in markup.lower()
    assert "<script src" not in lowered_all
    assert "<link" not in lowered_all
    assert "cdn.plot.ly" not in markup.lower()
    assert "plotly" in lowered_all
    assert "Plotly.newPlot" in html


def test_outlier_rate_appears_in_headline_and_methodology() -> None:
    """FR-3: the caveat must not be reachable only by reading to the bottom."""
    html = render_html(_context())
    assert html.count("33.3%") >= 2


def test_machine_derived_notice_and_scope_present() -> None:
    """FR-4."""
    html = render_html(_context())
    assert "Machine-derived figures" in html
    assert "Imedi" in html
    assert "2026-11-01" in html
    assert "lang=\"en\"" in html


def test_corpus_text_is_escaped() -> None:
    """FR-6: topic labels are ASR keywords, not trusted markup."""
    hostile = (
        queries.TopicShare(0, "<script>alert(1)</script>", ("<b>bold</b>",), 1, 1.0),
    )
    html = render_html(_context(hostile))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_empty_slice_states_it_and_charts_nothing() -> None:
    """FR-5: an empty slice must not render an empty chart that reads as "nothing broadcast"."""
    empty = ReportContext(
        title="t",
        generated_at=FIXED_NOW,
        channel_label="All channels",
        since=None,
        until=None,
        overview=queries.CorpusOverview(0, 0, 0, None, None, 0),
        shares=(),
        coverage=(),
        outlier_rate=0.0,
        segment_methods=(),
        topic_versions=(),
    )
    html = render_html(empty)
    assert "No classified segments" in html
    assert "plotly" not in html.lower()


def test_render_is_deterministic() -> None:
    """FR-8: same data, same body (the timestamp is the only varying field)."""
    assert render_html(_context()) == render_html(_context())


@pytest.fixture
def populated_db(initialized_db: Path) -> Path:
    """Database with one channel, three segments and a two-topic run."""
    from gtaf.domain.collector import CaptionCue
    from gtaf.domain.models import Channel, Video
    from gtaf.domain.topics import TopicAssignment, TopicSummary
    from gtaf.infrastructure.db import connect
    from gtaf.infrastructure.repository import DuckDBRepository

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
            "('v1:0','v1',0,90,'a',NULL,NULL,'drift','1'),"
            "('v1:1','v1',90,180,'b',NULL,NULL,'drift','1'),"
            "('v1:2','v1',180,270,'c',NULL,NULL,'drift','1')"
        )
        run_id = repo.start_run("topics", "{}")
        repo.replace_topic_results(
            run_id,
            (TopicAssignment("v1:0", 0), TopicAssignment("v1:1", 0), TopicAssignment("v1:2", -1)),
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


def test_build_report_computes_the_slice(populated_db: Path) -> None:
    """FR-2: filters restrict the figures, and the outlier rate comes from the data."""
    from gtaf.infrastructure.db import connect

    conn = connect(populated_db, read_only=True)
    try:
        context = build_report(conn, channel_id="imedi", now=FIXED_NOW)
        other = build_report(conn, channel_id="gpb", now=FIXED_NOW)
    finally:
        conn.close()

    assert context.channel_label == "Imedi"
    assert context.outlier_rate == pytest.approx(1 / 3)
    assert context.segment_methods == ("drift",)
    assert context.topic_versions == ("test-1",)
    assert other.is_empty is True
