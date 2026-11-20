"""Network use case (SPEC-012).

Turns the actor scan into pairs: which people are discussed in the same segment. The input is the same
mention data the report uses, so the network cannot disagree with the mention table.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from gtaf.domain.actors import Actor, find_mentions
from gtaf.domain.networks import PairStat, co_occurrence


class SegmentReader(Protocol):
    """Source of segment text, with and without the owning video."""

    def list_segments(self, method: str | None = None) -> tuple[tuple[str, str], ...]:
        """Return ``(segment_id, text)`` pairs."""
        ...

    def list_segments_with_video(
        self, method: str | None = None
    ) -> tuple[tuple[str, str, str], ...]:
        """Return ``(segment_id, video_id, text)`` triples."""
        ...


@dataclass(frozen=True, slots=True)
class NetworkResult:
    """A co-occurrence network over one slice.

    Attributes:
        unit: ``video`` or ``segment`` — what an edge's weight counts.
        analysed_units: Denominator: videos or segments analysed.
        units_with_two_or_more: Units mentioning at least two known actors; these are the only ones that
            can contribute an edge, so they explain a sparse graph.
        pairs: Pair statistics.
        actors_seen: Distinct actors mentioned.
    """

    unit: str
    analysed_units: int
    units_with_two_or_more: int
    pairs: tuple[PairStat, ...]
    actors_seen: int


def build_network(
    reader: SegmentReader,
    actors: Sequence[Actor],
    *,
    method: str,
    unit: str = "video",
    min_segments: int = 2,
) -> NetworkResult:
    """Build the actor co-occurrence network.

    Args:
        reader: Segment source.
        actors: Dictionary.
        method: Segmentation to analyse.
        unit: ``video`` (default) or ``segment``.
        min_segments: Minimum shared units for a pair to be kept.

    Returns:
        The network.

    Raises:
        ValueError: If ``unit`` is unknown.

    Notes:
        The default is the **video**, not the segment, because measurement forced it (D-030): at segment
        level only **21 of 4,837** segments mention two or more known actors (0.43 %) — a graph with six
        edges. At video level, **47 of 262** broadcasts do (17.9 %) with 22 repeated pairs. A segment is
        one story, so two named people rarely share one; a bulletin mentions several over half an hour.
        The weaker claim ("in the same broadcast") is the one this corpus can support.
    """
    if unit not in {"video", "segment"}:
        raise ValueError(f"unknown unit {unit!r}; expected 'video' or 'segment'")

    if unit == "video":
        grouped: dict[str, set[str]] = {}
        for _segment_id, video_id, text in reader.list_segments_with_video(method):
            grouped.setdefault(video_id, set()).update(
                mention.actor_id for mention in find_mentions(text, actors)
            )
        sets = [sorted(ids) for ids in grouped.values()]
        analysed = len(grouped)
    else:
        segments = reader.list_segments(method)
        sets = [
            sorted({mention.actor_id for mention in find_mentions(text, actors)})
            for _segment_id, text in segments
        ]
        analysed = len(segments)

    multi = sum(1 for ids in sets if len(ids) >= 2)
    return NetworkResult(
        unit=unit,
        analysed_units=analysed,
        units_with_two_or_more=multi,
        pairs=co_occurrence(sets, min_segments=min_segments),
        actors_seen=len({actor for ids in sets for actor in ids}),
    )
