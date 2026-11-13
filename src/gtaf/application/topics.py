"""Topic modelling use case (SPEC-007).

Depends on protocols, so the pipeline is testable without loading an embedding model: the engine is
the only part that needs BERTopic, and it is injected.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from gtaf.domain.topics import (
    TOPIC_METHOD_VERSION,
    TopicAssignment,
    TopicSummary,
    summarise_assignments,
)

MIN_SEGMENTS_DEFAULT = 200


class InsufficientDataError(RuntimeError):
    """Raised when there are too few segments for clustering to mean anything (FR-6)."""


class TopicEngine(Protocol):
    """A clustering engine over segment texts."""

    @property
    def method_version(self) -> str:
        """Version string recorded on every assignment row (D-009)."""
        ...

    def fit(
        self, segment_ids: Sequence[str], texts: Sequence[str]
    ) -> tuple[tuple[TopicAssignment, ...], tuple[TopicSummary, ...]]:
        """Cluster texts into topics.

        Args:
            segment_ids: Segment identifiers, parallel to ``texts``.
            texts: Segment texts.

        Returns:
            One assignment per input segment (including outliers as ``topic_id = -1``) and one
            summary per topic.
        """
        ...


class SegmentReader(Protocol):
    """Source of segments to cluster."""

    def list_segments(self) -> tuple[tuple[str, str], ...]:
        """Return ``(segment_id, text)`` pairs."""
        ...


class TopicRepository(Protocol):
    """Persistence for topic results."""

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

    def replace_topic_results(
        self,
        run_id: str,
        assignments: Sequence[TopicAssignment],
        summaries: Sequence[TopicSummary],
        method_version: str,
    ) -> int:
        """Replace the active topic assignment for every segment.

        Args:
            run_id: Owning run.
            assignments: One assignment per segment.
            summaries: One summary per topic.
            method_version: Version recorded on every assignment row.

        Returns:
            Number of assignment rows written.
        """
        ...


@dataclass(frozen=True, slots=True)
class TopicResult:
    """Outcome of a topic run.

    Attributes:
        run_id: The ``runs`` row id.
        n_segments: Segments clustered.
        n_topics: Topics discovered, excluding the outlier bucket.
        n_outliers: Segments assigned ``-1``.
        method_version: Engine version string.
    """

    run_id: str
    n_segments: int
    n_topics: int
    n_outliers: int
    method_version: str

    @property
    def outlier_rate(self) -> float:
        """Share of segments that could not be clustered."""
        return self.n_outliers / self.n_segments if self.n_segments else 0.0


def run_topics(
    reader: SegmentReader,
    engine: TopicEngine,
    repo: TopicRepository,
    *,
    min_segments: int = MIN_SEGMENTS_DEFAULT,
) -> TopicResult:
    """Cluster all stored segments into topics and persist the result (FR-1…FR-7).

    Args:
        reader: Segment source.
        engine: Clustering engine.
        repo: Persistence.
        min_segments: Refuse below this many segments.

    Returns:
        A summary of the run.

    Raises:
        InsufficientDataError: If there are fewer than ``min_segments`` segments (FR-6). Clustering
            a handful of segments produces a confident-looking model that means nothing, so this
            fails rather than warns.
    """
    segments = reader.list_segments()
    if len(segments) < min_segments:
        raise InsufficientDataError(
            f"only {len(segments)} segments available; clustering needs at least {min_segments}. "
            f"Collect and segment more video first."
        )

    params = json.dumps(
        {
            "min_segments": min_segments,
            "engine": getattr(engine, "method_version", TOPIC_METHOD_VERSION),
        },
        sort_keys=True,
    )
    run_id = repo.start_run("topics", params)

    try:
        segment_ids = [segment_id for segment_id, _ in segments]
        texts = [text for _, text in segments]
        assignments, summaries = engine.fit(segment_ids, texts)
        repo.replace_topic_results(run_id, assignments, summaries, engine.method_version)
    except Exception as exc:
        repo.finish_run(
            run_id,
            status="failed",
            n_items=0,
            watermark=None,
            error=f"{type(exc).__name__}: {exc}"[:500],
        )
        raise

    # Recompute from the assignments actually returned rather than trusting the engine's summaries.
    consistent = summarise_assignments(assignments)
    n_outliers = sum(1 for assignment in assignments if assignment.topic_id == -1)
    repo.finish_run(
        run_id,
        status="ok",
        n_items=len(assignments),
        watermark=None,
        error=None,
    )
    return TopicResult(
        run_id=run_id,
        n_segments=len(assignments),
        n_topics=len(consistent) - (1 if -1 in consistent else 0),
        n_outliers=n_outliers,
        method_version=engine.method_version,
    )
