"""Actor matching tests (SPEC-011).

These pin the matcher's tolerance: inflected forms must match, ASR typos must match within limits, and
ordinary political vocabulary must not be mistaken for a person.
"""

from __future__ import annotations

import pytest

from gtaf.application.actors import _context_around, spot_check_sample
from gtaf.domain.actors import (
    Actor,
    find_mentions,
    load_actors,
    match_token,
    stem,
    tokenise,
)

SAKASHVILI = Actor("saakashvili", "სააკაშვილი", "Saakashvili", "ex-president")
KOBAKHIDZE = Actor("kobakhidze", "კობახიძე", "Kobakhidze", "PM")
IVANISHVILI = Actor("ivanishvili", "ივანიშვილი", "Ivanishvili", "founder")


def test_stem_strips_one_ending() -> None:
    """A nominative surname loses its final vowel."""
    assert stem("სააკაშვილი") == "სააკაშვილ"


def test_stem_strips_trailing_e_so_the_nominative_still_matches() -> None:
    """`ბურჯანაძე` reduces to `ბურჯანაძ`, and the full form then matches via the `-ე` ending.

    Stripping is still single-pass: the guard keeps at least three characters, so a short name cannot be
    eaten down to nothing.
    """
    assert stem("ბურჯანაძე") == "ბურჯანაძ"
    mention = match_token("ბურჯანაძე", Actor("b", "ბურჯანაძე", "Burjanadze"))
    assert mention is not None
    # The dictionary form itself is an exact hit; the ending only matters for inflected occurrences.
    assert mention.method == "exact"


def test_exact_nominative_matches() -> None:
    """The dictionary form itself matches."""
    mention = match_token("სააკაშვილი", SAKASHVILI)
    assert mention is not None
    assert mention.method == "exact"


@pytest.mark.parametrize(
    "token",
    ["სააკაშვილს", "სააკაშვილმა", "სააკაშვილის", "სააკაშვილმაც", "სააკაშვილისა"],
)
def test_inflected_forms_match_via_ending(token: str) -> None:
    """Georgian case endings attach to the stem; all of these are the same person."""
    mention = match_token(token, SAKASHVILI)
    assert mention is not None
    assert mention.method in {"ending", "exact"}, token


@pytest.mark.parametrize(
    ("token", "actor"),
    [
        ("გახარიამ", Actor("gakharia", "გახარია", "Gakharia")),
        ("კობახიძემ", KOBAKHIDZE),
        ("ივანიშვილმა", IVANISHVILI),
        ("პაპუაშვილს", Actor("papuashvili", "პაპუაშვილი", "Papuashvili")),
    ],
)
def test_ergative_and_dative_forms_match_without_fuzzy(token: str, actor: Actor) -> None:
    """The ergative (-მა/-ემ/-ამ) is the most common form in speech, so it must not rely on fuzzy luck.

    Measured 2026-11-20: before these endings were added, `კობახიძემ` and `გახარიამ` were only reachable
    through fuzzy matching, where a stricter threshold could have dropped them.
    """
    mention = match_token(token, actor)
    assert mention is not None
    assert mention.method == "ending", token


def test_short_surname_does_not_match_a_common_verb() -> None:
    """Measured false positive: `გახარია` (stem 6) matched `გააცრია` ("sifted") at 0.86.

    Short stems now require 0.90, which rejects this without losing `კობახიძ` for `კობახიძე`.
    """
    assert match_token("გააცრია", Actor("gakharia", "გახარია", "Gakharia")) is None


def test_long_stem_still_matches_a_typo() -> None:
    """The stricter rule must not make long surnames unmatchable: one wrong letter is still the name."""
    mention = match_token("სააკაშველი", SAKASHVILI)
    assert mention is not None
    assert mention.method == "fuzzy"


def test_common_word_containing_a_surname_stem_is_rejected() -> None:
    """Measured false positive: `მდინარე` ("river") matched `მდინარაძე` at 0.88."""
    voter = Actor("mdinaradze", "მდინარაძე", "Mdinaradze")
    assert match_token("მდინარე", voter) is None


def test_asr_typo_matches_fuzzily() -> None:
    """A one-letter ASR error on a long surname is still that surname."""
    mention = match_token("სააკაშვილო", SAKASHVILI)
    assert mention is not None


def test_dropped_suffix_still_matches() -> None:
    """ASR sometimes drops the ending entirely; the bare stem must match."""
    assert match_token("კობახიძ", KOBAKHIDZE) is not None


def test_unrelated_word_does_not_match() -> None:
    """A different surname beginning with the same letter must not match."""
    assert match_token("კობახიძე", IVANISHVILI) is None


def test_short_tokens_are_not_fuzzy_matched() -> None:
    """Short stems collide with everything, so fuzzy matching is disabled below the length floor."""
    short = Actor("short", "სალი", "Sali")
    assert match_token("სალ", short) is not None  # exact stem, allowed
    assert match_token("სარკე", short) is None  # fuzzy, refused


