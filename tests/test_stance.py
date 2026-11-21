"""Stance labelling tests (SPEC-013).

The rules that matter: an unreadable reply is never coerced into a label, `unclear` is a real answer, and
only segments that mention the target are sent.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gtaf.application.stance import label_stance
from gtaf.domain.actors import Actor
from gtaf.domain.stance import LABELS, build_prompt, parse_stance, summarise

TARGET = Actor("saakashvili", "სააკაშვილი", "Saakashvili")


def test_parse_plain_json() -> None:
    """The expected shape parses."""
    parsed = parse_stance('{"label": "critical", "confidence": 0.8, "rationale": "harsh words"}')
    assert parsed is not None
    assert parsed.label == "critical"
    assert parsed.confidence == pytest.approx(0.8)


def test_parse_fenced_json() -> None:
    """Models often wrap JSON in a fence; that still parses."""
    parsed = parse_stance('```json\n{"label": "neutral", "confidence": 0.5}\n```')
    assert parsed is not None
    assert parsed.label == "neutral"


def test_unclear_is_a_real_answer() -> None:
    """`unclear` must survive parsing: it is the honest option, not a parse failure."""
    parsed = parse_stance('{"label": "unclear", "confidence": 0.9, "rationale": "no evaluation"}')
    assert parsed is not None
    assert parsed.label == "unclear"


def test_unknown_label_is_rejected() -> None:
    """A label outside the set is unusable rather than rounded to the nearest."""
    assert parse_stance('{"label": "positive", "confidence": 0.9}') is None


def test_missing_label_is_rejected() -> None:
    """A reply without a label cannot be stored."""
    assert parse_stance('{"confidence": 0.9}') is None


def test_prose_is_not_coerced_to_neutral() -> None:
    """Measured risk: coercing failures to `neutral` would inflate the most comfortable answer."""
    assert parse_stance("ვფიქრობ, ეს ტექსტი ნეიტრალურია.") is None


def test_confidence_is_clamped() -> None:
    """A model returning 1.7 gets 1.0, not an out-of-range value in the database."""
    parsed = parse_stance('{"label": "supportive", "confidence": 1.7}')
    assert parsed is not None
    assert parsed.confidence == 1.0


def test_summarise_includes_zero_labels() -> None:
    """Every label appears even at zero, so 'absent' cannot be read as 'not measured'."""
    counts = summarise(["critical", "critical"])
    assert counts == {"supportive": 0, "critical": 2, "neutral": 0, "unclear": 0}
    assert set(counts) == set(LABELS)


def test_prompt_offers_unclear_before_the_options() -> None:
    """The prompt must not nudge the model toward picking a side."""
    prompt = build_prompt("ტექსტი", target_en="Saakashvili", target_ka="სააკაშვილი")
    assert "unclear" in prompt
    assert "სააკაშვილი" in prompt
    assert '"label"' in prompt


class FakeGateway:
    """Gateway returning scripted replies in order."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls = 0

    def ask(self, prompt: str, *, prompt_version: str, provider: str) -> object:
        """Return the next scripted reply."""
        reply = self.replies[self.calls % len(self.replies)]
        self.calls += 1
        return SimpleNamespace(
            text=reply, model="fake-model", cost_usd=0.0001, prompt_version=prompt_version
        )


