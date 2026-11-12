"""Domain entities.

These are frozen dataclasses rather than ORM models on purpose (SPEC-001 §12): the workload is
analytical SQL, and a mapping layer would hide the joins and aggregations the analysis depends
on. Nothing here knows about DuckDB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

ProgrammeType = Literal["news", "talk", "interview"]
CaptionKind = Literal["manual", "auto", "none"]
VideoStatus = Literal["pending", "captioned", "skipped_no_caption", "failed"]
RunStatus = Literal["running", "ok", "failed", "blocked"]

PROGRAMME_TYPES: tuple[ProgrammeType, ...] = ("news", "talk", "interview")
CAPTION_KINDS: tuple[CaptionKind, ...] = ("manual", "auto", "none")
VIDEO_STATUSES: tuple[VideoStatus, ...] = (
    "pending",
    "captioned",
    "skipped_no_caption",
    "failed",
)
RUN_STATUSES: tuple[RunStatus, ...] = ("running", "ok", "failed", "blocked")


@dataclass(frozen=True, slots=True)
class Channel:
    """A broadcaster in scope.

    Attributes:
        channel_id: Stable slug, e.g. ``imedi``.
        name_en: Display name in English.
        name_ka: Display name in Georgian, when known.
        youtube_handle: Handle including the leading ``@``.
        youtube_channel_id: ``UC…`` identifier once the collector has resolved it; ``None``
            until then (config never asserts it — see ``config/channels.yaml``).
        active: Whether the channel is currently in scope.
    """

    channel_id: str
    name_en: str
    name_ka: str | None
    youtube_handle: str
    youtube_channel_id: str | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class Programme:
    """A pattern family used to classify a video, not necessarily a named show.

    Attributes:
        programme_id: Stable slug, e.g. ``imedi_news``.
        channel_id: Owning channel; must exist in the channel configuration.
        name_en: Display name in English.
        name_ka: Display name in Georgian, when known.
        type: One of ``news``, ``talk``, ``interview``.
        title_patterns: Case-insensitive substrings indicating this programme family.
        playlist_ids: YouTube playlist ids, an alternative to title matching.
        active: Whether the programme is currently in scope.
    """

    programme_id: str
    channel_id: str
    name_en: str
    name_ka: str | None
    type: ProgrammeType
    title_patterns: tuple[str, ...] = ()
    playlist_ids: tuple[str, ...] = ()
    active: bool = True


@dataclass(frozen=True, slots=True)
class Video:
    """One YouTube video and the caption facts known about it.

    Attributes:
        video_id: YouTube video id.
        channel_id: Owning channel.
        programme_id: Matched programme, or ``None`` when no pattern matched (never guessed).
        published_at: UTC instant, naive.
        broadcast_date_local: Tbilisi local date of ``published_at`` (D-009).
        title: Video title as published.
        duration_s: Duration in seconds when reported.
        caption_kind: ``manual``, ``auto`` or ``none``.
        caption_lang: Preferred caption language code, empty when no track exists.
        status: Pipeline status for this video.
    """

    video_id: str
    channel_id: str
    programme_id: str | None
    published_at: datetime
    broadcast_date_local: date
    title: str
    duration_s: int | None
    caption_kind: CaptionKind
    caption_lang: str
    status: VideoStatus


@dataclass(frozen=True, slots=True)
class Caption:
    """One caption cue.

    Attributes:
        video_id: Parent video.
        idx: Zero-based cue index, contiguous per video (INV-3).
        start_s: Start offset in seconds.
        end_s: End offset in seconds; must exceed ``start_s`` (INV-4).
        text: Cue text.
    """

    video_id: str
    idx: int
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True, slots=True)
class Segment:
    """A thematic slice of a video's transcript.

    Attributes:
        segment_id: Stable identifier.
        video_id: Parent video.
        start_s: Start offset in seconds.
        end_s: End offset in seconds.
        text: Segment transcript.
        title_ka: Georgian segment title, when the segmenter produced one.
        title_en: English segment title, when produced.
        seg_method: Which segmenter produced it.
        seg_version: Version of that segmenter (D-009).
    """

    segment_id: str
    video_id: str
    start_s: float
    end_s: float
    text: str
    title_ka: str | None
    title_en: str | None
    seg_method: Literal["llm", "texttiling", "fixed"]
    seg_version: str


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Bookkeeping for one stage execution.

    Attributes:
        run_id: Unique run identifier.
        stage: Pipeline stage name.
        method: Method name when the stage is a method run.
        status: One of ``running``, ``ok``, ``failed``, ``blocked``.
        started_at: UTC instant the run started.
        finished_at: UTC instant the run finished, ``None`` while running.
        n_items: Items processed.
        cost_usd: Measured cost, zero for non-LLM stages.
        watermark: Per-stage progress marker (D-004).
    """

    run_id: str
    stage: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    method: str | None = None
    n_items: int = 0
    cost_usd: float = 0.0
    watermark: str | None = None
