"""Collector use case (SPEC-002 §3.1-§3.7).

Depends only on three protocols it declares itself, so the entire collector is testable offline with
a fake source. The composition root in ``gtaf.cli`` supplies the real yt-dlp source, the raw-file
store and the DuckDB repository (D-004).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from gtaf.domain.collector import (
    CaptionCue,
    UploadRef,
    VideoMeta,
    classify_caption,
    is_client_block,
    is_video_unavailable,
    is_within_window,
    match_programme,
)
from gtaf.domain.invariants import local_date_of
from gtaf.domain.models import CaptionKind, Channel, Programme, Video
from gtaf.infrastructure.logging_setup import log_event


class ClientBlockedError(RuntimeError):
    """The client is blocked (429 / bot check / 403). The run stops; nothing is worked around."""


class VideoUnavailableError(RuntimeError):
    """One video cannot be read (age gate, private, removed). The run continues (FR-6)."""


@dataclass(frozen=True, slots=True)
class FetchedVideo:
    """What a source returns for one video.

    Attributes:
        meta: Caption-relevant metadata.
        raw_payload: The original ``json3`` payload, or None when the video has no transcript.
        cues: Parsed, validated cues (contiguous ``idx``, ``end_s > start_s``).
    """

    meta: VideoMeta
    raw_payload: str | None
    cues: tuple[CaptionCue, ...]


class VideoSource(Protocol):
    """A place videos can be listed and fetched from (yt-dlp in production, a fake in tests)."""

    def list_uploads(self, handle: str, limit: int) -> Sequence[UploadRef]:
        """List a channel's recent uploads, newest first.

        Args:
            handle: Channel handle including the leading ``@``.
            limit: Maximum entries to list. Implementations MUST bound pagination.

        Returns:
            Upload references in listing order.
        """
        ...

    def fetch_video(self, video_id: str) -> FetchedVideo:
        """Fetch one video's metadata and captions, downloading no media.

        Args:
            video_id: YouTube video id.

        Returns:
            The fetched video.

        Raises:
            VideoUnavailableError: For a per-video condition; the caller skips it.
            ClientBlockedError: For a client-level block; the caller stops the run.
        """
        ...


class RawStore(Protocol):
    """Immutable store for original caption payloads (SPEC-002 §3.4)."""

    def write_once(
        self, channel_id: str, local_date: date, video_id: str, payload: str
    ) -> bool:
        """Write a payload only if no file exists yet.

        Args:
            channel_id: Owning channel slug.
            local_date: Broadcast date in Tbilisi local time.
            video_id: YouTube video id.
            payload: Raw ``json3`` text.

        Returns:
            True when written, False when a file already existed (which is never overwritten).
        """
        ...


class Repository(Protocol):
    """Persistence operations the collector needs."""

    def upsert_channel(self, channel: Channel) -> None:
        """Insert or update one channel."""
        ...

    def upsert_programme(self, programme: Programme) -> None:
        """Insert or update one programme."""
        ...

    def upsert_video(self, video: Video, cues: Sequence[CaptionCue]) -> None:
        """Insert or update one video and replace its cue rows atomically."""
        ...

    def has_video(self, video_id: str) -> bool:
        """Report whether a video is already stored.

        Args:
            video_id: YouTube video id.

        Returns:
            True when the video row exists. Used to make a backfill resumable at video granularity
            rather than at run granularity, so an interrupted collection does not re-fetch work
            already paid for at two seconds per video.
        """
        ...

    def start_run(self, stage: str, params_json: str) -> str:
        """Open a run row and return its id."""
        ...

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        n_items: int,
        watermark: str | None,
        error: str | None,
    ) -> None:
        """Finalise a run row."""
        ...


@dataclass(frozen=True, slots=True)
class CollectPlan:
    """What to collect.

    Attributes:
        since: Earliest publish date, inclusive.
        limit: Maximum videos kept per channel.
        listing_limit: Maximum uploads listed per channel (bounds pagination).
        skip_existing: When True, videos already in the database are not re-fetched. This makes a
            long backfill resumable: re-running after an interruption costs nothing for the work
            already done.
    """

    since: date
    limit: int
    listing_limit: int
    skip_existing: bool = False


@dataclass
class ChannelReport:
    """Per-channel coverage counters, printed as a first-class result (FR-10, §3.7).

    ``unclassified`` is deliberately reported: roughly 69 % of titles match no programme, and a
    reader who does not see that number will assume the classifier worked.
    """

    channel_id: str
    name_en: str
    listed: int = 0
    kept: int = 0
    captioned: int = 0
    no_caption: int = 0
    unclassified: int = 0
    skipped: int = 0
    already_present: int = 0
    errors: list[str] = field(default_factory=list)
    newest: date | None = None


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """Outcome of a collection run.

    Attributes:
        run_id: The ``runs`` row id.
        status: ``ok`` or ``blocked``.
        reports: One report per channel, in configuration order.
    """

    run_id: str
    status: str
    reports: tuple[ChannelReport, ...]


def _build_video(
    channel: Channel,
    programme_id: str | None,
    meta: VideoMeta,
    caption_kind: CaptionKind,
    caption_lang: str,
) -> Video:
    """Assemble the domain ``Video`` row for a fetched video.

    Args:
        channel: Owning channel.
        programme_id: Matched programme, or None.
        meta: Fetched metadata.
        caption_kind: ``manual``, ``auto`` or ``none``.
        caption_lang: Preferred caption language.

    Returns:
        The row to persist.

    Raises:
        ValueError: If the source reported no publish date, which the window rule already excludes;
            reaching here means the contract was violated.
    """
    if meta.published_at is None:
        raise ValueError(f"video {meta.video_id} has no published_at; it cannot enter the schema")
    return Video(
        video_id=meta.video_id,
        channel_id=channel.channel_id,
        programme_id=programme_id,
        published_at=meta.published_at,
        broadcast_date_local=local_date_of(meta.published_at),
        title=meta.title,
        duration_s=meta.duration_s,
        caption_kind=caption_kind,
        caption_lang=caption_lang,
        status="captioned" if caption_kind != "none" else "skipped_no_caption",
    )


def collect_channel(
    channel: Channel,
    programmes: Sequence[Programme],
    plan: CollectPlan,
    *,
    source: VideoSource,
    repo: Repository,
    raw_store: RawStore,
    logger: logging.Logger,
) -> ChannelReport:
    """Collect one channel's in-window videos.

    Args:
        channel: The channel to collect.
        programmes: Programmes belonging to this channel only.
        plan: Window, limit and listing cap.
        source: Video source adapter.
        repo: Repository adapter.
        raw_store: Immutable payload store.
        logger: Structured logger.

    Returns:
        The channel's coverage report.

    Raises:
        ClientBlockedError: If the client is blocked; the caller finalises the run as blocked.
    """
    report = ChannelReport(channel_id=channel.channel_id, name_en=channel.name_en)

    repo.upsert_channel(channel)
    for programme in programmes:
        repo.upsert_programme(programme)

    uploads = source.list_uploads(channel.youtube_handle, plan.listing_limit)
    report.listed = len(uploads)

    for upload in uploads:
        if report.kept >= plan.limit:
            break

        programme_id = match_programme(upload.title, programmes)
        if programme_id is None:
            report.unclassified += 1

        if plan.skip_existing and repo.has_video(upload.video_id):
            report.already_present += 1
            continue

        try:
            fetched = source.fetch_video(upload.video_id)
        except VideoUnavailableError as exc:
            # A per-video condition is not a failure of the run (FR-6). This is the behaviour that
            # the feasibility probe lacked, which cost it a 240-video run over one age-gated video.
            report.skipped += 1
            report.errors.append(f"{upload.video_id}: {exc}"[:300])
            log_event(logger, logging.WARNING, "collect.video_skipped",
                      channel=channel.channel_id, video_id=upload.video_id, error=str(exc)[:200])
            continue

        meta = fetched.meta
        published_local = local_date_of(meta.published_at) if meta.published_at else None
        if not is_within_window(published_local, plan.since):
            continue

        caption_kind, caption_lang = classify_caption(meta.manual_langs, meta.auto_langs)
        video = _build_video(channel, programme_id, meta, caption_kind, caption_lang)

        # Raw file first: a crash leaves an orphan file (reused next run) rather than a DB row
        # pointing at nothing (§3.4).
        if caption_kind != "none" and fetched.raw_payload:
            raw_store.write_once(
                channel.channel_id, video.broadcast_date_local, meta.video_id, fetched.raw_payload
            )

        repo.upsert_video(video, fetched.cues if caption_kind != "none" else ())

        report.kept += 1
        if caption_kind == "none":
            report.no_caption += 1
        else:
            report.captioned += 1
        if report.newest is None or video.broadcast_date_local > report.newest:
            report.newest = video.broadcast_date_local

    log_event(
        logger,
        logging.INFO,
        "collect.channel_done",
        channel=channel.channel_id,
        listed=report.listed,
        kept=report.kept,
        captioned=report.captioned,
        no_caption=report.no_caption,
        unclassified=report.unclassified,
        skipped=report.skipped,
        already_present=report.already_present,
    )
    return report


def run_collection(
    channels: Sequence[Channel],
    programmes_by_channel: Mapping[str, Sequence[Programme]],
    plan: CollectPlan,
    *,
    source: VideoSource,
    repo: Repository,
    raw_store: RawStore,
    logger: logging.Logger,
) -> CollectionResult:
    """Collect every requested channel, bookkeeping the run (§3.6).

    Args:
        channels: Channels to collect.
        programmes_by_channel: Programmes keyed by ``channel_id``.
        plan: Window, limit and listing cap.
        source: Video source adapter.
        repo: Repository adapter.
        raw_store: Immutable payload store.
        logger: Structured logger.

    Returns:
        The run id, final status and per-channel reports.

    Raises:
        ClientBlockedError: After the run row is marked ``blocked``, so a scheduler can see why.
    """
    params = json.dumps(
        {"since": plan.since.isoformat(), "limit": plan.limit,
         "listing_limit": plan.listing_limit},
        sort_keys=True,
    )
    run_id = repo.start_run("collect", params)
    reports: list[ChannelReport] = []
    watermark: date | None = None

    try:
        for channel in channels:
            report = collect_channel(
                channel,
                programmes_by_channel.get(channel.channel_id, ()),
                plan,
                source=source,
                repo=repo,
                raw_store=raw_store,
                logger=logger,
            )
            reports.append(report)
            if report.newest and (watermark is None or report.newest > watermark):
                watermark = report.newest
    except ClientBlockedError as exc:
        repo.finish_run(
            run_id,
            status="blocked",
            n_items=sum(r.kept for r in reports),
            watermark=watermark.isoformat() if watermark else None,
            error=str(exc)[:500],
        )
        raise
    except Exception as exc:
        repo.finish_run(
            run_id,
            status="failed",
            n_items=sum(r.kept for r in reports),
            watermark=watermark.isoformat() if watermark else None,
            error=f"{type(exc).__name__}: {exc}"[:500],
        )
        raise

    repo.finish_run(
        run_id,
        status="ok",
        n_items=sum(r.kept for r in reports),
        watermark=watermark.isoformat() if watermark else None,
        error=None,
    )
    return CollectionResult(run_id=run_id, status="ok", reports=tuple(reports))


__all__ = [
    "ChannelReport",
    "ClientBlockedError",
    "CollectPlan",
    "CollectionResult",
    "FetchedVideo",
    "RawStore",
    "Repository",
    "VideoSource",
    "VideoUnavailableError",
    "collect_channel",
    "is_client_block",
    "is_video_unavailable",
    "run_collection",
]
