"""Data for the public report (SPEC-018).

Assembles the finding, the method and the limits into one object. Nothing here formats; the renderer only
places values, so a number cannot be introduced in the presentation layer by accident.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

GOVERNMENT_FIGURES = (
    "kobakhidze",
    "ivanishvili",
    "garibashvili",
    "mdinaradze",
    "papuashvili",
    "kavelashvili",
    "bochorishvili",
)
OPPOSITION_FIGURES = ("saakashvili", "zourabichvili")


class PublicReader(Protocol):
    """Storage operations the public report needs."""

    def publication_stats(self) -> Sequence[tuple[str, str, int, int, str | None, str | None]]:
        """Return ``(source_id, leaning, total, dated, first_day, last_day)``."""
        ...

    def publication_stance_counts(self, target: str) -> Sequence[tuple[str, str, str, int]]:
        """Return ``(leaning, source_id, label, count)``."""
        ...


@dataclass(frozen=True, slots=True)
class GroupRow:
    """One (figure group by outlet leaning) cell of the headline table.

    Attributes:
        group: ``government`` or ``opposition``.
        leaning: Outlet leaning.
        publications: Stance-labelled publications in the cell.
        critical: How many carried a critical evaluation.
        supportive: How many carried a supportive one.
    """

    group: str
    leaning: str
    publications: int
    critical: int
    supportive: int

    @property
    def critical_rate(self) -> float:
        """Return the critical share of this cell."""
        return self.critical / self.publications if self.publications else 0.0


@dataclass(frozen=True, slots=True)
class TargetRow:
    """One target as the public report lists it.

    Attributes:
        target: Actor id.
        leaning: Outlet leaning.
        supportive: Supportive count.
        critical: Critical count.
        neutral: Neutral count.
        unclear: Unclear count.
    """

    target: str
    leaning: str
    supportive: int
    critical: int
    neutral: int
    unclear: int

    @property
    def total(self) -> int:
        """Return the cell total."""
        return self.supportive + self.critical + self.neutral + self.unclear


@dataclass(frozen=True, slots=True)
class PublicReport:
    """Everything the public report shows.

    Attributes:
        generated_on: Build date.
        publications: Corpus size.
        sources: ``(source_id, leaning, leaning_assigned, total, first_day, last_day)``.
        groups: Headline table cells.
        targets: Per-target table rows.
        labels: Total stance labels.
        versions: Provenance strings printed in the footer.
    """

    generated_on: date
    publications: int
    sources: tuple[tuple[str, str, bool, int, str | None, str | None], ...]
    groups: tuple[GroupRow, ...]
    targets: tuple[TargetRow, ...]
    labels: int
    versions: tuple[tuple[str, str], ...]


def build_public_report(
    reader: PublicReader,
    *,
    generated_on: date,
    leaning_assigned: dict[str, bool],
    versions: tuple[tuple[str, str], ...],
) -> PublicReport:
    """Assemble the public report.

    Args:
        reader: Storage.
        generated_on: Build date.
        leaning_assigned: Whether each source's leaning is an editorial judgement rather than a placeholder.
        versions: Provenance pairs, e.g. ``("matcher", "matcher-2026-11-28")``.

    Returns:
        The assembled report.

    Notes:
        Sources whose leaning is unassigned take part in the corpus count and are excluded from the headline
        table. Comparing them by a placeholder leaning would manufacture a finding.
    """
    stats = reader.publication_stats()
    sources = tuple(
        (
            str(source_id),
            str(leaning),
            bool(leaning_assigned.get(str(source_id), True)),
            int(total),
            str(first)[:10] if first else None,
            str(last)[:10] if last else None,
        )
        for source_id, leaning, total, _dated, first, last in stats
    )

    per_target: dict[str, dict[str, dict[str, int]]] = {}
    for target in (*GOVERNMENT_FIGURES, *OPPOSITION_FIGURES):
        for leaning, _source, label, count in reader.publication_stance_counts(target):
            per_target.setdefault(target, {}).setdefault(leaning, {})[label] = int(count)

    groups: list[GroupRow] = []
    for group, targets in (
        ("government", GOVERNMENT_FIGURES),
        ("opposition", OPPOSITION_FIGURES),
    ):
        for leaning in ("pro-government", "opposition"):
            cell = {"critical": 0, "supportive": 0}
            total = 0
            for target in targets:
                counts = per_target.get(target, {}).get(leaning, {})
                total += sum(counts.values())
                cell["critical"] += counts.get("critical", 0)
                cell["supportive"] += counts.get("supportive", 0)
            if total:
                groups.append(
                    GroupRow(
                        group=group,
                        leaning=leaning,
                        publications=total,
                        critical=cell["critical"],
                        supportive=cell["supportive"],
                    )
                )

    targets_rows: list[TargetRow] = []
    for target in (*GOVERNMENT_FIGURES, *OPPOSITION_FIGURES):
        for leaning, counts in sorted(per_target.get(target, {}).items()):
            targets_rows.append(
                TargetRow(
                    target=target,
                    leaning=leaning,
                    supportive=counts.get("supportive", 0),
                    critical=counts.get("critical", 0),
                    neutral=counts.get("neutral", 0),
                    unclear=counts.get("unclear", 0),
                )
            )

    return PublicReport(
        generated_on=generated_on,
        publications=sum(int(stat[2]) for stat in stats),
        sources=sources,
        groups=tuple(groups),
        targets=tuple(targets_rows),
        labels=sum(
            sum(counts.values()) for counts_by_target in per_target.values() for counts in counts_by_target.values()
        ),
        versions=versions,
    )
