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
from gtaf.domain.actors import Actor, find_mentions
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


def _now() -> datetime:
    """Return the current UTC instant, naive (storage convention)."""
    return datetime.now(UTC).replace(tzinfo=None)
