"""Domain rules for topic modelling (SPEC-007).

Pure helpers only. The outlier bucket is a first-class topic here, because dropping it would inflate
the coverage of every other topic (SPEC-007 §3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

TOPIC_METHOD_VERSION = "bertopic-1"

# BERTopic's label for "no topic". Kept, never dropped.
OUTLIER_TOPIC_ID = -1
OUTLIER_LABEL = "unclassified"

# Georgian function words. Measured necessity, not caution: the first topic run put "და, რომ, ეს,
# არის, ამ, არ" at the top of every cluster, so the model was grouping grammar rather than subjects.
# The list is deliberately conservative — only unambiguous function words — because a wrong entry
# silently deletes real content from every topic.
GEORGIAN_STOPWORDS: tuple[str, ...] = (
    "და", "რომ", "ეს", "ამ", "ის", "ისინი", "არის", "არიან", "არ", "არა", "იყო", "იქნება",
    "მე", "ჩვენ", "თქვენ", "შენ", "რა", "როგორ", "როგორც", "როცა", "სად", "რატომ", "ვინ",
    "თუ", "ან", "მაგრამ", "ასევე", "თუმცა", "რადგან", "სანამ", "შემდეგ", "შორის", "გარეშე",
    "კი", "ხომ", "აბა", "აი", "უკვე", "ახლა", "აქ", "იქ", "ძალიან", "კიდევ", "მხოლოდ",
    "ყველა", "ყველას", "ბევრი", "ცოტა", "უნდა", "შეიძლება", "ამიტომ", "ერთი", "ესე",
)


@dataclass(frozen=True, slots=True)
class TopicAssignment:
    """One segment's topic assignment.

    Attributes:
        segment_id: Segment assigned.
        topic_id: Topic identifier, or ``-1`` for an outlier.
        probability: Membership probability when the engine provides one.
    """

    segment_id: str
    topic_id: int
    probability: float | None = None


@dataclass(frozen=True, slots=True)
class TopicSummary:
    """Metadata for one topic.

    Attributes:
        topic_id: Topic identifier, or ``-1``.
        label_ka: Georgian label. Until SPEC-005 exists this is the top keyword, not a phrase.
        label_en: English label, None in the keyword-only slice.
        keywords: Top terms, in rank order.
        n_segments: Number of segments assigned.
    """

    topic_id: int
    label_ka: str | None
    label_en: str | None
    keywords: tuple[str, ...]
    n_segments: int


def summarise_assignments(assignments: Sequence[TopicAssignment]) -> dict[int, int]:
    """Count segments per topic, including the outlier bucket.

    Args:
        assignments: Assignments to count.

    Returns:
        Mapping of topic id to segment count. The outlier bucket appears as ``-1`` when present.
    """
    counts: dict[int, int] = {}
    for assignment in assignments:
        counts[assignment.topic_id] = counts.get(assignment.topic_id, 0) + 1
    return counts


def topic_share(topic_id: int, assignments: Sequence[TopicAssignment]) -> float:
    """Return a topic's share of all segments, outliers included in the denominator.

    Args:
        topic_id: Topic whose share is wanted.
        assignments: All assignments.

    Returns:
        Share in ``[0, 1]``, computed over every segment. The denominator deliberately includes
        outliers: a share normalised over clustered segments only would overstate coverage.
    """
    if not assignments:
        return 0.0
    counts = summarise_assignments(assignments)
    return counts.get(topic_id, 0) / len(assignments)


def is_outlier(topic_id: int) -> bool:
    """Return True when an assignment is the outlier bucket.

    Args:
        topic_id: Topic identifier.

    Returns:
        True for ``-1``.
    """
    return topic_id == OUTLIER_TOPIC_ID
