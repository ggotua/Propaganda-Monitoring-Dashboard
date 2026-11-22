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
from gtaf.domain.actors import (
    Actor,
    ambiguous_mentions,
    find_mentions,
    match_token,
    title_conflict,
    tokenise,
)
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
        rows: Sequence[
            tuple[str, str, str, float, str, str, str | None, str, bool]
        ],
        *,
        run_id: str | None,
    ) -> int:
        """Write ``(segment_id, target, label, confidence, model, rationale, prompt_version, quote,
        quote_verified)`` rows."""
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
        verified: Labels whose quote was found verbatim in the segment.
        skipped_conflict: Segments dropped because a title contradicted the actor's role (D-031).
        counts: Label counts over the labelled rows.
        cost_usd: Total spend for this pass.
    """

    target: str
    asked: int
    labelled: int
    unparsable: int
    verified: int
    counts: dict[str, int]
    cost_usd: float
    skipped_conflict: int = 0


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
    skipped_conflict = 0
    for segment_id, text in reader.list_segments(method):
        mentions = find_mentions(text, (actor,))
        if not mentions:
            continue
        # D-031: a segment whose titles contradict the actor's role is a transcription artefact, and the
        # reviewer's pass showed these were still being labelled (Kavelashvili at COP31 counted as
        # Saakashvili). Excluded here as well as in the actor scan, so no stance label is produced for them.
        if title_conflict(text, actor) or ambiguous_mentions(mentions, (actor,)):
            skipped_conflict += 1
            continue
        candidates.append((segment_id, text))
        if limit and len(candidates) >= limit:
            break

    rows: list[tuple[str, str, str, float, str, str, str | None, str, bool]] = []
    labels: list[str] = []
    unparsable = 0
    verified = 0
    cost = 0.0

    for segment_id, text in candidates:
        response = gateway.ask(
            build_prompt(text, target_en=actor.en, target_ka=actor.ka),
            prompt_version=PROMPT_VERSION,
            provider=provider,
        )
        cost += float(getattr(response, "cost_usd", 0.0))
        parsed = parse_stance(str(getattr(response, "text", "")), segment_text=text)
        if parsed is None:
            unparsable += 1
            continue
        if parsed.quote_verified:
            verified += 1
        rows.append(
            (
                segment_id,
                actor.actor_id,
                parsed.label,
                parsed.confidence,
                str(getattr(response, "model", "unknown")),
                parsed.rationale,
                PROMPT_VERSION,
                parsed.quote,
                parsed.quote_verified,
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
        verified=verified,
        counts=summarise(labels),
        cost_usd=round(cost, 6),
        skipped_conflict=skipped_conflict,
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


def _near_duplicate(left: str, right: str, *, threshold: float = 0.85) -> bool:
    """Return True when two segments are near-identical by token overlap.

    Args:
        left: First text.
        right: Second text.
        threshold: Jaccard similarity above which they count as duplicates.

    Returns:
        True when the token sets overlap enough to be the same segment re-cut.

    Notes:
        The first two reviews found exact and near duplicates (#1/#10, #24/#26, and about a dozen summit
        scheduling reports). Exact-text dedupe missed them because the drift segmenter cuts the same passage
        at different offsets, so the strings differ slightly.
    """
    a = set(left.lower().split())
    b = set(right.lower().split())
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= threshold


def review_sample(
    rows: Sequence[tuple[str, str, float, str, str]],
    *,
    actor: Actor,
    size: int = 50,
    seed: int = 42,
    only_labels: Sequence[str] = (),
    dedupe: bool = True,
    text_chars: int = 300,
) -> tuple[ReviewRow, ...]:
    """Build a deterministic, label-stratified sample for the G-8 check.

    Args:
        rows: ``(segment_id, label, confidence, rationale, text)`` from storage.
        actor: Target person, used to centre each row on the mention.
        size: How many to offer.
        seed: Fixed seed, so a review is reproducible.
        only_labels: Restrict to these labels, for a targeted check of a rare class.
        dedupe: Drop rows whose segment text repeats an earlier row, exactly or nearly.
        text_chars: Maximum characters of segment text in a cell, so a viewer does not truncate the row.

    Returns:
        The sample, numbered.

    Notes:
        Three lessons from the reviews are encoded here. **Stratify by label**, because an overall figure
        hides a class the model gets wrong. **Exclude conflicted segments** (D-031), because Kavelashvili's
        COP31 coverage was labelled as Saakashvili. **Dedupe by similarity, not equality**, because
        near-identical rows made the sample smaller than its stated denominator.
    """
    if not rows:
        return ()

    import random

    from gtaf.domain.stance import LABELS

    filtered: list[tuple[str, str, float, str, str]] = []
    kept_texts: list[str] = []
    for row in rows:
        if only_labels and row[1] not in only_labels:
            continue
        if title_conflict(row[4], actor):
            continue
        if dedupe and any(_near_duplicate(row[4], other) for other in kept_texts):
            continue
        kept_texts.append(row[4])
        filtered.append(row)

    if not filtered:
        return ()

    rng = random.Random(seed)
    by_label: dict[str, list[int]] = {label: [] for label in LABELS}
    for index, row in enumerate(filtered):
        by_label.setdefault(row[1], []).append(index)

    chosen: list[int] = []
    if len(filtered) <= size:
        chosen = list(range(len(filtered)))
    else:
        # At least one per class first, then fill from the rest. Indices, not values: rows that are
        # identical tuples would otherwise all disappear from the pool at once and the sample would
        # silently come out short.
        for indices in by_label.values():
            if indices:
                chosen.append(rng.choice(indices))
        remaining = size - len(chosen)
        pool = [index for index in range(len(filtered)) if index not in set(chosen)]
        if remaining > 0 and pool:
            chosen.extend(rng.sample(pool, min(remaining, len(pool))))
    rng.shuffle(chosen)

    return tuple(
        ReviewRow(
            number=number,
            segment_id=filtered[index][0],
            label=filtered[index][1],
            confidence=filtered[index][2],
            rationale=filtered[index][3][:200].replace("|", "\\|").replace("\n", " "),
            text=_window_around_target(filtered[index][4], actor, width=text_chars // 2).replace(
                "|", "\\|"
            ),
        )
        for number, index in enumerate(chosen[:size], start=1)
    )


def _now() -> datetime:
    """Return the current UTC instant, naive (storage convention)."""
    return datetime.now(UTC).replace(tzinfo=None)
