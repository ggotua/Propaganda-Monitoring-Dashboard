"""Stance labelling use case (SPEC-013).

Selects segments that mention a target, asks the gateway for a stance label, and stores the result. The
labelling is cached by prompt hash (SPEC-005), so re-running is free and a prompt change is the only thing
that produces new calls.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from gtaf.application.actors import SegmentReader
from gtaf.domain.actors import Actor, find_mentions, match_token, tokenise
from gtaf.domain.stance import (
    PROMPT_VERSION,
    build_prompt,
    parse_stance,
    summarise,
)


class StanceStore(Protocol):
    """Persistence for stance labels."""

    def store_stance(
        self,
        rows: Sequence[tuple[str, str, str, float, str, str, str | None]],
        *,
        run_id: str | None,
    ) -> int:
        """Write ``(segment_id, target, label, confidence, model, rationale, prompt_version)`` rows."""
        ...


class Gateway(Protocol):
    """Subset of the LLM gateway this use case needs."""

    def ask(self, prompt: str, *, prompt_version: str, provider: str) -> object:
        """Return a response with ``text`` and ``model`` attributes."""
        ...


@dataclass(frozen=True, slots=True)
class StanceResult:
    """Outcome of a labelling pass.

    Attributes:
        target: Actor id labelled.
        asked: Segments that mentioned the target and were sent.
        labelled: Labels stored.
        unparsable: Replies that could not be read as a label.
        counts: Label counts over the labelled rows.
        cost_usd: Total spend for this pass.
    """

    target: str
    asked: int
    labelled: int
    unparsable: int
    counts: dict[str, int]
    cost_usd: float


def label_stance(
    gateway: Gateway,
    reader: SegmentReader,
    store: StanceStore,
    *,
    actor: Actor,
    provider: str,
    limit: int,
    method: str,
) -> StanceResult:
    """Label stance toward one actor over the segments that mention them.

    Args:
        gateway: LLM gateway.
        reader: Segment source.
        store: Stance persistence.
        actor: Target person.
        provider: Provider key.
        limit: Maximum segments to label; ``0`` means all.
        method: Segmentation to analyse.

    Returns:
        The result, including how many replies were unusable.

    Notes:
        Segments are taken in corpus order, not sampled: a sample would make the denominator unstable
        between runs, and the first version of a feature should be reproducible before it is clever.
    """
    candidates: list[tuple[str, str]] = []
    for segment_id, text in reader.list_segments(method):
        if find_mentions(text, (actor,)):
            candidates.append((segment_id, text))
        if limit and len(candidates) >= limit:
            break

    rows: list[tuple[str, str, str, float, str, str, str | None]] = []
    labels: list[str] = []
    unparsable = 0
    cost = 0.0

    for segment_id, text in candidates:
        response = gateway.ask(
            build_prompt(text, target_en=actor.en, target_ka=actor.ka),
            prompt_version=PROMPT_VERSION,
            provider=provider,
        )
        cost += float(getattr(response, "cost_usd", 0.0))
        parsed = parse_stance(str(getattr(response, "text", "")))
        if parsed is None:
            unparsable += 1
            continue
        rows.append(
            (
                segment_id,
                actor.actor_id,
                parsed.label,
                parsed.confidence,
                str(getattr(response, "model", "unknown")),
                parsed.rationale,
                PROMPT_VERSION,
            )
        )
        labels.append(parsed.label)

    if rows:
        store.store_stance(rows, run_id=None)

    return StanceResult(
        target=actor.actor_id,
        asked=len(candidates),
        labelled=len(rows),
        unparsable=unparsable,
        counts=summarise(labels),
        cost_usd=round(cost, 6),
    )


def _window_around_target(text: str, actor: Actor, *, width: int = 180) -> str:
    """Return text around the target's mention, falling back to the segment start.

    Args:
        text: Full segment text.
        actor: Target person.
        width: Characters to keep on each side.

    Returns:
        A window that contains the mention when the segment has one.

    Notes:
        Same defect as the G-5 file (SPEC-011): showing the first N characters hid the name, so a reviewer
        read a sentence with no target in it and could not judge the label. Inflected forms are located by
        matching tokens, not by substring search on the dictionary form.
    """
    cleaned = text.replace("\n", " ")
    position = -1
    for token in tokenise(cleaned):
        if match_token(token, actor) is not None:
            position = cleaned.lower().find(token)
            if position >= 0:
                break
    if position < 0:
        return cleaned[: width * 2]
    start = max(0, position - width // 2)
    end = min(len(cleaned), position + width * 2)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(cleaned) else ""
    return f"{prefix}{cleaned[start:end]}{suffix}"


@dataclass(frozen=True, slots=True)
class ReviewRow:
    """One labelled segment offered for human verification (G-8).

    Attributes:
        number: Position in the sample.
        segment_id: Where it came from.
        label: The model's verdict.
        confidence: The model's own confidence.
        rationale: The model's reason, so a reviewer sees what it was thinking.
        text: Segment text, windowed around the target where possible.
    """

    number: int
    segment_id: str
    label: str
    confidence: float
    rationale: str
    text: str


def review_sample(
    rows: Sequence[tuple[str, str, float, str, str]],
    *,
    actor: Actor,
    size: int = 50,
    seed: int = 42,
) -> tuple[ReviewRow, ...]:
    """Build a deterministic, label-stratified sample for the G-8 check.

    Args:
        rows: ``(segment_id, label, confidence, rationale, text)`` from storage.
        actor: Target person, used to centre each row on the mention.
        size: How many to offer.
        seed: Fixed seed, so a review is reproducible.

    Returns:
        The sample, numbered.

    Notes:
        Stratified **by label**, because an overall agreement figure hides a class the model gets wrong. A
        model that answers `critical` everywhere would score well on a sample drawn mostly from `critical`;
        every non-empty label class therefore contributes proportionally, with at least one row each.
    """
    if not rows:
        return ()

    import random

    from gtaf.domain.stance import LABELS

    rng = random.Random(seed)
    by_label: dict[str, list[int]] = {label: [] for label in LABELS}
    for index, row in enumerate(rows):
        by_label.setdefault(row[1], []).append(index)

    chosen: list[int] = []
    if len(rows) <= size:
        chosen = list(range(len(rows)))
    else:
        # At least one per class first, then fill from the rest. Indices, not values: rows that are
        # identical tuples (same segment text, same label) would otherwise all disappear from the pool at
        # once and the sample would silently come out short.
        for indices in by_label.values():
            if indices:
                chosen.append(rng.choice(indices))
        remaining = size - len(chosen)
        pool = [index for index in range(len(rows)) if index not in set(chosen)]
        if remaining > 0 and pool:
            chosen.extend(rng.sample(pool, min(remaining, len(pool))))
    rng.shuffle(chosen)

    return tuple(
        ReviewRow(
            number=number,
            segment_id=rows[index][0],
            label=rows[index][1],
            confidence=rows[index][2],
            rationale=rows[index][3][:200].replace("|", "\\|").replace("\n", " "),
            text=_window_around_target(rows[index][4], actor).replace("|", "\\|"),
        )
        for number, index in enumerate(chosen[:size], start=1)
    )


def _now() -> datetime:
    """Return the current UTC instant, naive (storage convention)."""
    return datetime.now(UTC).replace(tzinfo=None)
