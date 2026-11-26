"""Human review of publication stance (G-8 for the web corpus).

The broadcast stance labels have a human agreement figure; the publication labels do not. Without one, every web
stance number rests on a model agreeing with itself, which is the thing G-8 exists to prevent (D-023).

This module builds a review sample and scores it. It does not decide the sample by hand: the draw is
deterministic from a seed, stratified by source so one outlet cannot dominate a 30-item check.
"""

from __future__ import annotations

import csv
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from gtaf.domain.validation import Agreement, compare

STANCE_LABELS = ("supportive", "critical", "neutral", "unclear")


@dataclass(frozen=True, slots=True)
class ReviewRow:
    """One publication offered to a human reviewer.

    Attributes:
        publication_id: Publication key.
        source_id: Source.
        leaning: Source leaning.
        title: Headline.
        excerpt: Stored excerpt, the text the model saw.
        model_label: Label under review.
        confidence: Model confidence.
        target: Actor the label is about.
    """

    publication_id: str
    source_id: str
    leaning: str
    title: str
    excerpt: str
    model_label: str
    confidence: float
    target: str


def build_sample(
    rows: Sequence[tuple[str, str, str, str, str, float, str]],
    excerpts: dict[str, str],
    *,
    target: str,
    size: int,
    seed: int = 42,
    per_source_min: int = 2,
) -> tuple[ReviewRow, ...]:
    """Draw a review sample from labelled publications.

    Args:
        rows: ``(publication_id, source_id, leaning, title, label, confidence, target)``.
        excerpts: Publication id to stored excerpt.
        target: Label for the sample as a whole, for the header only.
        size: Requested sample size.
        seed: Random seed, so the same sample can be regenerated and audited.
        per_source_min: Floor per source, so a small source is still represented.

    Returns:
        The sample, ordered by source and title.

    Notes:
        Sampling is random *within* each source and proportional *across* sources. Sampling by model label would
        over-represent rare classes and flatter the agreement figure — the very thing being measured.

        Each row keeps **its own** target, because a pooled sample drawn from two actors is otherwise
        unlabelable: measured 2026-11-26, a reviewer had to assume one target for a sheet that mixed two, and the
        resulting agreement figure could not be interpreted.
    """
    by_source: dict[str, list[tuple[str, str, str, str, str, float, str]]] = {}
    for row in rows:
        by_source.setdefault(row[1], []).append(row)
    if not by_source:
        return ()

    generator = random.Random(seed)
    total = len(rows)
    quotas: dict[str, int] = {}
    for source, items in by_source.items():
        proportional = max(per_source_min, round(size * len(items) / total))
        quotas[source] = min(len(items), proportional)

    chosen: list[tuple[str, str, str, str, str, float, str]] = []
    for source, items in by_source.items():
        ordered = sorted(items, key=lambda item: item[0])
        generator.shuffle(ordered)
        chosen.extend(ordered[: quotas[source]])

    if len(chosen) > size:
        generator.shuffle(chosen)
        chosen = chosen[:size]

    sample = [
        ReviewRow(
            publication_id=row[0],
            source_id=row[1],
            leaning=row[2],
            title=row[3],
            excerpt=excerpts.get(row[0], ""),
            model_label=row[4],
            confidence=row[5],
            target=row[6],
        )
        for row in chosen
    ]
    return tuple(sorted(sample, key=lambda item: (item.target, item.source_id, item.title)))


def write_sample(sample: Sequence[ReviewRow], path: Path) -> int:
    """Write the sample as a CSV a reviewer can fill in a spreadsheet.

    Args:
        sample: Rows to write.
        path: Destination.

    Returns:
        Number of rows written.

    Notes:
        ``human_label`` is left empty on purpose: a prefilled column invites confirmation instead of judgement.
        The model's label sits two columns away so the reviewer can see it but must type their own.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "publication_id",
                "target",
                "source",
                "leaning",
                "title",
                "excerpt",
                "model_label",
                "confidence",
                "human_label",
                "note",
            ]
        )
        for row in sample:
            writer.writerow(
                [
                    row.publication_id,
                    row.target,
                    row.source_id,
                    row.leaning,
                    row.title,
                    row.excerpt[:1200],
                    row.model_label,
                    f"{row.confidence:.2f}",
                    "",
                    "",
                ]
            )
    return len(sample)


def read_labels(path: Path) -> list[tuple[str, str, str, str]]:
    """Read a filled review CSV.

    Args:
        path: File written by :func:`write_sample` and filled in by a human.

    Returns:
        ``(target, publication_id, human_label, model_label)`` for every filled row.

    Raises:
        ValueError: When a filled label is not one of the four allowed values, or when the target column is
            missing — a pooled sheet without targets cannot be scored at all, and failing loudly is better than
            producing one number for two questions.
    """
    rows: list[tuple[str, str, str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "target" not in reader.fieldnames:
            raise ValueError(
                "the sheet has no `target` column; regenerate it with `gtaf review-web` — a pooled sheet "
                "without targets cannot be scored"
            )
        for row in reader:
            publication_id = (row.get("publication_id") or "").strip()
            label = (row.get("human_label") or "").strip().lower()
            if not publication_id or not label:
                continue
            if label not in STANCE_LABELS:
                raise ValueError(
                    f"publication {publication_id}: {label!r} is not one of {', '.join(STANCE_LABELS)}"
                )
            rows.append(
                (
                    (row.get("target") or "").strip(),
                    publication_id,
                    label,
                    (row.get("model_label") or "").strip().lower(),
                )
            )
    return rows


def score(
    rows: Sequence[tuple[str, str, str, str]], *, min_items: int = 30
) -> dict[str, tuple[Agreement, bool]]:
    """Score a review against the model, per target.

    Args:
        rows: ``(target, publication_id, human_label, model_label)``.
        min_items: The G-8 sample floor, applied per target.

    Returns:
        Target to ``(agreement, floor_met)``. The floor is per target because a mixed sheet answered two
        questions, and a single aggregate would hide which one failed.

    Notes:
        Kappa is reported beside raw agreement: with `neutral` dominating the publication corpus, two labellers
        can agree 80 % of the time while barely beating chance, which is exactly the trap measured in SPEC-016.
    """
    grouped: dict[str, dict[str, str]] = {}
    models: dict[str, dict[str, str]] = {}
    for target, publication_id, human_label, model_label in rows:
        grouped.setdefault(target, {})[publication_id] = human_label
        models.setdefault(target, {})[publication_id] = model_label

    results: dict[str, tuple[Agreement, bool]] = {}
    for target, human in grouped.items():
        results[target] = (
            compare(human, models.get(target, {})),
            len(human) >= min_items,
        )
    return results