class FakeReader:
    """Reader with fixed segments."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts

    def list_segments(self, method: str | None = None) -> tuple[tuple[str, str], ...]:
        """Return numbered segments."""
        return tuple((f"seg{i}", text) for i, text in enumerate(self.texts))


class FakeStore:
    """Store capturing rows."""

    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def store_stance(self, rows, *, run_id):
        """Record rows."""
        self.rows.extend(rows)
        return len(rows)


def test_only_segments_mentioning_the_target_are_asked() -> None:
    """A segment that does not mention the person cannot carry their stance."""
    gateway = FakeGateway(['{"label": "critical", "confidence": 0.7, "rationale": "x"}'])
    reader = FakeReader(["სააკაშვილი კრიტიკულად", "ამინდი კარგია", "კობახიძე საუბრობს"])
    store = FakeStore()

    result = label_stance(
        gateway, reader, store, actor=TARGET, provider="fake", limit=10, method="drift"
    )

    assert result.asked == 1
    assert result.labelled == 1
    assert gateway.calls == 1


def test_unparsable_replies_are_counted_not_stored() -> None:
    """A reply that cannot be read is reported, not silently turned into a label."""
    gateway = FakeGateway(["ვფიქრობ, ეს ნეიტრალურია."])
    reader = FakeReader(["სააკაშვილი", "სააკაშვილი"])
    store = FakeStore()

    result = label_stance(
        gateway, reader, store, actor=TARGET, provider="fake", limit=10, method="drift"
    )

    assert result.unparsable == 2
    assert result.labelled == 0
    assert store.rows == []


def test_limit_stops_the_pass() -> None:
    """A limit keeps a first run cheap and bounded."""
    gateway = FakeGateway(['{"label": "neutral", "confidence": 0.5, "rationale": "x"}'])
    reader = FakeReader(["სააკაშვილი"] * 10)
    store = FakeStore()

    result = label_stance(
        gateway, reader, store, actor=TARGET, provider="fake", limit=3, method="drift"
    )

    assert result.asked == 3
    assert gateway.calls == 3


def test_counts_sum_to_labelled() -> None:
    """The reported denominator is the labelled rows, so percentages cannot exceed 100 %."""
    replies = [
        '{"label": "critical", "confidence": 0.6, "rationale": "x", "quote": "სააკაშვილი"}',
        '{"label": "unclear", "confidence": 0.4, "rationale": "y", "quote": "სააკაშვილი"}',
    ]
    gateway = FakeGateway(replies)
    store = FakeStore()

    result = label_stance(
        gateway,
        FakeReader(["სააკაშვილი"] * 4),
        store,
        actor=TARGET,
        provider="fake",
        limit=4,
        method="drift",
    )

    assert sum(result.counts.values()) == result.labelled


def test_quote_is_verified_against_the_segment() -> None:
    """Measured failure in the first review: rationales quoted words absent from the segment."""
    from gtaf.domain.stance import parse_stance, verify_quote

    text = "პრეზიდენტი დღეს ანტალიაში გაემგზავრება და კონფერენციაში მიიღებს მონაწილეობას"
    assert verify_quote("დღეს ანტალიაში გაემგზავრება", text) is True
    assert verify_quote("მან თქვა, რომ ყველაფერი ცრუობს", text) is False

    reply = '{"label": "neutral", "confidence": 0.5, "quote": "დღეს ანტალიაში", "rationale": "x"}'
    parsed = parse_stance(reply, segment_text=text)
    assert parsed is not None
    assert parsed.quote_verified is True


def test_invented_quote_is_marked_not_trusted() -> None:
    """An unverifiable quote keeps the label but records that its evidence is absent."""
    from gtaf.domain.stance import parse_stance

    text = "საქართველოს პრეზიდენტი ანტალიაშია"
    reply = (
        '{"label": "critical", "confidence": 0.9, "quote": "სრულიად გამოგონილი ციტატა", '
        '"rationale": "x"}'
    )
    parsed = parse_stance(reply, segment_text=text)

    assert parsed is not None
    assert parsed.quote_verified is False


def test_prompt_v2_states_the_target_rule_and_quote_duty() -> None:
    """The two v2 additions must be in the prompt, not only in a document."""
    from gtaf.domain.stance import build_prompt

    prompt = build_prompt("ტექსტი", target_en="Saakashvili", target_ka="სააკაშვილი")
    assert "არ არის მისი შეფასება" in prompt  # hostility to an associate is not the target's evaluation
    assert "quote" in prompt


def test_review_sample_covers_every_label_class() -> None:
    """G-8 needs the model's hard verdicts, not a draw that is 90 % `critical`."""
    from gtaf.application.stance import review_sample

    rows = (
        [("s1", "critical", 0.9, "r", "ტექსტი")] * 40
        + [("s2", "unclear", 0.5, "r", "ტექსტი")] * 5
        + [("s3", "neutral", 0.6, "r", "ტექსტი")] * 5
    )
    sample = review_sample(rows, actor=TARGET, size=12, seed=3)

    assert {row.label for row in sample} == {"critical", "unclear", "neutral"}
    assert len(sample) == 12


def test_review_sample_is_deterministic() -> None:
    """A review must be reproducible: same seed, same rows."""
    from gtaf.application.stance import review_sample

    rows = [("s1", "critical", 0.9, "r", "ა")] * 10 + [("s2", "unclear", 0.5, "r", "ბ")] * 10
    first = review_sample(rows, actor=TARGET, size=8, seed=11)
    second = review_sample(rows, actor=TARGET, size=8, seed=11)

    assert [(row.segment_id, row.label) for row in first] == [
        (row.segment_id, row.label) for row in second
    ]
    assert [row.number for row in first] == list(range(1, 9))


def test_review_row_shows_the_name_not_the_start_of_the_segment() -> None:
    """Found by opening the first generated file: the target sat past the truncation point."""
    from gtaf.application.stance import review_sample

    long_text = "შესავალი " * 60 + "სააკაშვილი კრიტიკულად " + "დასასრული " * 60
    sample = review_sample(
        [("s1", "critical", 0.9, "r", long_text)], actor=TARGET, size=1
    )

    assert "სააკაშვილი" in sample[0].text
    assert sample[0].text.startswith("…")
