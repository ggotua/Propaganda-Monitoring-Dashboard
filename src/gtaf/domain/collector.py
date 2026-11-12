"""Domain rules for the collector (SPEC-002 §3.2, §3.3).

Pure functions and constants only: no I/O, no yt-dlp, no database. Both the real adapter and the
tests use these, so the classification rules exist in exactly one place (the spike's duplicates are
now removed).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from gtaf.domain.models import CaptionKind, Programme

# Languages preferred when recording the single `caption_lang` value for a video.
LANG_PREFERENCE = ("ka", "ka-orig", "en", "ru")

# Keys that appear in YouTube's caption dictionaries but are NOT transcripts of the audio.
# A live chat is viewer text; counting it as a caption overstates coverage (measured in the probe).
NON_TRANSCRIPT_LANGS = frozenset({"live_chat", "live_chat_replay"})

# Client-level blocking: stop the run, report verbatim, never work around it.
CLIENT_BLOCK_HINTS = (
    "429",
    "too many requests",
    "not a bot",
    "confirm you're not a bot",
    "confirm you are not a bot",
    "http error 403",
)

# Per-video conditions: skip this video, keep the run alive.
VIDEO_SKIP_HINTS = (
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


@dataclass(frozen=True, slots=True)
class UploadRef:
    """A video that appears in a channel listing.

    Attributes:
        video_id: YouTube video id.
        title: Title as listed, used for programme matching before any fetch.
    """

    video_id: str
    title: str


@dataclass(frozen=True, slots=True)
class CaptionCue:
    """One caption cue, already validated.

    Attributes:
        idx: Zero-based cue index, contiguous per video.
        start_s: Start offset in seconds.
        end_s: End offset in seconds, strictly greater than ``start_s``.
        text: Cue text.
    """

    idx: int
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True, slots=True)
class VideoMeta:
    """Metadata for one video, as returned by a source.

    Attributes:
        video_id: YouTube video id.
        title: Title as published.
        published_at: UTC instant, naive (convention: `tech-stack.md`).
        duration_s: Duration in seconds, ``None`` when unreported.
        manual_langs: Language keys of human-authored caption tracks (non-transcript excluded).
        auto_langs: Language keys of automatic caption tracks (non-transcript excluded).
    """

    video_id: str
    title: str
    published_at: datetime | None
    duration_s: int | None
    manual_langs: tuple[str, ...]
    auto_langs: tuple[str, ...]


def is_client_block(message: str) -> bool:
    """Return True when an error means the client is blocked rather than one video being unreadable.

    Args:
        message: Error text from the source adapter.

    Returns:
        True only for client-level blocking. A per-video condition returns False, so the caller
        skips that video and continues (SPEC-002 FR-6/FR-7).
    """
    lowered = message.casefold()
    if any(hint in lowered for hint in VIDEO_SKIP_HINTS):
        return False
    return any(hint in lowered for hint in CLIENT_BLOCK_HINTS)


def is_video_unavailable(message: str) -> bool:
    """Return True when an error is specific to one video (age gate, private, removed).

    Args:
        message: Error text from the source adapter.

    Returns:
        True when the run should skip this video rather than stop.
    """
    lowered = message.casefold()
    return any(hint in lowered for hint in VIDEO_SKIP_HINTS)


def classify_caption(
    manual_langs: Sequence[str], auto_langs: Sequence[str]
) -> tuple[CaptionKind, str]:
    """Determine ``(caption_kind, caption_lang)`` for one video (FR-1, FR-4).

    Args:
        manual_langs: Language keys of human-authored tracks.
        auto_langs: Language keys of automatic tracks.

    Returns:
        ``("manual" | "auto" | "none", lang)``. Non-transcript keys are filtered out first, so a
        video offering only ``live_chat`` classifies as ``("none", "")``.
    """
    manual = [lang for lang in manual_langs if lang not in NON_TRANSCRIPT_LANGS]
    auto = [lang for lang in auto_langs if lang not in NON_TRANSCRIPT_LANGS]

    candidates: tuple[tuple[CaptionKind, list[str]], ...] = (
        ("manual", manual),
        ("auto", auto),
    )
    for kind, langs in candidates:
        if not langs:
            continue
        for preferred in LANG_PREFERENCE:
            if preferred in langs:
                return kind, preferred
        return kind, min(langs)
    return "none", ""


def match_programme(title: str, programmes: Sequence[Programme]) -> str | None:
    """Match a title against one channel's configured programmes (FR-5).

    Args:
        title: Video title.
        programmes: Programmes belonging to the video's channel only.

    Returns:
        The matching ``programme_id``, or ``None`` when nothing matches. Never guesses, and never
        considers another channel's patterns — cross-channel matching would label a Rustavi 2
        bulletin with an Imedi programme.
    """
    lowered = title.casefold()
    best: tuple[int, str] | None = None
    for programme in programmes:
        for pattern in programme.title_patterns:
            if pattern and pattern.casefold() in lowered:
                candidate = (len(pattern), programme.programme_id)
                if best is None or candidate[0] > best[0] or (
                    candidate[0] == best[0] and candidate[1] < best[1]
                ):
                    best = candidate
    return best[1] if best else None


def is_within_window(published: date | None, since: date) -> bool:
    """Return True when a publish date falls inside the archive window (FR-8).

    Args:
        published: Local publish date, or None when the source did not report one.
        since: Earliest acceptable date, inclusive.

    Returns:
        True when the date is known and not before ``since``. An unknown date is excluded: the
        window is a factual claim and cannot be asserted for a video with no date.
    """
    return published is not None and published >= since
