"""Adapter-level tests for yt-dlp classification and json3 parsing.

These cover the two failures that only appear when talking to the real service: a rate limit on the
caption endpoint (429) and per-video unavailability. Both are tested without network by replacing
`urlopen`.
"""

from __future__ import annotations

import urllib.error

import pytest

from gtaf.application.collect import ClientBlockedError, VideoUnavailableError
from gtaf.infrastructure import youtube
from gtaf.infrastructure.youtube import YtDlpSource, parse_json3


def test_caption_payload_429_is_a_client_block(monkeypatch) -> None:
    """A 429 on the caption endpoint must stop the run, not skip the video.

    This is the bug that turned a pause into a harder rate limit during the first full backfill: the
    payload download classified every failure as per-video, so the collector kept requesting.
    """

    def raise_429(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("https://example", 429, "Too Many Requests", None, None)

    monkeypatch.setattr(youtube.urllib.request, "urlopen", raise_429)
    source = YtDlpSource(throttle=0)

    with pytest.raises(ClientBlockedError):
        source._download_text("https://example/caption")


def test_caption_payload_403_is_a_client_block(monkeypatch) -> None:
    """A forbidden payload response is a client-level refusal."""

    def raise_403(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("https://example", 403, "Forbidden", None, None)

    monkeypatch.setattr(youtube.urllib.request, "urlopen", raise_403)
    source = YtDlpSource(throttle=0)

    with pytest.raises(ClientBlockedError):
        source._download_text("https://example/caption")


def test_caption_payload_404_is_a_video_skip(monkeypatch) -> None:
    """A missing payload is about one video; the run continues."""

    def raise_404(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("https://example", 404, "Not Found", None, None)

    monkeypatch.setattr(youtube.urllib.request, "urlopen", raise_404)
    source = YtDlpSource(throttle=0)

    with pytest.raises(VideoUnavailableError):
        source._download_text("https://example/caption")


def test_proxy_is_passed_to_ytdlp() -> None:
    """Measured 2026-11-26: YouTube answers transcript requests from this host with IpBlocked in two
    independent clients, so a different egress IP is the only lever. The adapter must carry a proxy."""
    from gtaf.infrastructure.youtube import YtDlpSource

    with_proxy = YtDlpSource(quiet=True, proxy="http://127.0.0.1:8080")._ydl()
    without = YtDlpSource(quiet=True)._ydl()

    assert with_proxy.params.get("proxy") == "http://127.0.0.1:8080"
    assert not without.params.get("proxy")


def test_parse_rss_extracts_ids_and_titles() -> None:
    """The RSS listing is the light path that avoids burning the caption quota."""
    from gtaf.infrastructure.youtube import parse_rss

    xml = """
    <feed>
      <entry><yt:videoId>abc123</yt:videoId><media:title>First &amp; best</media:title></entry>
      <entry><yt:videoId>def456</yt:videoId><media:title>Second</media:title></entry>
    </feed>
    """
    uploads = parse_rss(xml, 5)

    assert [upload.video_id for upload in uploads] == ["abc123", "def456"]
    assert uploads[0].title == "First & best"


def test_parse_rss_honours_the_limit() -> None:
    """A feed longer than the limit is truncated, newest first."""
    from gtaf.infrastructure.youtube import parse_rss

    xml = "".join(f"<yt:videoId>id{index}</yt:videoId>" for index in range(20))
    uploads = parse_rss(xml, 3)

    assert len(uploads) == 3
    assert uploads[0].video_id == "id0"


def test_parse_rss_without_titles_still_returns_ids() -> None:
    """A feed entry without a title must not lose its id."""
    from gtaf.infrastructure.youtube import parse_rss

    uploads = parse_rss("<yt:videoId>onlyid</yt:videoId>", 5)

    assert uploads[0].video_id == "onlyid"
    assert uploads[0].title == ""


def test_parse_json3_builds_contiguous_cues() -> None:
    """Blank events are dropped and indices recomputed, so INV-3 holds by construction."""
    payload = (
        '{"events": ['
        '{"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "hello "}, {"utf8": "world"}]},'
        '{"tStartMs": 2000, "dDurationMs": 1000, "segs": [{"utf8": "  "}]},'
        '{"tStartMs": 3000, "dDurationMs": 0, "segs": [{"utf8": "no duration"}]}'
        "]}"
    )
    cues = parse_json3(payload)
    assert [cue.idx for cue in cues] == [0, 1]
    assert cues[0].text == "hello world"
    assert cues[0].end_s == 2.0
    # A zero-duration cue keeps a 1 ms span rather than an invented length.
    assert cues[1].end_s > cues[1].start_s
    assert round(cues[1].end_s - cues[1].start_s, 3) == 0.001