def test_stopwords_never_match() -> None:
    """Institutional vocabulary that looks capitalised is not a person."""
    assert match_token("საქართველო", SAKASHVILI) is None
    assert match_token("პარლამენტი", KOBAKHIDZE) is None


def test_find_mentions_counts_once_per_segment() -> None:
    """Repeating a name in one segment is one mention: the unit is 'mentioned here', not frequency."""
    text = "სააკაშვილი და ივანიშვილი შეხვდნენ. სააკაშვილი კომენტარს არ აკეთებს."
    mentions = find_mentions(text, (IVANISHVILI, SAKASHVILI))

    assert sorted(m.actor_id for m in mentions) == ["ivanishvili", "saakashvili"]


def test_find_mentions_returns_nothing_for_plain_text() -> None:
    """A segment with no actors yields no mentions rather than a nearest guess."""
    assert (
        find_mentions("დღეს ამინდი კარგია და ქალაქში სამუშაოები მიმდინარეობს", (SAKASHVILI,)) == ()
    )


def test_tokenise_strips_punctuation_and_lowercases() -> None:
    """Tokens must be comparable regardless of punctuation the ASR emitted."""
    assert tokenise("სააკაშვილი, კობახიძე! «პარლამენტი».") == (
        "სააკაშვილი",
        "კობახიძე",
        "პარლამენტი",
    )


def test_load_actors_rejects_incomplete_entries() -> None:
    """A half-formed entry would silently never match — the worst failure for a dictionary."""
    with pytest.raises(ValueError, match="missing"):
        load_actors([{"id": "x", "ka": "სახელი"}])


def test_load_actors_reads_aliases() -> None:
    """Aliases let a full name and a surname point at the same actor."""
    actors = load_actors([{"id": "a", "ka": "სახელი", "en": "Name", "aliases": ["სრული სახელი"]}])
    assert actors[0].aliases == ("სრული სახელი",)


class FakeSegmentReader:
    """Reader returning fixed segment text."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts

    def list_segments(self, method: str | None = None) -> tuple[tuple[str, str], ...]:
        """Return numbered segments."""
        return tuple((f"seg{i}", text) for i, text in enumerate(self.texts))


def test_spot_check_is_deterministic_for_a_seed() -> None:
    """A review must be reproducible: the same seed yields the same rows."""
    reader = FakeSegmentReader([f"სააკაშვილი {i}" for i in range(60)])
    first = spot_check_sample(reader, (SAKASHVILI,), method="drift", size=10, seed=7)
    second = spot_check_sample(reader, (SAKASHVILI,), method="drift", size=10, seed=7)

    assert [row.segment_id for row in first] == [row.segment_id for row in second]
    assert [row.number for row in first] == list(range(1, 11))


def test_spot_check_always_includes_fuzzy_matches() -> None:
    """Fuzzy matches are the riskiest class; a random draw would leave them effectively unverified."""
    voter = Actor("mdinaradze", "მდინარაძე", "Mdinaradze")
    # `მდინარაჟ` is one letter off the stem (ძ -> ჟ) and is not a stem+ending form, so it can only
    # match fuzzily.
    texts = ["მდინარაძე" for _ in range(40)] + ["მდინარაჟ" for _ in range(2)]
    sample = spot_check_sample(FakeSegmentReader(texts), (voter,), method="drift", size=10, seed=1)

    assert sum(1 for row in sample if row.method == "fuzzy") == 2


def test_spot_check_returns_everything_when_small() -> None:
    """Fewer mentions than requested means all of them, not padding with repeats."""
    reader = FakeSegmentReader(["სააკაშვილი", "სააკაშვილი"])
    sample = spot_check_sample(reader, (SAKASHVILI,), method="drift", size=50)

    assert len(sample) == 2


def test_spot_check_empty_corpus() -> None:
    """No mentions means no sample, not an error."""
    assert spot_check_sample(FakeSegmentReader([]), (SAKASHVILI,), method="drift") == ()


def test_papashvili_is_not_papuashvili() -> None:
    """Found by the G-5 spot check: two different real people, one deleted უ apart.

    `თამარ პაპაშვილი` is a weather presenter; `შალვა პაპუაშვილი` is the parliament speaker. Merging them
    would put a broadcaster's weather slot in the speaker's count, so the first four characters of a fuzzy
    match must be identical.
    """
    speaker = Actor("papuashvili", "პაპუაშვილი", "Papuashvili")
    assert match_token("პაპაშვილი", speaker) is None
    assert match_token("პაპუაშვილი", speaker) is not None


def test_context_window_contains_a_late_token() -> None:
    """Found by inspecting the first generated file: the match sat past the truncation point."""
    text = "სიტყვა " * 80 + "კობახიძე" + " კიდევ " * 40
    window = _context_around(text, "კობახიძე", width=40)

    assert "კობახიძე" in window
    assert window.startswith("…")
    assert len(window) < 120
