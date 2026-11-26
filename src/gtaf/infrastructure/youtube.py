"""yt-dlp adapter (SPEC-002 §2, §3.2).

Metadata and caption text only: no video and no audio is ever downloaded. The adapter's whole job is
to turn yt-dlp's dictionaries and ``json3`` payloads into the domain types, and to classify failures
into "skip this video" versus "stop the run".
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
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


CHANNEL_ID_RE = re.compile(r'"channelId":"(UC[A-Za-z0-9_-]{22})"')
RSS_VIDEO_RE = re.compile(r"<yt:videoId>([^<]+)</yt:videoId>")
RSS_TITLE_RE = re.compile(r"<media:title>([^<]*)</media:title>")

# The feed carries at most 15 entries; beyond that the metadata listing is required.
RSS_MAX_ENTRIES = 15


def parse_rss(xml: str, limit: int) -> tuple[UploadRef, ...]:
    """Extract uploads from a channel RSS feed.

    Args:
        xml: Feed body.
        limit: Maximum entries to return.

    Returns:
        Uploads in feed order (newest first).

    Notes:
        RSS is used because the ordinary listing is what burns the caption quota. Measured 2026-11-25: a
        single yt-dlp channel listing made every following caption request return HTTP 429, while the same
        videos fetched fine on their own. The feed is a plain XML endpoint with no API quota, and it avoids
        the browse request that appears to trip the limiter.
    """
    video_ids = RSS_VIDEO_RE.findall(xml)
    titles = RSS_TITLE_RE.findall(xml)
    uploads: list[UploadRef] = []
    for index, video_id in enumerate(video_ids[:limit]):
        title = html_unescape(titles[index]) if index < len(titles) else ""
        uploads.append(UploadRef(video_id=video_id, title=title))
    return tuple(uploads)


def resolve_channel_id(handle: str, *, timeout: int = 30) -> str:
    """Resolve a handle to a channel id by reading the channel page.

    Args:
        handle: ``@name`` handle.
        timeout: Request timeout in seconds.

    Returns:
        The ``UC…`` channel id.

    Raises:
        VideoUnavailableError: When the page does not contain a channel id.
    """
    cleaned = handle if handle.startswith("@") else f"@{handle}"
    request = urllib.request.Request(
        f"https://www.youtube.com/{cleaned}",
        headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        page = response.read().decode("utf-8", errors="replace")
    match = CHANNEL_ID_RE.search(page)
    if not match:
        raise VideoUnavailableError(f"no channel id found on the page for {cleaned}")
    return match.group(1)


def list_uploads_rss(handle: str, limit: int, *, timeout: int = 30) -> tuple[UploadRef, ...]:
    """List a channel's newest uploads from its RSS feed.

    Args:
        handle: ``@name`` handle.
        limit: Maximum entries.
        timeout: Request timeout in seconds.

    Returns:
        Uploads, newest first.

    Raises:
        VideoUnavailableError: When the feed cannot be read.
    """
    channel_id = resolve_channel_id(handle, timeout=timeout)
    request = urllib.request.Request(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        xml = response.read().decode("utf-8", errors="replace")
    return parse_rss(xml, limit)


def html_unescape(text: str) -> str:
    """Decode the few XML entities a feed title may contain.

    Args:
        text: Raw text.

    Returns:
        Decoded text.
    """
    for entity, character in (
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
    ):
        text = text.replace(entity, character)
    return text


def load_netscape_cookies(path: Path) -> str:
    """Build a Cookie header from a Netscape-format cookies file.

    Args:
        path: Path to ``cookies.txt``.

    Returns:
        ``name=value; name=value`` for cookies whose domain mentions youtube, or an empty string.

    Notes:
        The caption fetch is a plain HTTP request, so it does not share yt-dlp's cookie jar; without the
        header the request stays anonymous while the metadata call is authenticated. That mismatch is the
        kind of half-fix that looks like it should work and does not.
    """
    if not path.exists():
        return ""
    pairs: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, _expiry, name, value = parts[:7]
        if "youtube" not in domain or not name:
            continue
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


class YtDlpSource:
    """Video source backed by yt-dlp."""

    def __init__(
        self,
        *,
        throttle: float = 2.0,
        quiet: bool = True,
        proxy: str | None = None,
        cookies: Path | None = None,
    ) -> None:
        """Initialise the source.

        Args:
            throttle: Seconds to sleep after every network call. Applies to listing as well as to
                per-video fetches; a listing burst is what triggered a bot check once already.
            quiet: Suppress yt-dlp's own output.
            proxy: Optional HTTP(S) proxy URL. Measured 2026-11-26: YouTube answers transcript requests from
                this host with `IpBlocked` in two independent clients, so the only working lever is a
                different egress IP — a proxy, a VPN, or another network.
            cookies: Optional Netscape ``cookies.txt`` from a signed-in browser. This changes the session
                from "anonymous client" to "a person's browser", which is the one remaining local lever.
        """
        self._throttle = throttle
        self._quiet = quiet
        self._proxy = proxy
        self._cookies = cookies
        self._cookie_header = load_netscape_cookies(cookies) if cookies else ""

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
        if self._proxy:
            options["proxy"] = self._proxy
        if self._cookies:
            options["cookiefile"] = str(self._cookies)
        return yt_dlp.YoutubeDL(options)

    def list_uploads(self, handle: str, limit: int) -> Sequence[UploadRef]:
        """List a channel's uploads, preferring the RSS feed.

        Args:
            handle: ``@name`` handle.
            limit: Maximum uploads to return.

        Returns:
            Uploads, newest first.

        Notes:
            The RSS feed is tried first because the ordinary listing is what burns the caption quota:
            measured 2026-11-25, one yt-dlp channel listing made every following caption request return
            HTTP 429, while the same videos fetched fine on their own. The feed is a light XML request with
            no API quota.

            The feed carries only the newest ~15 entries, so a larger ``limit`` falls back to yt-dlp's
            listing; that path is the expensive one and is used only for a deliberate backfill.
        """
        if limit <= RSS_MAX_ENTRIES:
            try:
                uploads = list_uploads_rss(handle, limit)
                if uploads:
                    return uploads
            except Exception:  # noqa: BLE001 - fall back to the metadata API
                pass
        return self._list_uploads_ytdlp(handle, limit)

    def _list_uploads_ytdlp(self, handle: str, limit: int) -> Sequence[UploadRef]:
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
            manual_langs=tuple(key for key in manual if key not in NON_TRANSCRIPT_LANGS),
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
            headers = {"Cookie": self._cookie_header} if self._cookie_header else {}
            if self._proxy:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({"http": self._proxy, "https": self._proxy})
                )
                request = urllib.request.Request(url, headers=headers)
                with opener.open(request, timeout=30) as response:
                    return str(response.read().decode("utf-8", errors="replace"))
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
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
