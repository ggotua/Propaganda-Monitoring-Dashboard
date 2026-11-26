"""Report data for the web corpus (SPEC-018).

Assembles everything the report needs into one object: what was collected, who it mentions, how stance splits by
leaning, and what the concordance currently licenses. The renderer only formats this; no number is computed in
the presentation layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from gtaf.domain.actors import Actor, find_mentions


class WebReportReader(Protocol):
    """Storage operations the report needs."""

    def publication_stats(self) -> Sequence[tuple[str, str, int, int, str | None, str | None]]:
        """Return ``(source_id, leaning, total, dated, first_day, last_day)``."""
        ...

    def list_publications(
        self, *, source_id: str | None = None, limit: int = 500
    ) -> Sequence[tuple[str, str, str, str, str]]:
        """Return ``(publication_id, source_id, title, excerpt, leaning)``."""
        ...

    def publication_stance_counts(self, target: str) -> Sequence[tuple[str, str, str, int]]:
        """Return ``(leaning, source_id, label, count)``."""
        ...


@dataclass(frozen=True, slots=True)
class SourceBlock:
    """One source as it appears in the report.

    Attributes:
        source_id: Source key.
        leaning: Editorial leaning label.
        total: Publications stored.
        dated: Publications carrying a publication date.
        first_day: Earliest date, when known.
        last_day: Latest date, when known.
        mentions: ``(actor_id, publications_mentioning, share)`` for the top actors.
        headline_sample: Three recent titles, for a reader who wants to see the material.
    """

    source_id: str
    leaning: str
    total: int
    dated: int
    first_day: str | None
    last_day: str | None
    mentions: tuple[tuple[str, int, float], ...]
    headline_sample: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StanceBlock:
    """Stance distribution for one actor, split by the source's leaning.

    Attributes:
        actor_id: Actor.
        rows: ``(source_id, leaning, supportive, critical, neutral, unclear)``.
    """

    actor_id: str
    rows: tuple[tuple[str, str, int, int, int, int], ...]


@dataclass(frozen=True, slots=True)
class ConcordanceBlock:
    """Website-versus-broadcast comparison, as measured.

    Attributes:
        available: Whether a comparison could be computed.
        source_id: Channel compared.
        start: First day.
        end: Last day.
        segments: Broadcast segments in the window.
        publications: Publications in the window.
        rho: Rank correlation.
        verdict: Plain-language reading.
    """

    available: bool
    source_id: str
    start: date | None
    end: date | None
    segments: int
    publications: int
    rho: float | None
    verdict: str


@dataclass(frozen=True, slots=True)
class WebReport:
    """Everything the web report shows.

    Attributes:
        generated_on: Build date.
        sources: Per-source blocks.
        stance: Per-actor stance blocks.
        concordance: The website-versus-broadcast check.
        caveats: Statements the reader must see before trusting a number.
    """

    generated_on: date
    sources: tuple[SourceBlock, ...]
    stance: tuple[StanceBlock, ...]
    concordance: ConcordanceBlock
    caveats: tuple[str, ...] = field(default_factory=tuple)


LABELS = ("supportive", "critical", "neutral", "unclear")


def build_web_report(
    reader: WebReportReader,
    *,
    actors: Sequence[Actor],
    stance_targets: Sequence[str],
    concordance: ConcordanceBlock | None,
    generated_on: date,
    top_actors: int = 8,
) -> WebReport:
    """Assemble the web report.

    Args:
        reader: Storage.
        actors: Actor dictionary for mention counting.
        stance_targets: Actors whose stance distribution is shown.
        concordance: Result of the website-versus-broadcast check, when one exists.
        generated_on: Build date.
        top_actors: How many actors to show per source.

    Returns:
        The report object.
    """
    rows = reader.list_publications(limit=10_000)
    by_source: dict[str, list[tuple[str, str]]] = {}
    leaning_by_source: dict[str, str] = {}
    recent: dict[str, list[str]] = {}
    for _publication_id, source, title, excerpt, leaning in rows:
        by_source.setdefault(source, []).append((title, excerpt))
        leaning_by_source[source] = leaning
        recent.setdefault(source, []).append(title)

    stats = {item[0]: item for item in reader.publication_stats()}
    sources: list[SourceBlock] = []
    for source, items in sorted(by_source.items()):
        stat = stats.get(source)
        total = int(stat[2]) if stat else len(items)
        dated = int(stat[3]) if stat else 0
        counts = []
        for actor in actors:
            hits = sum(1 for title, excerpt in items if find_mentions(f"{title} {excerpt}", (actor,)))
            if hits:
                counts.append((actor.actor_id, hits, hits / len(items) if items else 0.0))
        counts.sort(key=lambda item: item[1], reverse=True)
        sources.append(
            SourceBlock(
                source_id=source,
                leaning=leaning_by_source.get(source, "unknown"),
                total=total,
                dated=dated,
                first_day=str(stat[4]) if stat and stat[4] else None,
                last_day=str(stat[5]) if stat and stat[5] else None,
                mentions=tuple(counts[:top_actors]),
                headline_sample=tuple(recent.get(source, [])[:3]),
            )
        )

    stance_blocks: list[StanceBlock] = []
    for target in stance_targets:
        stance_counts = reader.publication_stance_counts(target)
        if not stance_counts:
            continue
        table: dict[tuple[str, str], dict[str, int]] = {}
        for leaning, source, label, count in stance_counts:
            table.setdefault((source, leaning), {name: 0 for name in LABELS})[label] = int(count)
        stance_blocks.append(
            StanceBlock(
                actor_id=target,
                rows=tuple(
                    (source, leaning, values["supportive"], values["critical"], values["neutral"], values["unclear"])
                    for (source, leaning), values in sorted(table.items())
                ),
            )
        )

    return WebReport(
        generated_on=generated_on,
        sources=tuple(sources),
        stance=tuple(stance_blocks),
        concordance=concordance
        or ConcordanceBlock(
            available=False,
            source_id="-",
            start=None,
            end=None,
            segments=0,
            publications=0,
            rho=None,
            verdict="No comparison was run, so no web figure may be described as airtime.",
        ),
        caveats=(
            "This is the web corpus. It is not airtime and never merged with broadcast segments (D-034).",
            "Stance is labelled on a 1,500-character excerpt by a language model, not by a human. "
            "The web corpus has no human agreement figure yet (G-8 is unmet here).",
            "`unclear` is a large class for the opposition outlet; treat it as an unstable boundary, "
            "not as neutrality.",
            "Concordance was measured on one channel and one window; it does not generalise.",
        ),
    )
