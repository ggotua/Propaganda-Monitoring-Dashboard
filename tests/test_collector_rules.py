"""Domain rule tests for the collector (SPEC-002 §9 cases 3-8, 10)."""

from __future__ import annotations

from datetime import date

import pytest

from gtaf.domain.collector import (
    classify_caption,
    is_client_block,
    is_video_unavailable,
    is_within_window,
    match_programme,
)
from gtaf.domain.models import Programme


def _programme(programme_id: str, channel_id: str, patterns: tuple[str, ...]) -> Programme:
    """Build a programme for matching tests."""
    return Programme(
        programme_id=programme_id,
        channel_id=channel_id,
        name_en=programme_id,
        name_ka=None,
        type="news",
        title_patterns=patterns,
    )


def test_live_chat_only_is_no_caption() -> None:
    """Case 3 / FR-4: a live chat is viewer text, not a transcript."""
    assert classify_caption([], ["live_chat"]) == ("none", "")
    assert classify_caption(["live_chat"], []) == ("none", "")


def test_manual_wins_over_auto() -> None:
    """Case 4: a human-authored track is preferred when both exist."""
    assert classify_caption(["ka"], ["ka"]) == ("manual", "ka")


def test_georgian_preferred_over_other_languages() -> None:
    """Case 5: `ka` is chosen even when another language sorts first."""
    assert classify_caption([], ["en", "ka"]) == ("auto", "ka")


def test_no_tracks_at_all() -> None:
    """A video with no caption dictionaries at all is `none`."""
    assert classify_caption([], []) == ("none", "")


def test_falls_back_to_smallest_language_key() -> None:
    """An unexpected language still gets a deterministic value, not an empty string."""
    kind, lang = classify_caption([], ["fr", "de"])
    assert kind == "auto"
    assert lang == "de"


def test_programme_matching_uses_longest_pattern() -> None:
    """A specific marker beats a generic one."""
    programmes = [
        _programme("generic", "rustavi2", ("კურიერი",)),
        _programme("specific", "rustavi2", ("ბიზნესკურიერი",)),
    ]
    assert match_programme("ბიზნესკურიერი-2026.11.12", programmes) == "specific"


def test_programme_matching_does_not_cross_channels() -> None:
    """Case 7: Imedi must not inherit Rustavi 2's patterns."""
    rustavi = [_programme("rustavi2_news", "rustavi2", ("კურიერი",))]
    assert match_programme("კურიერი 12 საათზე", rustavi) == "rustavi2_news"
    # The same title with only Imedi's programmes matches nothing.
    imedi = [_programme("imedi_news", "imedi", ("ქრონიკა",))]
    assert match_programme("კურიერი 12 საათზე", imedi) is None


def test_title_without_marker_is_unclassified() -> None:
    """Case 8 / FR-5: no guess."""
    programmes = [_programme("imedi_news", "imedi", ("ქრონიკა",))]
    assert match_programme("საქართველოს პრეზიდენტი თურქ კოლეგას ხვდება", programmes) is None


def test_matching_is_case_insensitive() -> None:
    """Georgian has no case, but Latin markers in titles do."""
    programmes = [_programme("formula_interview", "formula", ("ინტერვიუ",))]
    title = "ვრცელი ინტერვიუ კოკი იონათამიშვილთან"
    assert match_programme(title, programmes) == "formula_interview"


@pytest.mark.parametrize(
    ("published", "expected"),
    [
        (date(2026, 10, 1), True),
        (date(2026, 9, 30), False),
        (date(2026, 11, 12), True),
        (None, False),
    ],
)
def test_window_boundary(published: date | None, expected: bool) -> None:
    """Case 9 boundary: `since` is inclusive; an unknown date is excluded."""
    assert is_within_window(published, date(2026, 10, 1)) is expected


@pytest.mark.parametrize(
    ("message", "block", "unavailable"),
    [
        ("ERROR: Sign in to confirm your age. This video may be inappropriate", False, True),
        ("ERROR: [youtube] x: Video unavailable", False, True),
        ("HTTP Error 429: Too Many Requests", True, False),
        ("Sign in to confirm you're not a bot", True, False),
        ("HTTP Error 403: Forbidden", True, False),
    ],
)
def test_error_classification(message: str, block: bool, unavailable: bool) -> None:
    """FR-6/FR-7: one is a skip, the other stops the run. Never confuse them."""
    assert is_client_block(message) is block
    assert is_video_unavailable(message) is unavailable


def test_age_gate_is_not_a_block() -> None:
    """The exact bug that aborted the feasibility probe must not reappear."""
    age_gate = "ERROR: Sign in to confirm your age, not a bot check"
    assert is_client_block(age_gate) is False
    assert is_video_unavailable(age_gate) is True
