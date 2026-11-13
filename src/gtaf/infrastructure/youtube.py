"""yt-dlp adapter (SPEC-002 §2, §3.2).

Metadata and caption text only: no video and no audio is ever downloaded. The adapter's whole job is
to turn yt-dlp's dictionaries and ``json3`` payloads into the domain types, and to classify failures
into "skip this video" versus "stop the run".
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from gtaf.application.collect import (
    ClientBlockedError,
    FetchedVideo,
    VideoUnavailableError,
)
from gtaf.domain.collector import (
    NON_TRANSCRIPT_LANGS,
    CaptionCue,
    UploadRef,
    VideoMeta,
    classify_caption,
    is_client_block,
    is_video_unavailable,
)

_DEFAULT_CUE_SECONDS = 0.001


def _timestamp_to_utc(timestamp: Any) -> datetime | None:
    """Convert a yt-dlp epoch timestamp to a naive UTC datetime.

    Args:
        timestamp: Epoch seconds, or None.

    Returns:
        A naive UTC datetime, or None when no timestamp was reported.
    """
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def parse_json3(payload: str) -> tuple[CaptionCue, ...]:
    """Parse a YouTube ``json3`` caption payload into contiguous cues.

    Args:
        payload: Raw ``json3`` text.

    Returns:
        Validated cues with contiguous ``idx`` and ``end_s > start_s``. Blank events are dropped,
        and indices are recomputed after filtering so INV-3 holds by construction.

    Notes:
        A cue whose ``dDurationMs`` is missing or zero gets a 1 ms span. That is deliberate: the
        ``captions`` CHECK requires a positive duration, and inventing a plausible length would be
        fabricating data. 1 ms says "we know the start, not the end".
    """
    data = json.loads(payload)
    events = data.get("events") or []
    cues: list[CaptionCue] = []
    for event in events:
        segments = event.get("segs") or []
        text = "".join(str(segment.get("utf8", "")) for segment in segments).strip()
        if not text:
            continue
        start_s = float(event.get("tStartMs", 0)) / 1000.0
        duration_ms = event.get("dDurationMs") or 0
        end_s = start_s + (float(duration_ms) / 1000.0 if duration_ms > 0 else _DEFAULT_CUE_SECONDS)
        cues.append(CaptionCue(idx=len(cues), start_s=start_s, end_s=end_s, text=text))
    return tuple(cues)


class YtDlpSource:
    """Video source backed by yt-dlp."""

    def __init__(self, *, throttle: float = 2.0, quiet: bool = True) -> None:
        """Initialise the source.

        Args:
            throttle: Seconds to sleep after every network call. Applies to listing as well as to
                per-video fetches; a listing burst is what triggered a bot check once already.
            quiet: Suppress yt-dlp's own output.
        """
        self._throttle = throttle
        self._quiet = quiet

    def _ydl(self, *, flat_limit: int | None = None) -> Any:
        """Build a YoutubeDL instance.

        Args:
            flat_limit: When set, list a channel flat and cap pagination at this many entries.

        Returns:
            A configured ``YoutubeDL``.
        """
        import yt_dlp

        options: dict[str, Any] = {
            "skip_download": True,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "writeinfojson": False,
            "quiet": self._quiet,
            "no_warnings": self._quiet,
            "retries": 2,
            "socket_timeout": 30,
            "noplaylist": True,
            "extract_flat": "in_playlist" if flat_limit is not None else False,
        }
        if flat_limit is not None:
            # Mandatory: without it yt-dlp paginates the channel's entire upload history.
            options["playlistend"] = flat_limit
        return yt_dlp.YoutubeDL(options)

    def list_uploads(self, handle: str, limit: int) -> Sequence[UploadRef]:
        """List a channel's recent uploads, newest first.

        Args:
            handle: Channel handle including the leading ``@``.
            limit: Maximum entries to list.

        Returns:
            Upload references.

        Raises:
            ClientBlockedError: If listing is blocked.
            VideoUnavailableError: If the channel cannot be listed for a non-block reason.
        """
        url = f"https://www.youtube.com/{handle}/videos"
        try:
            info = self._ydl(flat_limit=limit).extract_info(url, download=False)
        except Exception as exc:
            message = str(exc)
            if is_client_block(message):
                raise ClientBlockedError(message) from exc
            raise VideoUnavailableError(message) from exc
        finally:
            time.sleep(self._throttle)

        if not info:
            return []
        uploads: list[UploadRef] = []
        for entry in info.get("entries") or []:
            if entry and entry.get("id"):
                uploads.append(
                    UploadRef(video_id=str(entry["id"]), title=str(entry.get("title") or ""))
                )
            if len(uploads) >= limit:
                break
        return uploads

    def fetch_video(self, video_id: str) -> FetchedVideo:
        """Fetch one video's metadata and caption payload.

        Args:
            video_id: YouTube video id.

        Returns:
            The fetched video, with cues and the raw payload when a transcript exists.

        Raises:
            VideoUnavailableError: For a per-video condition (age gate, private, removed).
            ClientBlockedError: For a client-level block.
        """
        try:
            info = self._ydl().extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
        except Exception as exc:
            message = str(exc)
            if is_client_block(message):
                raise ClientBlockedError(message) from exc
            if is_video_unavailable(message):
                raise VideoUnavailableError(message) from exc
            # An unrecognised per-video failure must not kill the run (FR-6), so it is treated as a
            # skip; the message is preserved in the report and the run log.
            raise VideoUnavailableError(message) from exc
        finally:
            time.sleep(self._throttle)

        if not info:
            raise VideoUnavailableError(f"no metadata returned for {video_id}")

        manual = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        caption_kind, caption_lang = classify_caption(list(manual), list(auto))

        meta = VideoMeta(
            video_id=video_id,
            title=str(info.get("title") or ""),
            published_at=_timestamp_to_utc(info.get("timestamp") or info.get("release_timestamp")),
            duration_s=int(info["duration"]) if info.get("duration") else None,
            manual_langs=tuple(
                key for key in manual if key not in NON_TRANSCRIPT_LANGS
            ),
            auto_langs=tuple(key for key in auto if key not in NON_TRANSCRIPT_LANGS),
        )

        if caption_kind == "none" or not caption_lang:
            return FetchedVideo(meta=meta, raw_payload=None, cues=())

        tracks = manual if caption_kind == "manual" else auto
        entries = tracks.get(caption_lang) or []
        url = next(
            (entry.get("url") for entry in entries if entry.get("url")),
            None,
        )
        if not url:
            return FetchedVideo(meta=meta, raw_payload=None, cues=())

        payload = self._download_text(url)
        return FetchedVideo(meta=meta, raw_payload=payload, cues=parse_json3(payload))

    def _download_text(self, url: str) -> str:
        """Fetch a caption payload as text.

        Args:
            url: Caption track URL reported by yt-dlp.

        Returns:
            The payload text.

        Raises:
            ClientBlockedError: If the caption endpoint rate-limits or refuses us (429/403). This
                must stop the run: the throttle exists to stay under that limit, and continuing
                after a 429 is what turns a pause into a hard block.
            VideoUnavailableError: For any other payload failure; the video is skipped rather than
                stored with captions it does not have.
        """
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return str(response.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            message = f"caption payload unavailable: {exc}"
            # The caption/timedtext endpoint rate-limits independently of the metadata API. A 429
            # here was previously misclassified as a per-video skip, so the run kept requesting and
            # deepened the limit instead of stopping — the same shape of bug as the age gate.
            if is_client_block(message):
                raise ClientBlockedError(message) from exc
            raise VideoUnavailableError(message) from exc
        finally:
            time.sleep(self._throttle)
