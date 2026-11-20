"""Actor scan over the corpus (SPEC-011).

Counts how many segments mention each actor, using the active segmentation. The counts are **not** a
finding: they are a candidate list that the G-5 validation gate must approve before any of it
reaches
a report. This module therefore reports coverage and uncertainty alongside the numbers, and the CLI
refuses to present them as publishable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from gtaf.domain.actors import Actor, find_mentions, load_actors


class SegmentReader(Protocol):
    """Source of segment text."""

    def list_segments(self, method: str | None = None) -> tuple[tuple[str, str], ...]:
        """Return ``(segment_id, text)`` pairs."""
        ...


@dataclass(frozen=True, slots=True)
class ActorStat:
    """One actor's occurrence in a slice.

    Attributes:
        actor_id: Stable key.
        en: English name.
        ka: Georgian name.
        role: Reader descriptor.
        segments: Segments mentioning the actor.
        share: ``segments`` divided by analysed segments (denominator stated, not folded away).
        exact: Mentions matched exactly or via a case ending.
        fuzzy: Mentions matched only by similarity — the ones a human must check.
    """

    actor_id: str
    en: str
    ka: str
    role: str
    segments: int
    share: float
    exact: int
    fuzzy: int


@dataclass(frozen=True, slots=True)
class ActorScan:
    """Result of a scan.

    Attributes:
        analysed_segments: Denominator.
        stats: Per-actor rows, largest first.
        matched_segments: Segments with at least one actor mention.
        fuzzy_mentions: Total fuzzy matches, the audit workload.
    """

    analysed_segments: int
    stats: tuple[ActorStat, ...]
    matched_segments: int
    fuzzy_mentions: int


@dataclass(frozen=True, slots=True)
class SpotRow:
    """One mention offered for human verification (G-5).

    Attributes:
        number: Position in the sample, 1-based.
        actor_en: English name of the matched actor.
        actor_ka: Georgian name.
        token: The token that matched, as it appeared in the text.
        method: ``exact``, ``ending`` or ``fuzzy``.
        ratio: Match quality.
        segment_id: Where it came from, so a reviewer can trace it back.
        text: Segment text, truncated for reading.
    """

    number: int
    actor_en: str
    actor_ka: str
    token: str
    method: str
    ratio: float
    segment_id: str
    text: str


def collect_mentions(
    reader: SegmentReader, actors: Sequence[Actor], *, method: str
) -> tuple[tuple[str, str, object], ...]:
    """Return every mention as ``(segment_id, segment_text, Mention)``.

    Args:
        reader: Segment source.
        actors: Dictionary.
        method: Segmentation to analyse.

    Returns:
        Mentions in corpus order.
    """
    rows: list[tuple[str, str, object]] = []
    for segment_id, text in reader.list_segments(method):
        for mention in find_mentions(text, actors):
            rows.append((segment_id, text, mention))
    return tuple(rows)


def _context_around(text: str, token: str, *, width: int = 110) -> str:
    """Return the text around a matched token, with ellipses when trimmed.

    Args:
        text: Full segment text.
        token: Matched token.
        width: Characters to keep on each side.

    Returns:
        A window that always contains the token.

    Notes:
        Showing the first N characters instead was a real usability defect found on 2026-11-20: the match
        frequently sits late in the segment, so the reviewer saw a sentence with no name in it and could
        not judge the row at all.
    """
    cleaned = text.replace("\n", " ")
    position = cleaned.lower().find(token.lower())
    if position == -1:
        return cleaned[: width * 2]
    start = max(0, position - width)
    end = min(len(cleaned), position + len(token) + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(cleaned) else ""
    return f"{prefix}{cleaned[start:end]}{suffix}".replace("|", "\\|")


def spot_check_sample(
    reader: SegmentReader,
    actors: Sequence[Actor],
    *,
    method: str,
    size: int = 50,
    seed: int = 42,
) -> tuple[SpotRow, ...]:
    """Build a deterministic sample of mentions for the G-5 spot check.

    Args:
        reader: Segment source.
        actors: Dictionary.
        method: Segmentation to analyse.
        size: How many mentions to offer.
        seed: Fixed seed, so re-running produces the same sample and a review stays reproducible.

    Returns:
        The sample, ordered by number.

    Notes:
        The sample is **stratified on match method**, not fully random. Fuzzy matches are the ones a
        reviewer must see, and a pure random draw of 50 from 332 would typically contain one or two of
        them, leaving the riskiest class effectively unverified. Every fuzzy mention is included while
        the rest is a random draw, so the sample covers both what is frequent and what is doubtful.
    """
    name_by_id = {actor.actor_id: actor for actor in actors}
    mentions = collect_mentions(reader, actors, method=method)
    if not mentions:
        return ()

    fuzzy = [row for row in mentions if getattr(row[2], "method", "") == "fuzzy"]
    others = [row for row in mentions if getattr(row[2], "method", "") != "fuzzy"]

    import random

    rng = random.Random(seed)
    chosen: list[tuple[str, str, object]] = []
    if len(fuzzy) >= size:
        chosen = rng.sample(fuzzy, size)
    else:
        chosen = list(fuzzy)
        remaining = size - len(chosen)
        if remaining > 0:
            chosen.extend(rng.sample(others, min(remaining, len(others))))
    rng.shuffle(chosen)

    rows: list[SpotRow] = []
    for number, (segment_id, text, mention) in enumerate(chosen[:size], start=1):
        actor = name_by_id[getattr(mention, "actor_id", "")]
        rows.append(
            SpotRow(
                number=number,
                actor_en=actor.en,
                actor_ka=actor.ka,
                token=str(getattr(mention, "token", "")),
                method=str(getattr(mention, "method", "")),
                ratio=float(getattr(mention, "ratio", 0.0)),
                segment_id=segment_id,
                text=_context_around(text, str(getattr(mention, "token", ""))),
            )
        )
    return tuple(rows)


def load_actor_config(path: Path) -> tuple[Actor, ...]:
    """Read the actor dictionary from YAML.

    Args:
        path: Path to `config/actors.yaml`.

    Returns:
        Actors in file order.

    Raises:
        ValueError: If the file is missing or empty, because an empty dictionary would produce an
            empty scan that looks like "no actors mentioned" rather than "nothing configured".
    """
    if not path.exists():
        raise ValueError(f"actor dictionary not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"actor dictionary is empty: {path}")
    return load_actors(raw)


def scan_actors(reader: SegmentReader, actors: Sequence[Actor], *, method: str) -> ActorScan:
    """Count actor mentions across every segment of one segmentation.

    Args:
        reader: Segment source.
        actors: Dictionary.
        method: ``seg_method`` to analyse.

    Returns:
        The scan, with per-actor counts and the fuzzy-match workload.
    """
    segments = reader.list_segments(method)
    total = len(segments)
    per_actor: dict[str, dict[str, int]] = {
        actor.actor_id: {"segments": 0, "exact": 0, "fuzzy": 0} for actor in actors
    }
    matched = 0
    fuzzy_total = 0

    for _segment_id, text in segments:
        mentions = find_mentions(text, actors)
        if mentions:
            matched += 1
        for mention in mentions:
            bucket = per_actor[mention.actor_id]
            bucket["segments"] += 1
            if mention.method == "fuzzy":
                bucket["fuzzy"] += 1
                fuzzy_total += 1
            else:
                bucket["exact"] += 1

    stats = []
    for actor in actors:
        bucket = per_actor[actor.actor_id]
        stats.append(
            ActorStat(
                actor_id=actor.actor_id,
                en=actor.en,
                ka=actor.ka,
                role=actor.role,
                segments=bucket["segments"],
                share=bucket["segments"] / total if total else 0.0,
                exact=bucket["exact"],
                fuzzy=bucket["fuzzy"],
            )
        )
    stats.sort(key=lambda stat: (-stat.segments, stat.actor_id))
    return ActorScan(
        analysed_segments=total,
        stats=tuple(stats),
        matched_segments=matched,
        fuzzy_mentions=fuzzy_total,
    )


def audit_sample(
    reader: SegmentReader, actors: Sequence[Actor], *, method: str, limit: int = 50
) -> tuple[str, ...]:
    """Return readable lines of matched mentions for human review.

    Args:
        reader: Segment source.
        actors: Dictionary.
        method: Segmentation to analyse.
        limit: Maximum lines.

    Returns:
        One line per mention: actor, matched token, method and the segment text around it.

    Notes:
        This exists because G-5 requires a 50-mention spot check. The workload is concentrated in
        fuzzy matches, so the sample is ordered to show them first — checking the easy ones proves
        nothing.
    """
    lines: list[str] = []
    for segment_id, text in reader.list_segments(method):
        for mention in find_mentions(text, actors):
            if mention.method != "fuzzy":
                continue
            lines.append(
                f"FUZZY  {mention.actor_id:16} matched={mention.token!r:28} "
                f"ratio={mention.ratio:.2f} segment={segment_id}\n       {text[:160]}"
            )
            if len(lines) >= limit:
                return tuple(lines)
    return tuple(lines)
