"""Topic labelling tests (SPEC-007 increment).

The gateway is faked. The rules under test are the ones that decide whether a label can be trusted:
strict JSON parsing (no guessing), the outlier bucket never labelled, and an unusable answer leaving
the keyword label in place rather than inventing a name.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gtaf.application.topic_labels import (
    build_prompt,
    label_topics,
    parse_label,
)


class FakeGateway:
    """Gateway returning a fixed reply per prompt."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def ask(self, prompt: str, *, prompt_version: str, provider: str) -> object:
        """Record the prompt and return the canned reply."""
        self.prompts.append(prompt)
        return SimpleNamespace(text=self.reply)


class FakeRepo:
    """Topic persistence recording writes."""

    def __init__(self, topics: tuple[tuple[int, str | None, tuple[str, ...], int], ...]) -> None:
        self.topics = topics
        self.written: dict[int, tuple[str, str | None]] = {}

    def latest_topics_run(self) -> str | None:
        """Return a fixed run id."""
        return "run-1"

    def list_topics(self, run_id: str) -> tuple[tuple[int, str | None, tuple[str, ...], int], ...]:
        """Return the seeded topics."""
        return self.topics

    def update_topic_labels(self, run_id: str, labels: dict) -> int:
        """Record the labels."""
        self.written = dict(labels)
        return len(labels)


def test_parse_plain_json() -> None:
    """A bare JSON object is the expected shape."""
    assert parse_label('{"label_ka": "სასამართლო", "label_en": "courts"}') == (
        "სასამართლო",
        "courts",
    )


def test_parse_fenced_json() -> None:
    """Models often wrap JSON in a markdown fence; that is still parseable."""
    reply = '```json\n{"label_ka": "არჩევნები", "label_en": "elections"}\n```'
    assert parse_label(reply) == ("არჩევნები", "elections")


def test_parse_json_with_prose_around_it() -> None:
    """Surrounding prose is tolerated as long as exactly one object is present."""
    reply = 'აუცილებლად: {"label_ka": "ბიუჯეტი", "label_en": "budget"} დასასრულს.'
    assert parse_label(reply) == ("ბიუჯეტი", "budget")


def test_parse_rejects_missing_georgian_label() -> None:
    """An English-only answer is not a usable label for a Georgian corpus."""
    assert parse_label('{"label_en": "budget"}') is None


def test_parse_rejects_non_json() -> None:
    """Prose is not repaired by guessing: the topic keeps its keyword label."""
    assert parse_label("ვფიქრობ, ეს არის ბიუჯეტის თემა.") is None


def test_english_label_is_optional() -> None:
    """A Georgian-only reply is accepted; the English side is None."""
    assert parse_label('{"label_ka": "ენერგეტიკა"}') == ("ენერგეტიკა", None)


def test_prompt_asks_for_both_languages_and_json() -> None:
    """One call for two languages halves the quota cost."""
    prompt = build_prompt(("სასამართლო", "პარტია"), 51)
    assert '"label_ka"' in prompt
    assert '"label_en"' in prompt
    assert "სასამართლო" in prompt
    assert "51" in prompt


def test_outlier_bucket_is_never_labelled() -> None:
    """`unclassified` is a coverage statement, not a topic to be named."""
    repo = FakeRepo(
        (
            (0, None, ("სასამართლო",), 51),
            (-1, "unclassified", (), 910),
        )
    )
    result = label_topics(
        FakeGateway('{"label_ka": "სასამართლო პროცესები", "label_en": "court cases"}'),
        repo,
        provider="gemini",
    )

    assert result.labelled == 1
    assert result.skipped == 1
    assert set(repo.written) == {0}


def test_unusable_answer_keeps_the_keyword_label() -> None:
    """A model that answers in prose does not get to invent a name."""
    repo = FakeRepo(((0, None, ("სასამართლო",), 51),))
    result = label_topics(FakeGateway("ეს არის სასამართლოს თემა."), repo, provider="gemini")

    assert result.labelled == 0
    assert result.skipped == 1
    assert repo.written == {}


def test_no_topics_run_is_an_error() -> None:
    """Labelling before clustering is a configuration mistake, not an empty success."""

    class EmptyRepo(FakeRepo):
        def latest_topics_run(self) -> str | None:
            return None

    with pytest.raises(ValueError, match="no topics run"):
        label_topics(FakeGateway("{}"), EmptyRepo(()), provider="gemini")


def test_every_topic_is_asked_once() -> None:
    """Three real topics, three prompts — no re-asking, no skipping."""
    repo = FakeRepo(
        (
            (0, None, ("ა",), 10),
            (1, None, ("ბ",), 9),
            (2, None, ("გ",), 8),
        )
    )
    gateway = FakeGateway('{"label_ka": "ტესტი", "label_en": "test"}')

    result = label_topics(gateway, repo, provider="gemini")

    assert len(gateway.prompts) == 3
    assert result.labelled == 3
