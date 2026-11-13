"""Normaliser use case (SPEC-003 §2).

Thin on purpose: the rules live in the domain, and this only fetches cues and applies them. The
protocol keeps the use case free of DuckDB (D-004).
"""

from __future__ import annotations

from typing import Protocol

from gtaf.domain.collector import CaptionCue
from gtaf.domain.normalise import NormalisationResult, normalise_cues


class CueReader(Protocol):
    """Source of a video's caption cues."""

    def fetch_cues(self, video_id: str) -> tuple[CaptionCue, ...]:
        """Return a video's cues in ``idx`` order.

        Args:
            video_id: YouTube video id.

        Returns:
            Cues for that video; an empty tuple when it has none.
        """
        ...


def sentences_for_video(video_id: str, reader: CueReader) -> NormalisationResult:
    """Normalise one video's cues into sentences.

    Args:
        video_id: YouTube video id.
        reader: Cue source.

    Returns:
        The normalisation result. An unknown or caption-less video yields an empty result rather
        than an error: a missing transcript is a data fact, not a failure (FR-7).
    """
    return normalise_cues(reader.fetch_cues(video_id))
