"""Actor matching over noisy ASR text (SPEC-011).

Pure functions: dictionary in, mentions out. The hard part is not finding a name — it is finding it
when the caption engine merged or split tokens, or dropped the nominative ending. Georgian nouns
inflect, so a surname appears as stem plus a case ending, and ASR adds its own noise on top.

Design: a dictionary entry is a **stem** plus a set of endings; a token matches when it equals the
stem, equals the stem with a known ending, or is close enough to the stem that a typo explains the
difference.
Nothing here decides whether the mention is *correct* — that is the G-5 validation gate's job.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

# Georgian case and clitic endings that attach to surnames. Longest first, so the longest is tried
# before the shortest.
ENDINGS: tuple[str, ...] = (
    "ებისაც",
    "ებისა",
    "ებმა",
    "ებს",
    "ებით",
    "საც",
    "მაც",
    "იც",
    "ზეც",
    "ზე",
    "ში",
    "დან",
    "ემ",
    "ამ",
    "ისა",
    "ის",
    "სა",
    "მა",
    "ს",
    "ი",
    "ე",
    "ა",
    "ო",
    "ად",
    "მ",
    "ც",
)

# Minimum length for fuzzy matching: short stems collide with ordinary words — measured 2026-11-20,
# `მელია` (5 letters) matched `მედია` ("media"), `მერია` ("city hall") and `მეტია` ("more") at one edit
# apiece, inflating that actor to 79 segments from 4. No fuzzy matching below 7 characters.
MIN_FUZZY_LEN = 7

# Characters that must survive exactly for a fuzzy match. Found by the G-5 spot check: `პაპაშვილი`
# (a weather presenter, თამარ პაპაშვილი) is a different person from `პაპუაშვილი` (the parliament speaker),
# and one deleted უ made the matcher merge them. Two real people one vowel apart is the worst case for
# this feature, so the first four characters are not allowed to differ at all.
FUZZY_PREFIX = 4

# Similarity floor, applied together with edit distance: both must hold. The floor is low on purpose —
# edit distance does the discrimination, and the measured overlap of a genuine ASR slip
# (`სააკაშველი` for `სააკაშვილი`) is only 0.84.
FUZZY_MIN_RATIO = 0.80
SHORT_STEM = 9


def max_edits(stem_length: int) -> int:
    """Return how many character edits a typo may explain for a stem of this length.

    Args:
        stem_length: Length of the stem.

    Returns:
        Two edits for stems of 9+ characters, one for 6-8, none below the fuzzy floor.

    Notes:
        Length is the discriminator, not similarity: measured 2026-11-20, `გააცრია` ("sifted") sits 2
        edits from `გახარია` (stem 6) and `მდინარე` ("river") 2 from `მდინარაძე` (stem 8), while a real
        ASR slip `სააკაშველი` for `სააკაშვილი` (stem 9) is also 2 edits. Allowing two edits only from 9
        characters keeps the genuine slip and drops both common nouns.
    """
    if stem_length >= SHORT_STEM:
        return 2
    if stem_length >= MIN_FUZZY_LEN:
        return 1
    return 0


def _levenshtein(left: str, right: str, *, limit: int) -> int:
    """Return the edit distance, abandoned early once it exceeds ``limit``.

    Args:
        left: First string.
        right: Second string.
        limit: Maximum distance of interest.

    Returns:
        The distance, or ``limit + 1`` when it is larger.
    """
    if left == right:
        return 0
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]

# Words that look like names but are not. Kept explicit so the false-positive rule is auditable.
STOPWORDS: frozenset[str] = frozenset(
    {
        "საქართველო",
        "საქართველოს",
        "მთავრობა",
        "მთავრობის",
        "პარლამენტი",
        "პარლამენტის",
        "სასამართლო",
        "სასამართლოს",
    }
)


@dataclass(frozen=True, slots=True)
class Actor:
    """One dictionary entry.

    Attributes:
        actor_id: Stable key.
        ka: Nominative surname as written in text.
        en: English rendering for the report.
        role: Reader-facing descriptor; never used in analysis.
        aliases: Additional spellings (full names) that must match exactly or fuzzily.
    """

    actor_id: str
    ka: str
    en: str
    role: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Mention:
    """One matched occurrence.

    Attributes:
        actor_id: Which actor.
        token: The word as it appeared, so a reviewer can see the ASR spelling.
        method: ``exact``, ``ending`` or ``fuzzy`` — how the match was made.
        ratio: Similarity score; 1.0 for exact and ending matches.
    """

    actor_id: str
    token: str
    method: str
    ratio: float


def stem(surname: str) -> str:
    """Reduce a nominative surname to its stem.

    Args:
        surname: Surname as written, e.g. ``სააკაშვილი``.

    Returns:
        The stem without a trailing case ending, e.g. ``სააკაშვილ``.

    Notes:
        Only one ending is stripped. Stripping repeatedly would eat real letters — a four-letter
        stem would lose its final vowel and stop matching its own inflected forms.
    """
    lowered = surname.strip().lower()
    for ending in ENDINGS:
        if lowered.endswith(ending) and len(lowered) - len(ending) >= 3:
            return lowered[: -len(ending)]
    return lowered


def tokenise(text: str) -> tuple[str, ...]:
    """Split text into lowercase word tokens.

    Args:
        text: Segment text.

    Returns:
        Tokens with punctuation removed.

    Notes:
        Georgian does not use hyphens inside surnames, but ASR inserts spaces: a split surname is
        two tokens for one name. The matcher therefore works per token and cannot recover a split
        name by
        itself — the dictionary holds the full form, and a bigram pass catches it.
    """
    cleaned = text.replace("\u2014", " ").replace("\u2013", " ")
    cleaned = cleaned.replace("\u00ab", " ").replace("\u00bb", " ")
    for mark in ",.;:!?()[]\"'":
        cleaned = cleaned.replace(mark, " ")
    return tuple(token for token in cleaned.lower().split() if token)


def _similarity(left: str, right: str) -> float:
    """Return a similarity ratio between two tokens."""
    return SequenceMatcher(None, left, right).ratio()


def match_token(token: str, actor: Actor) -> Mention | None:
    """Decide whether one token refers to an actor.

    Args:
        token: Lowercase token.
        actor: Dictionary entry.

    Returns:
        A mention when the token matches, else None.

    Notes:
        Exact and ending matches are checked first because they are cheap and unambiguous; fuzzy
        matching requires a shared first character and a minimum length, which removes most accidental
        collisions.
    """
    if token in STOPWORDS:
        return None

    stem_value = stem(actor.ka)
    for alias in (actor.ka, *actor.aliases):
        alias_stem = stem(alias)
        for candidate in (alias.lower(), alias_stem):
            if token == candidate:
                return Mention(actor.actor_id, token, "exact", 1.0)

    if token == stem_value:
        return Mention(actor.actor_id, token, "exact", 1.0)
    for ending in ENDINGS:
        if token == stem_value + ending:
            return Mention(actor.actor_id, token, "ending", 1.0)

    if len(stem_value) >= MIN_FUZZY_LEN and token[:FUZZY_PREFIX] == stem_value[:FUZZY_PREFIX]:
        allowed = max_edits(len(stem_value))
        if allowed and _levenshtein(token, stem_value, limit=allowed) <= allowed:
            ratio = _similarity(token, stem_value)
            if ratio >= FUZZY_MIN_RATIO:
                return Mention(actor.actor_id, token, "fuzzy", round(ratio, 3))
    return None


def find_mentions(text: str, actors: Sequence[Actor]) -> tuple[Mention, ...]:
    """Find actor mentions in one segment.

    Args:
        text: Segment text.
        actors: Dictionary.

    Returns:
        Mentions in reading order, one per matched token, de-duplicated per actor per segment.

    Notes:
        A segment mentioning the same actor three times counts once. The unit of analysis is "did this
        segment mention X", not "how many times", because ASR repetition and the segmenter's length both
        inflate counts without carrying information.
    """
    tokens = tokenise(text)
    seen: set[str] = set()
    mentions: list[Mention] = []
    for token in tokens:
        for actor in actors:
            mention = match_token(token, actor)
            if mention is not None and mention.actor_id not in seen:
                seen.add(mention.actor_id)
                mentions.append(mention)
                break
    return tuple(mentions)


def load_actors(entries: Iterable[dict[str, object]]) -> tuple[Actor, ...]:
    """Build actors from parsed YAML.

    Args:
        entries: Raw dictionaries from `config/actors.yaml`.

    Returns:
        Actors in file order.

    Raises:
        ValueError: If an entry lacks ``id``, ``ka`` or ``en`` — a half-formed entry would silently never
            match, which is the worst failure mode for a dictionary.
    """
    actors: list[Actor] = []
    for entry in entries:
        missing = [key for key in ("id", "ka", "en") if not entry.get(key)]
        if missing:
            raise ValueError(f"actor entry missing {missing}: {entry}")
        aliases = entry.get("aliases") or ()
        alias_values = (
            tuple(str(alias) for alias in aliases) if isinstance(aliases, (list, tuple)) else ()
        )
        actors.append(
            Actor(
                actor_id=str(entry["id"]),
                ka=str(entry["ka"]),
                en=str(entry["en"]),
                role=str(entry.get("role") or ""),
                aliases=alias_values,
            )
        )
    return tuple(actors)
