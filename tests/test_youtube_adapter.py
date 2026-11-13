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
