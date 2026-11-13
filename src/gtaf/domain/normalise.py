"""Cue-to-sentence normalisation (SPEC-003).

Pure functions only: no I/O, no database, no clock, no randomness. Sentences are transient by
decision (D-017) — a deterministic function of `captions` plus `NORMALISER_VERSION`, never stored.

The rules exist because of what the real transcripts look like (`ASR-QUALITY.md`): cue boundaries
are not speech boundaries, `>>` marks a speaker turn, `[...]` marks non-speech, and ASR
occasionally emits a foreign script inside Georgian text.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from gtaf.domain.collector import CaptionCue

# Bumped whenever the rules below change in a way that changes output. Methods whose result depends
# on normalisation must record it (D-017).
NORMALISER_VERSION = "1"

# Non-speech events, e.g. [მუსიკა] (music), [ტაში] (applause).
_BRACKET_RE = re.compile(r"\[[^\]]*\]")

# Speaker-turn marker emitted by YouTube for Georgian broadcasts.
TURN_MARKER = ">>"

# A sentence ends on one of these, when followed by whitespace or end of text.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.?!…:])\s+")

# Merge limits.
MAX_GAP_S = 2.5
MAX_CHARS = 400

# Scripts allowed without raising the flag: Georgian (including the old block some fonts use),
# Latin, Cyrillic, plus digits and whatever punctuation/space the text already contains.
_GEORGIAN_RANGES = ((0x10A0, 0x10FF), (0x2D00, 0x2D2F), (0x1C90, 0x1CBF))
_CYRILLIC_RANGE = (0x0400, 0x04FF)

FLAG_FOREIGN_SCRIPT = "foreign_script"


@dataclass(frozen=True, slots=True)
class Sentence:
    """One normalised sentence.

    Attributes:
        start_s: Start of the first contributing cue, in seconds.
        end_s: End of the last contributing cue, in seconds.
        text: Merged text with markers removed and whitespace collapsed.
        turn_index: Speaker turn, 0-based and non-decreasing, derived from `>>` markers.
        flags: Sorted tuple of quality flags, e.g. ``("foreign_script",)``.
    """

    start_s: float
    end_s: float
    text: str
    turn_index: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalisationResult:
    """Output of one video's normalisation.

    Attributes:
        sentences: Sentences in time order.
        n_events: Number of bracketed non-speech events removed.
        n_flagged: Number of sentences carrying at least one flag.
        version: The normaliser version that produced this result.
    """

    sentences: tuple[Sentence, ...]
    n_events: int
    n_flagged: int
    version: str = NORMALISER_VERSION


@dataclass(frozen=True, slots=True)
class _Token:
    """A fragment of text with its span, belonging to one cue and one turn."""

    text: str
    start_s: float
    end_s: float
    turn_index: int
    gap_before: float


def has_foreign_script(text: str) -> bool:
    """Return True when the text contains letters outside Georgian, Latin and Cyrillic.

    Args:
        text: Candidate sentence text.

    Returns:
        True when at least one letter falls outside those scripts. Digits, punctuation and
        whitespace never trigger the flag.

    Notes:
        This detects, it never corrects. A Devanagari word inside Georgian text is real ASR output
        (`ASR-QUALITY.md` §3) and must survive to the report, flagged, rather than be silently
        rewritten into something the channel did not broadcast.
    """
    for char in text:
        if not char.isalpha():
            continue
        code = ord(char)
        if any(low <= code <= high for low, high in _GEORGIAN_RANGES):
            continue
        if "a" <= char.lower() <= "z":
            continue
        if _CYRILLIC_RANGE[0] <= code <= _CYRILLIC_RANGE[1]:
            continue
        return True
    return False


def _tokens(cues: Sequence[CaptionCue]) -> tuple[list[_Token], int]:
    """Turn cues into sentence fragments, removing bracket events and splitting turns.

    Args:
        cues: Caption cues, in any order.

    Returns:
        The fragments in time order, and the number of bracketed events removed.
    """
    tokens: list[_Token] = []
    n_events = 0
    turn_index = 0
    previous_end: float | None = None

    for cue in sorted(cues, key=lambda item: item.idx):
        n_events += len(_BRACKET_RE.findall(cue.text))
        cleaned = " ".join(_BRACKET_RE.sub(" ", cue.text).split())
        gap_before = 0.0 if previous_end is None else max(cue.start_s - previous_end, 0.0)

        if cleaned:
            for position, segment in enumerate(cleaned.split(TURN_MARKER)):
                if position > 0:
                    turn_index += 1
                    # A new speaker is a hard boundary; the gap rule must not merge across it.
                    gap_before = MAX_GAP_S + 1.0
                piece = segment.strip()
                if not piece:
                    continue
                fragments = [fragment.strip() for fragment in _SENTENCE_SPLIT_RE.split(piece)]
                fragments = [fragment for fragment in fragments if fragment]
                # Split the cue's span across its fragments by character count. Without this, every
                # fragment of one cue would claim the whole cue span and successive sentences would
                # overlap in time — visible immediately in a spot-check of a real bulletin.
                total_chars = sum(len(fragment) for fragment in fragments) or 1
                cursor = cue.start_s
                for index, fragment in enumerate(fragments):
                    share = (len(fragment) / total_chars) * (cue.end_s - cue.start_s)
                    token_start = cursor
                    token_end = cursor + share
                    cursor = token_end
                    tokens.append(
                        _Token(
                            text=fragment,
                            start_s=token_start,
                            end_s=token_end,
                            turn_index=turn_index,
                            gap_before=gap_before if index == 0 else 0.0,
                        )
                    )
        previous_end = cue.end_s if previous_end is None else max(previous_end, cue.end_s)

    return tokens, n_events


def _ends_sentence(text: str) -> bool:
    """Return True when the fragment ends with a sentence terminator."""
    return bool(text) and text[-1] in ".?!…:"


def normalise_cues(
    cues: Sequence[CaptionCue], *, version: str = NORMALISER_VERSION
) -> NormalisationResult:
    """Merge caption cues into timestamped sentences.

    Args:
        cues: Caption cues for one video.
        version: Normaliser version recorded on the result.

    Returns:
        The sentences, the count of non-speech events removed, and the count of flagged sentences.

    Notes:
        A sentence is flushed at a terminator, a turn change, a gap greater than ``MAX_GAP_S``, or
        when adding the next fragment would exceed ``MAX_CHARS``. Spans are monotonic because tokens
        are consumed in time order.
    """
    tokens, n_events = _tokens(cues)

    sentences: list[Sentence] = []
    buffer: list[str] = []
    start_s = 0.0
    end_s = 0.0
    current_turn = 0

    def flush() -> None:
        """Emit the buffered fragments as one sentence, if any."""
        nonlocal buffer
        if not buffer:
            return
        text = " ".join(buffer).strip()
        if text:
            flags: list[str] = []
            if has_foreign_script(text):
                flags.append(FLAG_FOREIGN_SCRIPT)
            sentences.append(
                Sentence(
                    start_s=start_s,
                    end_s=end_s,
                    text=text,
                    turn_index=current_turn,
                    flags=tuple(sorted(flags)),
                )
            )
        buffer = []

    for token in tokens:
        buffered_chars = sum(len(part) for part in buffer) + len(buffer)
        if buffer and (
            token.turn_index != current_turn
            or token.gap_before > MAX_GAP_S
            or buffered_chars + len(token.text) > MAX_CHARS
        ):
            flush()

        if not buffer:
            start_s = token.start_s
            current_turn = token.turn_index
        buffer.append(token.text)
        end_s = token.end_s

        if _ends_sentence(token.text):
            flush()

    flush()

    return NormalisationResult(
        sentences=_make_monotonic(sentences),
        n_events=n_events,
        n_flagged=sum(1 for sentence in sentences if sentence.flags),
        version=version,
    )


def _make_monotonic(sentences: list[Sentence]) -> tuple[Sentence, ...]:
    """Trim overlapping sentence ends so spans never overlap.

    Args:
        sentences: Sentences in start order.

    Returns:
        The same sentences with each ``end_s`` clipped to the next sentence's start where the source
        cues overlapped.

    Notes:
        YouTube's auto-caption cues sometimes overlap each other, so two sentences can claim the
        same second. The overlap is real in the source (`data/raw/` keeps it), but downstream
        segmentation would have to reason about overlapping spans for no benefit, so the earlier
        sentence is trimmed to the later one's start. Only the overlapping tail is lost — typically
        under three seconds — and a sentence is never shrunk to zero length.
    """
    if len(sentences) < 2:
        return tuple(sentences)

    adjusted: list[Sentence] = []
    for index, sentence in enumerate(sentences):
        if index + 1 < len(sentences):
            next_start = sentences[index + 1].start_s
            if sentence.end_s > next_start > sentence.start_s:
                sentence = Sentence(
                    start_s=sentence.start_s,
                    end_s=next_start,
                    text=sentence.text,
                    turn_index=sentence.turn_index,
                    flags=sentence.flags,
                )
        adjusted.append(sentence)
    return tuple(adjusted)
