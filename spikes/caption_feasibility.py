"""Caption feasibility probe for the six Georgian TV channels.

Purpose
-------
Answer one factual question before SPEC-002 is written: for each channel, how often do recent
videos actually carry YouTube captions, and are those captions manual or auto-generated?

This script reads *metadata only*. It downloads no video, no audio and no subtitle file: it asks
YouTube for the video's info dictionary and records whether captions are advertised and in which
languages. Nothing here constitutes collection.

Classification is driven by the committed `config/programmes.yaml`, loaded through the real
application loader. That is deliberate (DRY): the probe and the future collector must not hold two
different opinions about what a "news" programme is. A title matching no configured pattern is
recorded as `unknown` rather than guessed.

Design notes
------------
- One flat channel listing enumerates recent uploads cheaply, capped with `playlistend`. Without
  that cap yt-dlp walks the channel's entire upload history a page at a time — it once reached
  page 293 and very likely triggered YouTube's bot check.
- Every network call is followed by a fixed throttle. If YouTube blocks the requests, the script
  stops on that error and reports it verbatim; it does not rotate proxies, retry through a mirror,
  or switch user agents.
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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from gtaf.infrastructure.config_io import load_configuration  # noqa: E402

# Languages to prefer when recording a single caption language per video.
LANG_PREFERENCE = ("ka", "ka-orig", "en", "ru")

# Keys that appear in yt-dlp's caption dictionaries but are NOT transcripts of the audio. A live
# chat is viewer text; counting it as a caption would overstate coverage, so it is excluded.
NON_TRANSCRIPT_KEYS = ("live_chat", "live_chat_replay")

# IP/client-level blocking: the whole run must stop and report, never work around it.
BLOCK_HINTS = (
    "429",
    "too many requests",
    "not a bot",
    "confirm you're not a bot",
    "confirm you are not a bot",
    "http error 403",
)

# Per-video conditions: this video cannot be read, everything else still can. These must NOT stop
# the run — an age gate on one bulletin says nothing about the channel, and aborting a 240-video
# probe because of one such video would throw away all the usable evidence.
SKIP_HINTS = (
    "sign in to confirm your age",
    "age-restricted",
    "inappropriate for some users",
    "video unavailable",
    "this video is not available",
    "private video",
    "members-only",
    "removed by the uploader",
    "has been terminated",
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
    programme_id: str

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
            "programme_id": self.programme_id,
        }


def classify(title: str, programmes: Sequence[Any]) -> tuple[str, str] | None:
    """Match a title against one channel's configured programme patterns.

    Args:
        title: Video title.
        programmes: Programme objects belonging to that channel.

    Returns:
        ``(programme_id, type)`` for the first matching programme, or None when nothing matches
        (recorded as ``unknown`` — never guessed).

    Notes:
        Matching is case-insensitive substring, longest pattern first, so a specific marker beats a
        generic one. Ties are broken by programme_id for determinism.
    """
    lowered = title.casefold()
    candidates: list[tuple[int, str, str]] = []
    for programme in programmes:
        for pattern in programme.title_patterns:
            if pattern and pattern.casefold() in lowered:
                candidates.append((len(pattern), programme.programme_id, programme.type))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    _, programme_id, programme_type = candidates[0]
    return programme_id, programme_type


def pick_caption(info: dict[str, Any]) -> tuple[str, str]:
    """Determine caption kind and language for one video's info dictionary.

    Args:
        info: A yt-dlp info dictionary (full extraction, not flat).

    Returns:
        A ``(caption_kind, caption_lang)`` pair. ``caption_kind`` is ``"manual"`` when YouTube
        advertises human-authored captions, ``"auto"`` when it advertises only automatic ones, and
        ``"none"`` otherwise. ``caption_lang`` is the preferred language code that actually exists,
        or ``""`` when there is no caption track.
    """
    manual: dict[str, Any] = info.get("subtitles") or {}
    auto: dict[str, Any] = info.get("automatic_captions") or {}

    def transcripts(tracks: dict[str, Any]) -> dict[str, Any]:
        """Drop non-transcript tracks (live chat) from a caption dictionary."""
        return {
            key: value
            for key, value in tracks.items()
            if key.casefold() not in NON_TRANSCRIPT_KEYS
        }

    for source_kind, tracks in (("manual", transcripts(manual)), ("auto", transcripts(auto))):
        if not tracks:
            continue
        for lang in LANG_PREFERENCE:
            if lang in tracks:
                return source_kind, lang
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
        moment = datetime.fromtimestamp(float(timestamp), tz=UTC)
    except (TypeError, ValueError, OSError):
        return ""
    return moment.date().isoformat()


def looks_blocked(message: str) -> bool:
    """Return True when an error means the client is blocked, not that one video is unreadable.

    Args:
        message: yt-dlp error text.

    Returns:
        True for IP/client-level blocking only. A per-video condition (age gate, removed video)
        returns False, so the caller skips that item and continues.
    """
    lowered = message.casefold()
    if any(hint in lowered for hint in SKIP_HINTS):
        return False
    return any(hint in lowered for hint in BLOCK_HINTS)


def build_ydl(quiet: bool = True, flat: bool = False, limit: int | None = None) -> Any:
    """Construct a YoutubeDL instance configured for metadata reads only.

    Args:
        quiet: Suppress yt-dlp's own progress output.
        flat: Enumerate a channel's uploads without resolving each video.
        limit: For flat listings, stop paginating after this many entries (see module docstring).

    Returns:
        A configured ``YoutubeDL`` instance.
    """
    import yt_dlp  # imported here so --help works without the dependency installed

    options: dict[str, Any] = {
        "skip_download": True,
        "writesubtitles": False,
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
        Flat playlist entries (``id``, ``title``).
    """
    info = ydl.extract_info(f"https://www.youtube.com/{handle}/videos", download=False)
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
    parser.add_argument("--unclassified-sample", type=int, default=0,
                        help="Also sample this many UNCLASSIFIED videos per channel. Without it "
                             "the caption rate is measured only on videos that matched a "
                             "programme, which is a selection bias: the unclassified majority "
                             "goes unchecked.")
    parser.add_argument("--config-dir", default="config",
                        help="Directory holding channels.yaml and programmes.yaml")
    parser.add_argument("--out", default="data/feasibility/captions.csv", help="CSV output path")
    parser.add_argument("--errors", default="data/feasibility/probe_errors.jsonl",
                        help="Per-video error log path")
    args = parser.parse_args(argv)

    since = date.fromisoformat(args.since)
    out_path = Path(args.out)
    err_path = Path(args.errors)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    err_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        config = load_configuration(Path(args.config_dir))
    except Exception as exc:  # noqa: BLE001 - a bad config must stop the probe loudly
        print(f"FATAL: cannot load configuration: {exc}", file=sys.stderr)
        return 1

    programmes_by_channel: dict[str, list[Any]] = {}
    for programme in config.programmes:
        programmes_by_channel.setdefault(programme.channel_id, []).append(programme)

    rows: list[VideoRow] = []
    errors: list[dict[str, Any]] = []
    unclassified = 0

    try:
        ydl_flat = build_ydl(flat=True, limit=args.listing_limit)
        ydl_full = build_ydl()
    except ImportError:
        print("FATAL: yt-dlp is not installed for this interpreter.", file=sys.stderr)
        return 1

    for channel in config.channels:
        name = channel.name_en
        channel_programmes = programmes_by_channel.get(channel.channel_id, [])
        print(f"[{name}] {len(channel_programmes)} programme(s); listing "
              f"{args.listing_limit} uploads from {channel.youtube_handle}", file=sys.stderr)
        try:
            uploads = list_recent_uploads(ydl_flat, channel.youtube_handle, args.listing_limit)
        except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
            message = str(exc)
            errors.append({"channel": name, "stage": "listing", "error": message})
            print(f"[{name}] listing failed: {message}", file=sys.stderr)
            if looks_blocked(message):
                print(f"BLOCKED on listing {name}: {message}", file=sys.stderr)
                _write_outputs(out_path, err_path, rows, errors)
                return 1
            time.sleep(args.throttle)
            continue

        time.sleep(args.throttle)

        kept = {"news": 0, "talk": 0, "interview": 0, "unknown": 0}
        # Only require quotas for types this channel actually configures; otherwise a channel with
        # no news programme would exhaust its listing trying to satisfy an unreachable news quota.
        available_types = {programme.type for programme in channel_programmes}
        quota = {
            kind: (args.per_category if kind in available_types else 0)
            for kind in ("news", "talk", "interview")
        }
        quota["unknown"] = args.unclassified_sample
        extracted = 0
        for entry in uploads:
            if all(kept[kind] >= quota[kind] for kind in kept):
                break
            if extracted >= args.max_extract_per_channel:
                break

            match = classify(entry.get("title") or "", channel_programmes)
            if match is None:
                unclassified += 1
                if quota["unknown"] == 0:
                    continue
                # Sampled deliberately to remove the selection bias: these are the videos whose
                # captions would otherwise never be checked.
                programme_id, programme_type = "", "unknown"
            else:
                programme_id, programme_type = match
            if kept[programme_type] >= quota[programme_type]:
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
                # Outside the archive window. Skip rather than break: listings are newest-first in
                # practice, but treating that as a guarantee would silently truncate a channel.
                continue

            caption_kind, caption_lang = pick_caption(info)
            rows.append(
                VideoRow(
                    channel=name,
                    video_id=video_id,
                    title=(info.get("title") or entry.get("title") or "").strip(),
                    published_at=published,
                    duration_s=str(int(info["duration"])) if info.get("duration") else "",
                    programme_type=programme_type,
                    caption_kind=caption_kind,
                    caption_lang=caption_lang,
                    programme_id=programme_id,
                )
            )
            kept[programme_type] += 1

        print(
            f"[{name}] kept news={kept['news']} talk={kept['talk']} "
            f"interview={kept['interview']} unknown={kept['unknown']} (extracted {extracted})",
            file=sys.stderr,
        )

    _write_outputs(out_path, err_path, rows, errors)
    print(f"wrote {len(rows)} rows to {out_path}; {len(errors)} errors; "
          f"{unclassified} title(s) matched no programme", file=sys.stderr)
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
        "programme_id",
    ]
    ordered = sorted(rows, key=lambda r: (r.channel, r.programme_type, r.published_at, r.video_id))
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
