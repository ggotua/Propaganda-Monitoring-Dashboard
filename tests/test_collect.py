"""Collector use-case tests against fakes (SPEC-002 §9 cases 1, 2, 9-14).

No test here touches the network: the use case depends only on the three protocols, which is the
point of the layering (D-004).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

import pytest

from gtaf.application.collect import (
    ChannelReport,
    ClientBlockedError,
    CollectPlan,
    FetchedVideo,
    VideoUnavailableError,
    run_collection,
)
from gtaf.domain.collector import CaptionCue, UploadRef, VideoMeta
from gtaf.domain.models import Channel, Programme, Video
from gtaf.infrastructure.raw_store import FileRawStore

LOGGER = logging.getLogger("test.collect")


def _channel(channel_id: str = "imedi", handle: str = "@tvimedi") -> Channel:
    """Build a channel fixture."""
    return Channel(channel_id=channel_id, name_en=channel_id.title(), name_ka=None,
                   youtube_handle=handle)


def _news_programme(channel_id: str = "imedi") -> Programme:
    """Build a news programme fixture matching `ქრონიკა`."""
    return Programme(
        programme_id=f"{channel_id}_news",
        channel_id=channel_id,
        name_en="News",
        name_ka=None,
        type="news",
        title_patterns=("ქრონიკა",),
    )


def _fetched(
    video_id: str,
    *,
    title: str = "ქრონიკა 19:00",
    published: datetime | None = datetime(2026, 11, 1, 19, 0),
    manual: tuple[str, ...] = (),
    auto: tuple[str, ...] = ("ka",),
    raw: str | None = '{"events": []}',
    cues: tuple[CaptionCue, ...] = (CaptionCue(0, 0.0, 2.0, "hello"),),
) -> FetchedVideo:
    """Build a fetched-video fixture."""
    return FetchedVideo(
        meta=VideoMeta(
            video_id=video_id,
            title=title,
            published_at=published,
            duration_s=1800,
            manual_langs=manual,
            auto_langs=auto,
        ),
        raw_payload=raw if auto or manual else None,
        cues=cues if auto or manual else (),
    )


class FakeSource:
    """Video source returning fixtures, or raising the exception given per video id."""

    def __init__(self, uploads: list[UploadRef], results: dict[str, object]) -> None:
        self.uploads = uploads
        self.results = results
        self.fetched: list[str] = []

    def list_uploads(self, handle: str, limit: int) -> Sequence[UploadRef]:
        """Return the fixtures, capped."""
        return self.uploads[:limit]

    def fetch_video(self, video_id: str) -> FetchedVideo:
        """Return the fixture or raise the configured exception."""
        self.fetched.append(video_id)
        result = self.results[video_id]
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, FetchedVideo)
        return result


class FakeRepo:
    """Repository recording every call."""

    def __init__(self) -> None:
        self.channel_ids: list[str] = []
        self.programme_ids: list[str] = []
        self.videos: dict[str, tuple[Video, int]] = {}
        self.existing: set[str] = set()
        self.runs: dict[str, dict[str, object]] = {}
        self.finished: list[str] = []

    def upsert_channel(self, channel: Channel) -> None:
        """Record a channel upsert."""
        self.channel_ids.append(channel.channel_id)

    def upsert_programme(self, programme: Programme) -> None:
        """Record a programme upsert."""
        self.programme_ids.append(programme.programme_id)

    def upsert_video(self, video: Video, cues: Sequence[CaptionCue]) -> None:
        """Record a video upsert with its cue count."""
        self.videos[video.video_id] = (video, len(cues))

    def has_video(self, video_id: str) -> bool:
        """Report whether the video was already recorded."""
        return video_id in self.existing or video_id in self.videos

    def start_run(self, stage: str, params_json: str) -> str:
        """Open a fake run."""
        self.runs["run1"] = {"stage": stage, "status": "running", "params": params_json}
        return "run1"

    def finish_run(
        self, run_id: str, *, status: str, n_items: int, watermark: str | None, error: str | None
    ) -> None:
        """Finalise the fake run."""
        self.runs[run_id].update(
            {"status": status, "n_items": n_items, "watermark": watermark, "error": error}
        )
        self.finished.append(status)


class FakeStore:
    """Raw store recording writes, optionally reporting that files already exist."""

    def __init__(self, existing: Sequence[str] = ()) -> None:
        self.existing = set(existing)
        self.writes: list[tuple[str, date, str]] = []

    def write_once(self, channel_id: str, local_date: date, video_id: str, payload: str) -> bool:
        """Record a write attempt; report False when the file 'exists'."""
        if video_id in self.existing:
            return False
        self.writes.append((channel_id, local_date, video_id))
        return True


def _plan(**overrides: object) -> CollectPlan:
    """Build a collect plan with sensible defaults."""
    defaults: dict[str, object] = {"since": date(2026, 10, 1), "limit": 10, "listing_limit": 50}
    defaults.update(overrides)
    return CollectPlan(**defaults)  # type: ignore[arg-type]


def _run(source: FakeSource, repo: FakeRepo, store: FakeStore, plan: CollectPlan | None = None):
    """Run a collection over one channel."""
    return run_collection(
        [_channel()],
        {"imedi": [_news_programme()]},
        plan or _plan(),
        source=source,
        repo=repo,
        raw_store=store,
        logger=LOGGER,
    )


def test_collects_captioned_videos() -> None:
    """Case 1: three captioned videos produce three rows, three files and their cues."""
    uploads = [UploadRef(f"v{i}", "ქრონიკა 19:00") for i in range(3)]
    source = FakeSource(uploads, {f"v{i}": _fetched(f"v{i}") for i in range(3)})
    repo, store = FakeRepo(), FakeStore()

    result = _run(source, repo, store)

    assert result.status == "ok"
    assert len(repo.videos) == 3
    assert len(store.writes) == 3
    assert all(cues == 1 for _, cues in repo.videos.values())
    report = result.reports[0]
    assert (report.listed, report.kept, report.captioned) == (3, 3, 3)


def test_programme_is_matched_and_counted() -> None:
    """FR-5: matched videos get a programme; unmatched ones are counted, not guessed."""
    uploads = [UploadRef("v1", "ქრონიკა 19:00"), UploadRef("v2", "პრეზიდენტი ხვდება კოლეგას")]
    source = FakeSource(
        uploads, {"v1": _fetched("v1"), "v2": _fetched("v2", title="პრეზიდენტი ხვდება კოლეგას")}
    )
    repo, store = FakeRepo(), FakeStore()

    result = _run(source, repo, store)

    assert repo.videos["v1"][0].programme_id == "imedi_news"
    assert repo.videos["v2"][0].programme_id is None
    assert result.reports[0].unclassified == 1


def test_videos_before_window_are_not_stored() -> None:
    """Case 9 / FR-8: published before `since` is excluded.

    The first fixture is 03:00Z on 30 September: 07:00 local, i.e. genuinely before the window.
    A naive 20:30Z fixture would be 00:30 on 1 October in Tbilisi and correctly *inside* it — the
    boundary this suite covers in `test_broadcast_date_uses_tbilisi_time`.
    """
    uploads = [UploadRef("old", "ქრონიკა"), UploadRef("new", "ქრონიკა")]
    source = FakeSource(
        uploads,
        {
            "old": _fetched("old", published=datetime(2026, 9, 30, 3, 0)),
            "new": _fetched("new"),
        },
    )
    repo, store = FakeRepo(), FakeStore()

    _run(source, repo, store)

    assert "old" not in repo.videos
    assert "new" in repo.videos


def test_broadcast_date_uses_tbilisi_time() -> None:
    """Case 10 / FR-9: 21:30Z on 31 Oct is 1 Nov in Tbilisi."""
    uploads = [UploadRef("v1", "ქრონიკა")]
    source = FakeSource(uploads, {"v1": _fetched("v1", published=datetime(2026, 10, 31, 21, 30))})
    repo, store = FakeRepo(), FakeStore()

    _run(source, repo, store)

    assert repo.videos["v1"][0].broadcast_date_local == date(2026, 11, 1)
    assert store.writes[0][1] == date(2026, 11, 1)


def test_unavailable_video_is_skipped_and_run_succeeds() -> None:
    """Case 11 / FR-6: one bad video must not end the run."""
    uploads = [UploadRef(f"v{i}", "ქრონიკა") for i in range(3)]
    results: dict[str, object] = {f"v{i}": _fetched(f"v{i}") for i in range(3)}
    results["v1"] = VideoUnavailableError("Sign in to confirm your age")
    source = FakeSource(uploads, results)
    repo, store = FakeRepo(), FakeStore()

    result = _run(source, repo, store)

    assert result.status == "ok"
    assert set(repo.videos) == {"v0", "v2"}
    assert result.reports[0].skipped == 1
    assert repo.finished == ["ok"]


def test_client_block_stops_the_run() -> None:
    """Case 12 / FR-7: a block ends the run and marks it blocked."""
    uploads = [UploadRef(f"v{i}", "ქრონიკა") for i in range(3)]
    results: dict[str, object] = {f"v{i}": _fetched(f"v{i}") for i in range(3)}
    results["v1"] = ClientBlockedError("HTTP Error 429: Too Many Requests")
    source = FakeSource(uploads, results)
    repo, store = FakeRepo(), FakeStore()

    with pytest.raises(ClientBlockedError):
        _run(source, repo, store)

    assert repo.finished == ["blocked"]
    assert "429" in str(repo.runs["run1"]["error"])


def test_video_without_captions_is_recorded_as_skipped() -> None:
    """A no-caption video is data: stored, counted, but no raw file written."""
    uploads = [UploadRef("v1", "ქრონიკა")]
    source = FakeSource(uploads, {"v1": _fetched("v1", auto=(), cues=())})
    repo, store = FakeRepo(), FakeStore()

    result = _run(source, repo, store)

    video, cues = repo.videos["v1"]
    assert video.status == "skipped_no_caption"
    assert video.caption_kind == "none"
    assert cues == 0
    assert store.writes == []
    assert result.reports[0].no_caption == 1


def test_live_chat_only_becomes_no_caption_end_to_end() -> None:
    """FR-4 through the use case, not just the predicate."""
    uploads = [UploadRef("v1", "ქრონიკა")]
    source = FakeSource(uploads, {"v1": _fetched("v1", auto=("live_chat",), cues=())})
    repo, store = FakeRepo(), FakeStore()

    _run(source, repo, store)

    video, _ = repo.videos["v1"]
    assert (video.caption_kind, video.caption_lang) == ("none", "")


def test_limit_is_respected() -> None:
    """`--limit` caps kept videos per channel."""
    uploads = [UploadRef(f"v{i}", "ქრონიკა") for i in range(10)]
    source = FakeSource(uploads, {f"v{i}": _fetched(f"v{i}") for i in range(10)})
    repo, store = FakeRepo(), FakeStore()

    result = _run(source, repo, store, _plan(limit=3))

    assert result.reports[0].kept == 3
    assert len(repo.videos) == 3


def test_channel_with_nothing_captioned_reports_zeros() -> None:
    """Case 14 / FR-10: an empty channel still produces a report line."""
    source = FakeSource([], {})
    repo, store = FakeRepo(), FakeStore()

    result = _run(source, repo, store)

    report = result.reports[0]
    assert isinstance(report, ChannelReport)
    assert (report.listed, report.kept, report.captioned) == (0, 0, 0)


def test_watermark_records_newest_date() -> None:
    """The run watermark is the newest processed broadcast date (D-004)."""
    uploads = [UploadRef("a", "ქრონიკა"), UploadRef("b", "ქრონიკა")]
    source = FakeSource(
        uploads,
        {
            "a": _fetched("a", published=datetime(2026, 10, 5, 19, 0)),
            "b": _fetched("b", published=datetime(2026, 10, 9, 19, 0)),
        },
    )
    repo, store = FakeRepo(), FakeStore()

    _run(source, repo, store)

    assert repo.runs["run1"]["watermark"] == "2026-10-09"


def test_skip_existing_avoids_refetching() -> None:
    """A resumable backfill must not pay two seconds for work already done."""
    uploads = [UploadRef("v1", "ქრონიკა"), UploadRef("v2", "ქრონიკა")]
    source = FakeSource(uploads, {"v2": _fetched("v2")})
    repo, store = FakeRepo(), FakeStore()
    repo.existing.add("v1")

    result = _run(source, repo, store, _plan(skip_existing=True))

    assert source.fetched == ["v2"]
    assert result.reports[0].already_present == 1
    assert result.reports[0].kept == 1


def test_without_skip_existing_everything_is_refetched() -> None:
    """Default behaviour stays re-fetch-and-converge, which is what fixes drift."""
    uploads = [UploadRef("v1", "ქრონიკა")]
    source = FakeSource(uploads, {"v1": _fetched("v1")})
    repo, store = FakeRepo(), FakeStore()
    repo.existing.add("v1")

    _run(source, repo, store, _plan(skip_existing=False))

    assert source.fetched == ["v1"]


def test_raw_store_never_overwrites(tmp_path: Path) -> None:
    """Case 13 / FR-2: an existing raw file is left byte-identical."""
    store = FileRawStore(tmp_path / "raw")
    first = store.write_once("imedi", date(2026, 11, 1), "vid1", '{"original": true}')
    second = store.write_once("imedi", date(2026, 11, 1), "vid1", '{"different": true}')

    path = store.path_for("imedi", date(2026, 11, 1), "vid1")
    assert first is True
    assert second is False
    assert path.read_text(encoding="utf-8") == '{"original": true}'


def test_raw_store_layout(tmp_path: Path) -> None:
    """Raw files land under channel/date/video.json3."""
    store = FileRawStore(tmp_path / "raw")
    store.write_once("gpb", date(2026, 11, 2), "abc", "{}")
    expected = tmp_path / "raw" / "gpb" / "2026-11-02" / "abc.json3"
    assert expected.exists()
