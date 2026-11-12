"""Caption feasibility probe for the six Georgian TV channels.

Purpose
-------
Answer one factual question before any spec is written: for the six channels in
scope, how often do the evening-news and talk-show videos actually carry YouTube
captions, and are those captions manual or auto-generated?

This script reads *metadata only*. It downloads no video, no audio and no subtitle
file: it asks YouTube for the video's info dictionary and records whether captions
are advertised and in which languages. Nothing here constitutes collection.

Design notes
------------
- One channel listing (flat) is used to enumerate recent uploads cheaply, because a
  per-video extraction is the expensive call.
- Programme type is inferred from the title only, and conservatively: a title with no
  explicit marker is recorded as ``unknown`` rather than guessed. The task that
  produced this script is explicit that guessing is worse than ``unknown``.
- Every network call is followed by a fixed throttle. If YouTube blocks the requests,
  the script stops on that error and reports it verbatim. It does not rotate proxies,
  change user agents beyond yt-dlp's defaults, or retry through a mirror.
- No ``while`` loop is used for bounded work: every loop has a fixed ceiling.

Usage
-----
    .venv\\Scripts\\python.exe spikes/caption_feasibility.py
    .venv\\Scripts\\python.exe spikes/caption_feasibility.py --per-category 20 --throttle 2.0

Exit codes
----------
0   probe completed (individual video failures do not fail the run)
1   YouTube blocked the requests, or the run could not start
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------------------
# Channel registry
#
# Handles confirmed by George on 2026-11-11. This is provisional configuration for the
# spike only; SPEC-001 introduces channels.yaml as the single source of truth, at which
# point this dict is deleted rather than maintained in two places.
# --------------------------------------------------------------------------------------
CHANNELS: list[dict[str, str]] = [
    {"channel_id": "imedi", "name_en": "Imedi", "handle": "@tvimedi"},
    {"channel_id": "rustavi2", "name_en": "Rustavi 2", "handle": "@rustavi2official"},
    {"channel_id": "postv", "name_en": "POSTV", "handle": "@postv"},
    {"channel_id": "gpb", "name_en": "GPB (First Channel)", "handle": "@georgianbroadcaster"},
    {"channel_id": "formula", "name_en": "Formula", "handle": "@tvformula"},
    {"channel_id": "pirveli", "name_en": "TV Pirveli", "handle": "@tvpirveli1"},
]

# Titles are Georgian, sometimes with an English word. Markers are matched
# case-insensitively against the whole title. Deliberately small and explicit: a title
# must contain a marker to be classified at all.
NEWS_MARKERS = ("ამბები", "სიახლე", "newscast", "news")
TALK_MARKERS = (
    "ტოქ-შოუ",
    "ტოქ შოუ",
    "ინტერვიუ",
    "პირისპირ",
    "დებატები",
    "talk show",
    "interview",
    "საუბრები",
)

# Languages to prefer when recording a single caption language per video.
LANG_PREFERENCE = ("ka", "ka-orig", "en", "ru")

BLOCK_HINTS = (
    "429",
    "too many requests",
    "sign in to confirm",
    "confirm you're not a bot",
    "confirm you are not a bot",
    "unable to extract",
    "this video is not available",
    "http error 403",
)


@dataclass(frozen=True)
class VideoRow:
    """One row of the feasibility output; mirrors the CSV columns exactly."""

    channel: str
    video_id: str
    title: str
    published_at: str
    duration_s: str
    programme_type: str
    caption_kind: str
    caption_lang: str

    def as_csv(self) -> dict[str, str]:
        """Return this row as a CSV-ready mapping with string values only."""
        return {
            "channel": self.channel,
            "video_id": self.video_id,
            "title": self.title,
            "published_at": self.published_at,
            "duration_s": self.duration_s,
            "programme_type": self.programme_type,
            "caption_kind": self.caption_kind,
            "caption_lang": self.caption_lang,
        }


def classify_programme(title: str) -> str:
    """Classify a video as ``news``, ``talk`` or ``unknown`` from its title alone.

    Args:
        title: The video title as returned by YouTube.

    Returns:
        ``"news"`` if a news marker is present, ``"talk"`` if a talk/interview marker
        is present, otherwise ``"unknown"``.

    Notes:
        A title containing both marker families is ambiguous, so it returns
        ``"unknown"`` rather than letting list order decide. Titles are matched as
        substrings, so "ამბები" also matches "დღის ამბები" — that is intended.
    """
    lowered = title.casefold()
    is_news = any(marker.casefold() in lowered for marker in NEWS_MARKERS)
    is_talk = any(marker.casefold() in lowered for marker in TALK_MARKERS)
    if is_news and is_talk:
        return "unknown"
    if is_news:
        return "news"
    if is_talk:
        return "talk"
    return "unknown"


def pick_caption(info: dict[str, Any]) -> tuple[str, str]:
    """Determine caption kind and language for one video's info dictionary.

    Args:
        info: A yt-dlp info dictionary (full extraction, not flat).

    Returns:
        A ``(caption_kind, caption_lang)`` pair. ``caption_kind`` is ``"manual"`` when
        YouTube advertises human-authored captions, ``"auto"`` when it advertises only
        automatic ones, and ``"none"`` otherwise. ``caption_lang`` is the preferred
        language code that actually exists, or ``""`` when there is no caption track.
    """
    manual: dict[str, Any] = info.get("subtitles") or {}
    auto: dict[str, Any] = info.get("automatic_captions") or {}

    for source_kind, tracks in (("manual", manual), ("auto", auto)):
        if not tracks:
            continue
        for lang in LANG_PREFERENCE:
            if lang in tracks:
                return source_kind, lang
        # Fall back to the first advertised language, deterministically ordered.
        return source_kind, min(tracks.keys())
    return "none", ""


def to_iso_date(timestamp: Any) -> str:
    """Convert a yt-dlp timestamp (epoch seconds) to an ISO-8601 UTC date string.

    Args:
        timestamp: Epoch seconds, or None/empty when YouTube did not report one.

    Returns:
        ``"YYYY-MM-DD"`` in UTC, or ``""`` when no usable timestamp was reported.
    """
    if not timestamp:
        return ""
    try:
        moment = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return ""
    return moment.date().isoformat()


def looks_blocked(message: str) -> bool:
    """Return True when a yt-dlp error message indicates blocking rather than a bad video."""
    lowered = message.casefold()
    return any(hint in lowered for hint in BLOCK_HINTS)


def build_ydl(quiet: bool = True, flat: bool = False, limit: int | None = None) -> Any:
    """Construct a YoutubeDL instance configured for metadata reads only.

    Args:
        quiet: Suppress yt-dlp's own progress output.
        flat: When True, enumerate a channel's uploads without resolving each video.
            This matters: without flat extraction, asking for a channel URL makes
            yt-dlp resolve every video in the catalogue, which is thousands of calls
            and looks exactly like a hang.
        limit: For flat listings, stop paginating after this many entries. Without it
            yt-dlp walks the channel's entire upload history a page at a time — a
            channel with thousands of videos will appear to hang indefinitely.

    Returns:
        A configured ``YoutubeDL`` instance.
    """
    import yt_dlp  # imported here so --help works without the dependency installed

    options: dict[str, Any] = {
        "skip_download": True,       # never fetch video or audio
        "writesubtitles": False,     # never write subtitle files
        "writeautomaticsub": False,
        "writeinfojson": False,
        "extract_flat": "in_playlist" if flat else False,
        "quiet": quiet,
        "no_warnings": quiet,
        "ignoreerrors": False,
        "retries": 2,
        "socket_timeout": 30,
        "noplaylist": True,
    }
    if flat:
        options["playlistend"] = limit or 100
    return yt_dlp.YoutubeDL(options)


def list_recent_uploads(ydl: Any, handle: str, limit: int) -> list[dict[str, Any]]:
    """Enumerate a channel's most recent uploads without extracting each video.

    Args:
        ydl: A YoutubeDL instance built with ``flat=True``.
        handle: Channel handle including the leading ``@``.
        limit: Maximum number of entries to request.

    Returns:
        A list of flat playlist entries (``id``, ``title``; timestamps when the
        listing reports them).

    Notes:
        The ``/videos`` tab is a playlist of the channel's uploads. Flat extraction
        returns one request's worth of ids and titles without resolving each video;
        that is the whole point of using it here.
    """
    url = f"https://www.youtube.com/{handle}/videos"
    info = ydl.extract_info(url, download=False)
    if not info:
        return []
    entries: Iterable[dict[str, Any]] = info.get("entries") or []
    collected: list[dict[str, Any]] = []
    for entry in entries:
        if entry and entry.get("id"):
            collected.append(entry)
        if len(collected) >= limit:
            break
    return collected


def probe(argv: list[str] | None = None) -> int:
    """Run the caption feasibility probe and write the CSV.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: 0 on completion, 1 when blocked or unable to start.
    """
    parser = argparse.ArgumentParser(description="Caption availability feasibility probe")
    parser.add_argument("--per-category", type=int, default=20,
                        help="Videos to keep per programme type per channel")
    parser.add_argument("--since", default="2026-10-01",
                        help="Earliest publish date (ISO), inclusive")
    parser.add_argument("--throttle", type=float, default=2.0,
                        help="Seconds to wait after every network call")
    parser.add_argument("--listing-limit", type=int, default=120,
                        help="Recent uploads to enumerate per channel")
    parser.add_argument("--max-extract-per-channel", type=int, default=80,
                        help="Hard ceiling on per-video extractions per channel")
    parser.add_argument("--out", default="data/feasibility/captions.csv",
                        help="CSV output path")
    parser.add_argument("--errors", default="data/feasibility/probe_errors.jsonl",
                        help="Per-video error log path")
    args = parser.parse_args(argv)

    since = date.fromisoformat(args.since)
    out_path = Path(args.out)
    err_path = Path(args.errors)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    err_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[VideoRow] = []
    errors: list[dict[str, Any]] = []

    try:
        ydl_flat = build_ydl(flat=True, limit=args.listing_limit)  # ids and titles only
        ydl_full = build_ydl()                                     # per-video captions
    except ImportError:
        print("FATAL: yt-dlp is not installed for this interpreter.", file=sys.stderr)
        return 1

    for channel in CHANNELS:
        name = channel["name_en"]
        print(f"[{name}] listing {args.listing_limit} recent uploads from {channel['handle']}",
              file=sys.stderr)
        try:
            uploads = list_recent_uploads(ydl_flat, channel["handle"], args.listing_limit)
        except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
            message = str(exc)
            if looks_blocked(message):
                print(f"BLOCKED on listing {name}: {message}", file=sys.stderr)
                errors.append({"channel": name, "stage": "listing", "error": message})
                _write_outputs(out_path, err_path, rows, errors)
                return 1
            errors.append({"channel": name, "stage": "listing", "error": message})
            print(f"[{name}] listing failed: {message}", file=sys.stderr)
            time.sleep(args.throttle)
            continue

        time.sleep(args.throttle)

        kept = {"news": 0, "talk": 0}
        extracted = 0
        for entry in uploads:
            if kept["news"] >= args.per_category and kept["talk"] >= args.per_category:
                break
            if extracted >= args.max_extract_per_channel:
                break

            programme_type = classify_programme(entry.get("title") or "")
            if programme_type == "unknown":
                # Not a guess: the task says an unclassifiable title is recorded as
                # unknown and excluded from both quota pools.
                continue
            if kept[programme_type] >= args.per_category:
                continue

            video_id = entry["id"]
            extracted += 1
            try:
                info = ydl_full.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )
            except Exception as exc:  # noqa: BLE001 - per-video failure is recorded
                message = str(exc)
                errors.append({"channel": name, "video_id": video_id, "error": message})
                print(f"[{name}] {video_id} failed: {message}", file=sys.stderr)
                if looks_blocked(message):
                    print(f"BLOCKED on {name} {video_id}: {message}", file=sys.stderr)
                    _write_outputs(out_path, err_path, rows, errors)
                    return 1
                time.sleep(args.throttle)
                continue
            finally:
                time.sleep(args.throttle)

            if not info:
                continue

            published = to_iso_date(info.get("timestamp") or info.get("release_timestamp"))
            if published and date.fromisoformat(published) < since:
                # Outside the archive window. Skip rather than break: the listing is
                # newest-first in practice, but treating that as a guarantee would
                # silently truncate a channel whose uploads are not strictly ordered.
                continue

            caption_kind, caption_lang = pick_caption(info)
            rows.append(
                VideoRow(
                    channel=name,
                    video_id=video_id,
                    title=(info.get("title") or entry.get("title") or "").strip(),
                    published_at=published or to_iso_date(entry.get("timestamp")),
                    duration_s=str(int(info["duration"])) if info.get("duration") else "",
                    programme_type=programme_type,
                    caption_kind=caption_kind,
                    caption_lang=caption_lang,
                )
            )
            kept[programme_type] += 1

        print(
            f"[{name}] kept news={kept['news']} talk={kept['talk']} "
            f"(extracted {extracted})",
            file=sys.stderr,
        )

    _write_outputs(out_path, err_path, rows, errors)
    print(f"wrote {len(rows)} rows to {out_path}; {len(errors)} errors to {err_path}",
          file=sys.stderr)
    return 0


def _write_outputs(
    out_path: Path,
    err_path: Path,
    rows: list[VideoRow],
    errors: list[dict[str, Any]],
) -> None:
    """Write the CSV and the error log. Safe to call on both success and abort."""
    columns = [
        "channel",
        "video_id",
        "title",
        "published_at",
        "duration_s",
        "programme_type",
        "caption_kind",
        "caption_lang",
    ]
    ordered = sorted(
        rows,
        key=lambda r: (r.channel, r.programme_type, r.published_at, r.video_id),
    )
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in ordered:
            writer.writerow(row.as_csv())

    with err_path.open("w", encoding="utf-8") as handle:
        for record in errors:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(probe())
