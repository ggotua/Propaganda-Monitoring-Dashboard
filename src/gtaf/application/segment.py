"""Segmentation use case (SPEC-004 §3).

Composes the normaliser with the segmenter and the repository, so the CLI stays thin and the rules
remain testable without a database.
"""

from __future__ import annotations

from typing import Protocol

from gtaf.application.text import CueReader
from gtaf.domain.normalise import normalise_cues
from gtaf.domain.segment import (
    MAX_S,
    MIN_S,
    SEG_METHOD,
    SEG_VERSION,
    TARGET_S,
    SegmentDraft,
    segment_sentences,
)


class SegmentWriter(Protocol):
    """Persistence for segment rows."""

    def replace_segments(
        self,
        video_id: str,
        drafts: tuple[SegmentDraft, ...],
        seg_method: str,
        seg_version: str,
    ) -> int:
        """Replace one video's segments for a given method.

        Args:
            video_id: Owning video.
            drafts: Segments to insert.
            seg_method: Method name, e.g. ``fixed``.
            seg_version: Version of the method's rules.

        Returns:
            Number of rows written.
        """
        ...

    def list_video_ids(self) -> tuple[str, ...]:
        """Return every stored video id."""
        ...


def segment_video(
    video_id: str,
    reader: CueReader,
    writer: SegmentWriter,
    *,
    target_s: float = TARGET_S,
    max_s: float = MAX_S,
    min_s: float = MIN_S,
) -> int:
    """Normalise and segment one video, then persist the segments.

    Args:
        video_id: Video to segment.
        reader: Cue source.
        writer: Segment persistence.
        target_s: Window length to aim for.
        max_s: Hard ceiling per segment.
        min_s: Minimum trailing remainder.

    Returns:
        Number of segments written (zero for a video with no captions).
    """
    normalised = normalise_cues(reader.fetch_cues(video_id))
    drafts = segment_sentences(
        normalised.sentences, video_id, target_s=target_s, max_s=max_s, min_s=min_s
    )
    return writer.replace_segments(video_id, drafts, SEG_METHOD, SEG_VERSION)
