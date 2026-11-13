"""Normaliser tests (SPEC-003 §5 cases 1-11).

Every fixture in the spec's examples table appears here, including the ASR artefacts found in real
transcripts: bracket events, `>>` turn markers, run-on dialogue and foreign-script contamination.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from gtaf.domain.collector import CaptionCue
from gtaf.domain.normalise import (
    FLAG_FOREIGN_SCRIPT,
    MAX_CHARS,
    normalise_cues,
)


def _cue(idx: int, text: str, start: float, end: float) -> CaptionCue:
    """Build a caption cue."""
    return CaptionCue(idx=idx, start_s=start, end_s=end, text=text)


def test_bracket_only_cue_produces_no_sentence() -> None:
    """Case 1: music is not speech."""
    result = normalise_cues([_cue(0, "[მუსიკა]", 0.0, 2.0)])
    assert result.sentences == ()
    assert result.n_events == 1


def test_bracket_event_is_removed_but_counted() -> None:
    """Case 2: the sentence survives, the event is stripped and counted."""
    result = normalise_cues([_cue(0, "გამარჯობა.", 0.0, 1.0), _cue(1, "[ტაში]", 1.0, 2.0)])
    assert [s.text for s in result.sentences] == ["გამარჯობა."]
    assert result.n_events == 1


def test_turn_marker_starts_new_turn() -> None:
    """Case 3 / FR-2: `>>` separates speakers and is removed from the text."""
    result = normalise_cues([_cue(0, "სიტყვა A >> სიტყვა B", 0.0, 4.0)])
    texts = [s.text for s in result.sentences]
    turns = [s.turn_index for s in result.sentences]
    assert texts == ["სიტყვა A", "სიტყვა B"]
    assert turns == [0, 1]
    assert ">>" not in " ".join(texts)


def test_terminators_split_within_one_cue() -> None:
    """Case 4: one cue can contain several sentences."""
    result = normalise_cues([_cue(0, "სიტყვა A. სიტყვა B.", 0.0, 4.0)])
    assert [s.text for s in result.sentences] == ["სიტყვა A.", "სიტყვა B."]


def test_small_gap_does_not_split() -> None:
    """Case 5: 2.4 s is below the threshold."""
    cues = [_cue(0, "ერთი", 0.0, 1.0), _cue(1, "ორი", 3.4, 4.0)]
    assert len(normalise_cues(cues).sentences) == 1


def test_large_gap_splits() -> None:
    """Case 6: 2.6 s is above the threshold."""
    cues = [_cue(0, "ერთი", 0.0, 1.0), _cue(1, "ორი", 3.6, 4.0)]
    assert len(normalise_cues(cues).sentences) == 2


def test_length_cap_splits_run_on_text() -> None:
    """Case 7: a long run-on cue is capped rather than becoming one giant sentence."""
    long_text = "ა" * (MAX_CHARS // 2 + 10)
    result = normalise_cues([_cue(0, long_text, 0.0, 1.0), _cue(1, long_text, 1.0, 2.0)])
    assert len(result.sentences) == 2
    assert all(len(sentence.text) <= MAX_CHARS for sentence in result.sentences)


def test_foreign_script_is_flagged_and_preserved() -> None:
    """Case 8 / FR-4: Devanagari inside Georgian is detected, never rewritten."""
    text = "მშვიდობიანი თანაცხოვრება და इकोनॉमिक პარტნიორობა."
    result = normalise_cues([_cue(0, text, 0.0, 3.0)])
    sentence = result.sentences[0]
    assert FLAG_FOREIGN_SCRIPT in sentence.flags
    assert "इकोनॉमिक" in sentence.text
    assert result.n_flagged == 1


def test_georgian_and_latin_text_is_not_flagged() -> None:
    """A Georgian sentence with a Latin acronym or number is normal output, not contamination."""
    result = normalise_cues([_cue(0, "NATO-ს სამიტი 2026 წელს გაიმართა.", 0.0, 3.0)])
    assert result.sentences[0].flags == ()


def test_whitespace_is_collapsed() -> None:
    """Case 9."""
    result = normalise_cues([_cue(0, "  ზედმეტი   სივრცე  ", 0.0, 1.0)])
    assert result.sentences[0].text == "ზედმეტი სივრცე"


def test_no_cues_returns_empty() -> None:
    """Case 10 / FR-7."""
    result = normalise_cues([])
    assert result.sentences == ()
    assert result.n_events == 0


def test_deterministic() -> None:
    """Case 11 / FR-6: identical input, identical output."""
    cues = [
        _cue(0, "პირველი. >> მეორე [მუსიკა]", 0.0, 3.0),
        _cue(1, "მესამე", 6.0, 7.0),
    ]
    first = normalise_cues(cues)
    second = normalise_cues(cues)
    assert first == second


def test_spans_are_monotonic_and_inside_input() -> None:
    """FR-5: spans never go backwards and stay within the cues they came from."""
    cues = [
        _cue(0, "ერთი.", 0.0, 1.0),
        _cue(1, "ორი.", 1.2, 2.5),
        _cue(2, "სამი.", 2.7, 3.9),
    ]
    sentences = normalise_cues(cues).sentences
    assert all(a.end_s <= b.start_s for a, b in pairwise(sentences))
    assert sentences[0].start_s >= 0.0
    assert sentences[-1].end_s <= 3.9


def test_two_sentences_in_one_cue_do_not_overlap() -> None:
    """Regression: fragments of a single cue must not both claim the whole cue span.

    Found by spot-checking a real bulletin, where 82.6-86.6 began before 77.9-84.8 ended. FR-5 says
    spans are monotonic, and two sentences from one cue is the case that broke it.
    """
    result = normalise_cues([_cue(0, "პირველი წინადადება. მეორე წინადადება.", 10.0, 14.0)])
    first, second = result.sentences
    assert first.end_s <= second.start_s
    assert first.start_s >= 10.0
    assert second.end_s <= 14.0


def test_turn_indices_are_non_decreasing() -> None:
    """Turn arithmetic must not jump backwards when markers repeat in one cue."""
    cues = [_cue(0, "a >> b >> c >> d", 0.0, 4.0)]
    turns = [s.turn_index for s in normalise_cues(cues).sentences]
    assert turns == sorted(turns)


@pytest.mark.parametrize("text", ["[მუსიკა]", "[ტაში]", "[მუსიკა] [ტაში]"])
def test_multiple_bracket_events_all_counted(text: str) -> None:
    """Each bracketed event counts, and none produce text."""
    result = normalise_cues([_cue(0, text, 0.0, 1.0)])
    assert result.sentences == ()
    assert result.n_events == text.count("[")
