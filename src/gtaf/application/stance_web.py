"""Stance labelling for web publications (SPEC-018).

The same prompt, the same labels, the same gates as broadcast stance — applied to article text. That is the
point: if the model recognises criticism in an opposition outlet's prose, then its low `critical` count for the
incumbent on the government channel is a property of that channel, not a blind spot.

The corpora stay separate: results land in `publication_stance`, never in `stance`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from gtaf.domain.actors import Actor, find_mentions
from gtaf.domain.stance import PROMPT_VERSION, build_prompt, parse_stance, summarise

# Below this, the "article" is a headline and no body: labelling it measures the headline, not the article.
MIN_EXCERPT_CHARS = 120


class Gateway(Protocol):
    """Subset of the LLM gateway this use case needs."""

    def ask(self, prompt: str, *, prompt_version: str, provider: str) -> object:
        """Return a response with ``text`` and ``model``."""
        ...


class PublicationReader(Protocol):
    """Source of stored publications."""

    def list_publications(
        self, *, source_id: str | None = None, limit: int = 500
    ) -> tuple[tuple[str, str, str, str, str], ...]:
        """Return ``(publication_id, source_id, title, excerpt, leaning)`` rows."""
        ...


class PublicationStanceStore(Protocol):
    """Persistence for publication stance labels."""

    def store_publication_stance(
        self, rows: Sequence[tuple[str, str, str, float, str, str, str, bool]], *, prompt_version: str
    ) -> int:
        """Write ``(publication_id, target, label, confidence, model, rationale, quote, verified)`` rows."""
        ...


@dataclass(frozen=True, slots=True)
class WebStanceResult:
    """Outcome of labelling one leak of publications.

    Attributes:
        target: Actor labelled.
        by_source: ``(source_id, leaning, counts)`` per source.
        labelled: Publications labelled in total.
        unparsable: Replies that could not be read.
        cost_usd: Spend.
    """

    target: str
    by_source: tuple[tuple[str, str, dict[str, int]], ...]
    labelled: int
    unparsable: int
    cost_usd: float
    skipped_no_text: int = 0


def label_publication_stance(
    gateway: Gateway,
    reader: PublicationReader,
    store: PublicationStanceStore,
    *,
    actor: Actor,
    provider: str,
    limit: int,
    source_id: str | None = None,
) -> WebStanceResult:
    """Label stance toward an actor across stored publications.

    Args:
        gateway: LLM gateway.
        reader: Publication source.
        store: Label persistence.
        actor: Target person.
        provider: Provider key.
        limit: Maximum publications to label.
        source_id: Restrict to one source, or None for all.

    Returns:
        Counts per source, so the government and opposition channels can be compared directly.

    Notes:
        Only publications whose title or excerpt mentions the target are sent. An article that never names the
        person cannot carry an evaluation of them, and sending it would invite the model to invent one.
    """
    # Scan the whole corpus, then stop after `limit` LLM calls. Reading rows is free; a call is not, so the
    # window must never be the thing that silently hides mentions — measured 2026-11-26, when a 120-row window
    # over 286 publications found one mention of a target who actually appears ten times.
    rows = reader.list_publications(source_id=source_id, limit=5000)
    stored_rows: list[tuple[str, str, str, float, str, str, str, bool]] = []
    counts: dict[tuple[str, str], list[str]] = {}
    unparsable = 0
    cost = 0.0

    processed = 0
    skipped_no_text = 0
    for publication_id, source, title, excerpt, leaning in rows:
        if processed >= limit:
            break
        if len(excerpt.strip()) < MIN_EXCERPT_CHARS:
            # A title alone is not the article. Measured 2026-11-27: with empty excerpts, a critical piece about
            # Ivanishvili came back `unclear`, and a piece whose only Ivanishvili line was a teaser came back
            # `critical` — both are artefacts of labelling on a headline.
            skipped_no_text += 1
            continue
        text = f"{title}. {excerpt}".strip()
        if not find_mentions(text, (actor,)):
            continue
        response = gateway.ask(
            build_prompt(text, target_en=actor.en, target_ka=actor.ka),
            prompt_version=PROMPT_VERSION,
            provider=provider,
        )
        cost += float(getattr(response, "cost_usd", 0.0))
        parsed = parse_stance(str(getattr(response, "text", "")), segment_text=text)
        processed += 1
        if parsed is None:
            unparsable += 1
            continue
        stored_rows.append(
            (
                publication_id,
                actor.actor_id,
                parsed.label,
                parsed.confidence,
                str(getattr(response, "model", "unknown")),
                parsed.rationale,
                parsed.quote,
                parsed.quote_verified,
            )
        )
        counts.setdefault((source, leaning), []).append(parsed.label)

    if stored_rows:
        store.store_publication_stance(stored_rows, prompt_version=PROMPT_VERSION)

    by_source = tuple(
        (source, leaning, summarise(labels))
        for (source, leaning), labels in sorted(counts.items())
    )
    return WebStanceResult(
        target=actor.actor_id,
        by_source=by_source,
        labelled=len(stored_rows),
        unparsable=unparsable,
        cost_usd=round(cost, 6),
        skipped_no_text=skipped_no_text,
    )


def _now() -> datetime:
    """Return the current UTC instant, naive (storage convention)."""
    return datetime.now(UTC).replace(tzinfo=None)
