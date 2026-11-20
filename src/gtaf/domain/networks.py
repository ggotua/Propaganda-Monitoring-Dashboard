"""Co-occurrence between actors (SPEC-012).

Pure counting: which actors appear in the same segment, how often, and how *surprisingly*. Raw counts
answer "who is talked about together most", which mostly answers "who is talked about most" — so every
pair also carries Jaccard, which divides by how often either appears and therefore does not simply reward
fame.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True, slots=True)
class PairStat:
    """One actor pair.

    Attributes:
        a: Lexicographically smaller actor id, so a pair has one canonical form.
        b: The other actor id.
        segments: Segments mentioning both.
        a_segments: Segments mentioning ``a`` at all.
        b_segments: Segments mentioning ``b`` at all.
        jaccard: ``segments / (a_segments + b_segments - segments)`` — 1.0 means they always appear
            together, 0.0 would mean never.
    """

    a: str
    b: str
    segments: int
    a_segments: int
    b_segments: int
    jaccard: float


def co_occurrence(
    segment_actor_sets: Iterable[Sequence[str]], *, min_segments: int = 2
) -> tuple[PairStat, ...]:
    """Count pairs of actors that appear in the same segment.

    Args:
        segment_actor_sets: One sequence of actor ids per segment.
        min_segments: Drop pairs seen together fewer times than this.

    Returns:
        Pairs ordered by co-occurrence, then Jaccard, then id.

    Notes:
        A pair is counted once per segment, not once per mention: the unit is "this segment discussed both",
        and a segment that repeats a name is not extra evidence of a relationship.
    """
    per_actor: dict[str, int] = {}
    pair_counts: dict[tuple[str, str], int] = {}

    for actors in segment_actor_sets:
        unique = sorted(set(actors))
        for actor in unique:
            per_actor[actor] = per_actor.get(actor, 0) + 1
        for a, b in combinations(unique, 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1

    stats: list[PairStat] = []
    for (a, b), both in pair_counts.items():
        if both < min_segments:
            continue
        a_count = per_actor[a]
        b_count = per_actor[b]
        union = a_count + b_count - both
        jaccard = both / union if union else 0.0
        stats.append(
            PairStat(a=a, b=b, segments=both, a_segments=a_count, b_segments=b_count,
                     jaccard=round(jaccard, 3))
        )

    stats.sort(key=lambda stat: (-stat.segments, -stat.jaccard, stat.a, stat.b))
    return tuple(stats)


def top_by_jaccard(
    stats: Sequence[PairStat], *, limit: int = 10, min_segments: int = 3
) -> tuple[PairStat, ...]:
    """Return the most *concentrated* pairs rather than the most frequent.

    Args:
        stats: Pairs from :func:`co_occurrence`.
        limit: How many to return.
        min_segments: Ignore thin pairs, where one coincidental segment produces a Jaccard of 1.0.

    Returns:
        Pairs ordered by Jaccard, then by co-occurrence.

    Notes:
        Without the ``min_segments`` floor, Jaccard is dominated by pairs that appear together once — a
        single segment gives 1.0, which is the opposite of evidence.
    """
    eligible = [stat for stat in stats if stat.segments >= min_segments]
    eligible.sort(key=lambda stat: (-stat.jaccard, -stat.segments, stat.a, stat.b))
    return tuple(eligible[:limit])
