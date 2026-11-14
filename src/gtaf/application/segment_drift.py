"""Drift segmentation use case (SPEC-006, D-027).

Composes the normaliser, the embedder and the segmenter: sentences in, drift-cut segments out. The
threshold is derived per video from that video's own distribution of neighbour similarities, because
a flat bulletin and a heated interview do not share a scale.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from gtaf.application.methods import ACTIVE_SEG_VERSION
from gtaf.application.text import CueReader
from gtaf.domain.normalise import Sentence, normalise_cues
from gtaf.domain.segment import SEG_METHOD_DRIFT, SegmentDraft, segment_by_drift
from gtaf.infrastructure.embeddings import Embedder, cosine

# Share of neighbour pairs below which a boundary is placed. Measured on 20 videos (D-027): 0.25
# gives a topic-separating gap of +0.217, where time-based rules produce -0.015.
DRIFT_QUANTILE = 0.25


class DriftSegmentWriter(Protocol):
    """Persistence for drift segments."""

    def replace_segments(
        self, video_id: str, drafts: tuple[SegmentDraft, ...], seg_method: str, seg_version: str
    ) -> int:
        """Replace one video's segments for a given method."""
        ...


def neighbour_similarities(
    sentences: Sequence[Sentence], vectors: Sequence[Sequence[float]]
) -> tuple[float, ...]:
    """Return cosine similarity between each sentence and the next.

    Args:
        sentences: Sentences in order (used only for its length).
        vectors: One vector per sentence, aligned.

    Returns:
        ``len(sentences) - 1`` similarities.

    Raises:
        ValueError: If vectors and sentences are not aligned.
    """
    if len(vectors) != len(sentences):
        raise ValueError("vectors must be aligned with sentences")
    return tuple(
        cosine(vectors[index], vectors[index + 1]) for index in range(len(vectors) - 1)
    )


def drift_threshold(
    similarities: Sequence[float], *, quantile: float = DRIFT_QUANTILE
) -> float:
    """Return the similarity below which a boundary is placed.

    Args:
        similarities: Neighbour similarities for one video.
        quantile: Share of pairs treated as a drop.

    Returns:
        The threshold, or 0.0 when there is nothing to compare.

    Notes:
        Per video, not global: a global cut-off would shatter a slowly modulated bulletin and merge a
        fast-moving interview.
    """
    if not similarities:
        return 0.0
    ordered = sorted(similarities)
    index = min(len(ordered) - 1, max(0, int(quantile * len(ordered))))
    return float(ordered[index])


def segment_video_drift(
    video_id: str,
    reader: CueReader,
    writer: DriftSegmentWriter,
    embedder: Embedder,
    *,
    quantile: float = DRIFT_QUANTILE,
) -> int:
    """Normalise, embed, segment by drift, then persist.

    Args:
        video_id: Video to segment.
        reader: Cue source.
        writer: Segment persistence.
        embedder: Local embedder.
        quantile: Share of neighbour pairs treated as a boundary.

    Returns:
        Number of segments written (zero for a video with no captions).
    """
    normalised = normalise_cues(reader.fetch_cues(video_id))
    sentences = normalised.sentences
    if not sentences:
        return 0

    vectors = embedder.encode([sentence.text for sentence in sentences])
    similarities = neighbour_similarities(sentences, vectors)
    threshold = drift_threshold(similarities, quantile=quantile)

    drafts = segment_by_drift(
        sentences, similarities, video_id, threshold=threshold
    )
    return writer.replace_segments(video_id, drafts, SEG_METHOD_DRIFT, ACTIVE_SEG_VERSION)
