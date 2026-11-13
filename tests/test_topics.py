"""Topic modelling tests (SPEC-007).

The engine is faked, so these run without loading an embedding model. The rules under test are the
ones that decide whether a topic table can be trusted: outliers are kept, shares use every segment
in the denominator, and a tiny corpus is refused rather than clustered.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from gtaf.application.topics import (
    InsufficientDataError,
    TopicResult,
    run_topics,
)
from gtaf.domain.topics import (
    OUTLIER_TOPIC_ID,
    TopicAssignment,
    TopicSummary,
    is_outlier,
    summarise_assignments,
    topic_share,
)


class FakeEngine:
    """Engine returning a fixed assignment pattern: first two segments topic 0, rest outliers."""

    method_version = "fake-1"

    def __init__(self, assignments: dict[str, int] | None = None) -> None:
        self._assignments = assignments
        self.seen: list[str] = []

    def fit(
        self, segment_ids: Sequence[str], texts: Sequence[str]
    ) -> tuple[tuple[TopicAssignment, ...], tuple[TopicSummary, ...]]:
        """Assign topics from the configured mapping, defaulting to the outlier bucket."""
        self.seen = list(segment_ids)
        assignments = tuple(
            TopicAssignment(
                segment_id=segment_id,
                topic_id=(self._assignments or {}).get(segment_id, -1),
            )
            for segment_id in segment_ids
        )
        counts = summarise_assignments(assignments)
        summaries = tuple(
            TopicSummary(
                topic_id=topic_id,
                label_ka="keyword" if topic_id != -1 else "unclassified",
                label_en=None,
                keywords=("keyword",) if topic_id != -1 else (),
                n_segments=count,
            )
            for topic_id, count in sorted(counts.items())
        )
        return assignments, summaries


class FakeRepo:
    """Repository recording run lifecycle and stored results."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, object]] = {}
        self.assignments: tuple[TopicAssignment, ...] = ()
        self.summaries: tuple[TopicSummary, ...] = ()
        self.method_version: str | None = None

    def start_run(self, stage: str, params_json: str) -> str:
        """Open a fake run."""
        self.runs["run1"] = {"stage": stage, "status": "running", "params": params_json}
        return "run1"

    def finish_run(
        self, run_id: str, *, status: str, n_items: int, watermark: str | None, error: str | None
    ) -> None:
        """Finalise the fake run."""
        self.runs[run_id].update({"status": status, "n_items": n_items, "error": error})

    def replace_topic_results(
        self,
        run_id: str,
        assignments: Sequence[TopicAssignment],
        summaries: Sequence[TopicSummary],
        method_version: str,
    ) -> int:
        """Record stored results."""
        self.assignments = tuple(assignments)
        self.summaries = tuple(summaries)
        self.method_version = method_version
        return len(assignments)


class FakeReader:
    """Reader returning a fixed number of segments."""

    def __init__(self, count: int) -> None:
        self.count = count

    def list_segments(self) -> tuple[tuple[str, str], ...]:
        """Return ``count`` synthetic segments."""
        return tuple((f"seg{i}", f"text {i}") for i in range(self.count))


def test_too_few_segments_is_refused() -> None:
    """FR-6: clustering a handful of segments would produce a confident-looking nonsense model."""
    with pytest.raises(InsufficientDataError):
        run_topics(FakeReader(10), FakeEngine(), FakeRepo(), min_segments=200)


def test_outliers_are_stored_not_dropped() -> None:
    """FR-2: an unplaceable segment is a fact, and dropping it would inflate every other share."""
    repo = FakeRepo()
    result = run_topics(
        FakeReader(250), FakeEngine({"seg0": 0, "seg1": 0}), repo, min_segments=200
    )

    assert len(repo.assignments) == 250
    assert sum(1 for a in repo.assignments if a.topic_id == OUTLIER_TOPIC_ID) == 248
    assert result.n_outliers == 248
    assert result.outlier_rate > 0.9
    assert result.n_topics == 1


def test_run_is_finalised_ok() -> None:
    """FR-1: a successful run closes cleanly with its item count."""
    repo = FakeRepo()
    result = run_topics(FakeReader(250), FakeEngine({"seg0": 0}), repo, min_segments=200)

    assert repo.runs["run1"]["status"] == "ok"
    assert repo.runs["run1"]["n_items"] == 250
    assert result.run_id == "run1"


def test_engine_failure_marks_run_failed() -> None:
    """A crashed engine must not leave a run looking successful."""

    class BrokenEngine(FakeEngine):
        def fit(self, segment_ids, texts):
            raise RuntimeError("model exploded")

    repo = FakeRepo()
    with pytest.raises(RuntimeError):
        run_topics(FakeReader(250), BrokenEngine(), repo, min_segments=200)
    assert repo.runs["run1"]["status"] == "failed"
    assert "model exploded" in str(repo.runs["run1"]["error"])


def test_method_version_is_recorded() -> None:
    """D-009: results must be attributable to a method version."""
    repo = FakeRepo()
    run_topics(FakeReader(250), FakeEngine({"seg0": 0}), repo, min_segments=200)
    assert repo.method_version == "fake-1"


def test_share_uses_all_segments_in_denominator() -> None:
    """A share normalised over clustered segments only would overstate coverage."""
    assignments = [
        TopicAssignment("a", 0),
        TopicAssignment("b", 0),
        TopicAssignment("c", OUTLIER_TOPIC_ID),
        TopicAssignment("d", OUTLIER_TOPIC_ID),
    ]
    assert topic_share(0, assignments) == 0.5
    assert topic_share(OUTLIER_TOPIC_ID, assignments) == 0.5


def test_summarise_counts_include_outlier_bucket() -> None:
    """The outlier bucket appears as its own topic, so its size is reportable."""
    assignments = [TopicAssignment("a", 0), TopicAssignment("b", -1)]
    assert summarise_assignments(assignments) == {0: 1, -1: 1}
    assert is_outlier(-1) is True
    assert is_outlier(0) is False


def test_empty_assignments_give_zero_share() -> None:
    """No segments means no share, not a division error."""
    assert topic_share(0, []) == 0.0


def test_result_outlier_rate_is_safe_when_empty() -> None:
    """A zero-segment result must not divide by zero."""
    assert TopicResult("r", 0, 0, 0, "v").outlier_rate == 0.0
