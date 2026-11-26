"""Concordance between a channel's website and its broadcast (SPEC-018, D-034 §4).

Before any web figure may be described as what a channel *broadcast*, the two corpora must be measured against
each other on an overlapping window. This module does that measurement and nothing else: it reports how closely
actor attention on the site tracks actor attention on air, and refuses to invent a verdict it cannot support.

The metric is deliberately simple. Actor mention shares are computed with the same matcher in both corpora, then
compared by rank correlation: a channel that covers the same people in the same order both places is a channel
whose website can stand in for its airtime on that dimension.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from gtaf.domain.actors import Actor, find_mentions


class ConcordanceReader(Protocol):
    """Two corpora behind one reader, so the comparison has no idea which storage it talks to."""

    def list_segments_with_date(
        self, method: str | None = None
    ) -> Sequence[tuple[str, str, str]]:
        """Return ``(segment_id, date_iso, text)`` for broadcast segments."""
        ...

    def list_publications_in_window(
        self, *, source_id: str, start: date, end: date
    ) -> Sequence[tuple[str, str, str]]:
        """Return ``(publication_id, title, excerpt)`` inside a date window."""
        ...


@dataclass(frozen=True, slots=True)
class ActorShare:
    """One actor's apparent attention in each corpus.

    Attributes:
        actor_id: Actor key.
        broadcast_share: Share of in-window segments mentioning the actor.
        web_share: Share of in-window publications mentioning the actor.
    """

    actor_id: str
    broadcast_share: float
    web_share: float


@dataclass(frozen=True, slots=True)
class ConcordanceReport:
    """Outcome of comparing one channel's two corpora.

    Attributes:
        source_id: Channel compared.
        start: First day of the window.
        end: Last day of the window.
        segments: In-window broadcast segments.
        publications: In-window publications.
        shares: Per-actor shares in both corpora.
        spearman: Rank correlation of the two share vectors, or None when it cannot be computed.
        verdict: Plain-language reading of the number.
    """

    source_id: str
    start: date
    end: date
    segments: int
    publications: int
    shares: tuple[ActorShare, ...]
    spearman: float | None
    verdict: str


def rank(values: Sequence[float]) -> list[float]:
    """Return average ranks, so ties do not distort a correlation.

    Args:
        values: Numbers to rank.

    Returns:
        Ranks starting at 1, with tied values sharing the mean rank.
    """
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for index in order[position : end + 1]:
            ranks[index] = average
        position = end + 1
    return ranks


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Compute Spearman's rank correlation.

    Args:
        left: First vector.
        right: Second vector.

    Returns:
        Correlation in ``[-1, 1]``, or None when it is undefined (fewer than three points, or no variation).

    Notes:
        Written out rather than pulled from a dependency: the project already avoids adding a numerical stack
        for two dozen numbers, and a hand implementation is checkable against a known case in the tests.
    """
    if len(left) != len(right) or len(left) < 3:
        return None
    left_ranks = rank(list(left))
    right_ranks = rank(list(right))
    mean_left = sum(left_ranks) / len(left_ranks)
    mean_right = sum(right_ranks) / len(right_ranks)
    numerator = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(left_ranks, right_ranks, strict=True)
    )
    left_var = sum((a - mean_left) ** 2 for a in left_ranks) ** 0.5
    right_var = sum((b - mean_right) ** 2 for b in right_ranks) ** 0.5
    if left_var == 0 or right_var == 0:
        return None
    return float(numerator / (left_var * right_var))


def compare(
    reader: ConcordanceReader,
    *,
    source_id: str,
    actors: Sequence[Actor],
    start: date,
    end: date,
    method: str,
    min_spearman: float = 0.7,
) -> ConcordanceReport:
    """Compare a channel's website against its broadcast over a window.

    Args:
        reader: Source of both corpora.
        source_id: Channel to compare.
        actors: Actors whose mention shares are compared.
        start: First day, inclusive.
        end: Last day, inclusive.
        method: Segmentation method for broadcast segments.
        min_spearman: Threshold above which the site may stand in for airtime.

    Returns:
        The report, including a verdict written in plain language.

    Notes:
        A share, not a count: the corpora differ in size by an order of magnitude, and comparing raw counts would
        measure corpus size rather than editorial attention.
    """
    segments = [
        (segment_id, text)
        for segment_id, day_iso, text in reader.list_segments_with_date(method)
        # Dates arrive as ISO strings from storage; parsing here keeps the reader dumb and the window explicit.
        if start <= date.fromisoformat(day_iso[:10]) <= end
    ]
    publications = list(
        reader.list_publications_in_window(source_id=source_id, start=start, end=end)
    )

    shares: list[ActorShare] = []
    for actor in actors:
        broadcast_hits = sum(
            1 for _id, text in segments if find_mentions(text, (actor,))
        )
        web_hits = sum(
            1
            for _id, title, excerpt in publications
            if find_mentions(f"{title} {excerpt}", (actor,))
        )
        shares.append(
            ActorShare(
                actor_id=actor.actor_id,
                broadcast_share=broadcast_hits / len(segments) if segments else 0.0,
                web_share=web_hits / len(publications) if publications else 0.0,
            )
        )

    active = [item for item in shares if item.broadcast_share or item.web_share]
    correlation = spearman(
        [item.broadcast_share for item in active], [item.web_share for item in active]
    )
    return ConcordanceReport(
        source_id=source_id,
        start=start,
        end=end,
        segments=len(segments),
        publications=len(publications),
        shares=tuple(shares),
        spearman=correlation,
        verdict=_verdict(correlation, len(active), len(segments), len(publications), min_spearman),
    )


def _verdict(
    correlation: float | None,
    actors_compared: int,
    segments: int,
    publications: int,
    threshold: float,
) -> str:
    """Write the plain-language reading of a correlation.

    Args:
        correlation: Spearman value, or None.
        actors_compared: Actors with at least one mention in either corpus.
        segments: In-window broadcast segments.
        publications: In-window publications.
        threshold: The project's threshold for substitution.

    Returns:
        One sentence stating what may and may not be claimed.
    """
    if correlation is None:
        return (
            f"Not computable: {actors_compared} actor(s) with any mention and {publications} publication(s). "
            "The site cannot be described as airtime on this evidence."
        )
    if correlation >= threshold:
        return (
            f"Concordant (rho={correlation:.2f} over {actors_compared} actors, {segments} segments, "
            f"{publications} publications): site attention tracks airtime on this window."
        )
    return (
        f"Below the {threshold:.1f} threshold (rho={correlation:.2f} over {actors_compared} actors). "
        "Web figures must be described as what the site published, never as airtime."
    )
