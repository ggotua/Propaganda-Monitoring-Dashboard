"""Validator tests (SPEC-016).

The arithmetic is hand-verified, because a wrong kappa is invisible — it still looks like a number between
0 and 1 — and the vendor rule is enforced before any call is made.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gtaf.domain.llm import VendorConflictError
from gtaf.domain.validation import cohens_kappa, compare


def test_kappa_is_hand_verified() -> None:
    """10 items, 8 agreed, both marginals 6/4 → pe = 0.52 → kappa = 0.28/0.48 ≈ 0.583.

    Ordering matters, and two earlier versions of this test got it wrong, which is exactly why the
    example is written out:

        items 0-4  critical / critical   agree
        item  5    critical / unclear    disagree
        item  6    unclear  / critical   disagree
        items 7-9  unclear  / unclear    agree

    primary:   6 critical, 4 unclear
    secondary: 6 critical, 4 unclear
    po = 8/10 = 0.80
    pe = (6*6 + 4*4)/100 = 0.52
    kappa = (0.80 - 0.52)/(1 - 0.52) = 0.28/0.48 = 0.5833

    Note: a plain six-then-four list against seven-then-three agrees **nine** times (kappa 0.783), not
    eight - the labels must be laid out, not counted.
    """
    primary = [
        "critical",
        "critical",
        "critical",
        "critical",
        "critical",
        "critical",
        "unclear",
        "unclear",
        "unclear",
        "unclear",
    ]
    secondary = [
        "critical",
        "critical",
        "critical",
        "critical",
        "critical",
        "unclear",
        "critical",
        "unclear",
        "unclear",
        "unclear",
    ]

    assert cohens_kappa(primary, secondary) == pytest.approx(0.5833, abs=1e-4)


def test_agreement_without_kappa_can_be_meaningless() -> None:
    """Two labellers who always answer the same class agree perfectly and carry no information.

    pe = 1.0 here, which would divide by zero; the function returns 0.0 rather than pretending.
    """
    assert cohens_kappa(["unclear"] * 10, ["unclear"] * 10) == 0.0


def test_compare_counts_only_shared_items() -> None:
    """An item the validator never saw is not a disagreement."""
    result = compare({"a": "critical", "b": "unclear"}, {"a": "critical"})

    assert result.n == 1
    assert result.agree == 1
    assert result.rate == 1.0


def test_compare_reports_per_class_and_disagreements() -> None:
    """The class breakdown is what catches a model that is right overall and wrong on one class."""
    result = compare(
        {"a": "critical", "b": "critical", "c": "neutral", "d": "unclear"},
        {"a": "critical", "b": "unclear", "c": "neutral", "d": "unclear"},
    )

    assert result.n == 4
    assert result.agree == 3
    per_class = {label: (agree, total) for label, agree, total in result.per_class}
    assert per_class["critical"] == (1, 2)
    assert per_class["neutral"] == (1, 1)
    assert result.disagreements == (("b", "critical", "unclear"),)


def test_empty_comparison() -> None:
    """No shared items means no agreement claim."""
    result = compare({}, {})
    assert result.n == 0


class FakeGateway:
    """Gateway returning a fixed reply."""

    def __init__(self, reply: str, model: str = "validator-model") -> None:
        self.reply = reply
        self.model = model
        self.providers: list[str] = []

    def ask(self, prompt: str, *, prompt_version: str, provider: str) -> object:
        """Record the provider and return the reply."""
        self.providers.append(provider)
        return SimpleNamespace(text=self.reply, model=self.model, cost_usd=0.0001)


class FakeReader:
    """Segments with ids."""

    def __init__(self, rows: dict[str, str]) -> None:
        self.rows = rows

    def list_segments(self, method: str | None = None) -> tuple[tuple[str, str], ...]:
        """Return segments."""
        return tuple(self.rows.items())


class FakeStore:
    """Stores primary labels and validation rows."""

    def __init__(self, labels: dict[str, str]) -> None:
        self.labels = labels
        self.validation: list[tuple[str, str, float]] = []

    def stance_labels(self, target: str, *, prompt_version: str) -> dict[str, str]:
        """Return the seeded labels."""
        return self.labels

    def store_validation(self, rows, *, validator_model: str):
        """Record validation rows."""
        self.validation.extend(rows)
        return len(rows)


def test_validator_rejects_the_same_vendor() -> None:
    """D-010 enforced before any call: two models from one vendor are not independent evidence."""
    from gtaf.application.validation import validate_stance
    from gtaf.domain.actors import Actor

    gateway = FakeGateway('{"label": "critical", "confidence": 0.9, "quote": "x", "rationale": "y"}')
    store = FakeStore({})

    with pytest.raises(VendorConflictError):
        validate_stance(
            gateway,
            FakeReader({}),
            store,
            actor=Actor("s", "სააკაშვილი", "Saakashvili"),
            primary_provider="gemini",
            validator_provider="gemini",
        )

    assert gateway.providers == []


def test_validator_compares_and_stores() -> None:
    """A cross-vendor pass compares the shared items and stores its verdicts."""
    from gtaf.application.validation import validate_stance
    from gtaf.domain.actors import Actor

    gateway = FakeGateway('{"label": "unclear", "confidence": 0.8, "quote": "სააკაშვილი", "rationale": "y"}')
    store = FakeStore({"s1": "critical", "s2": "unclear"})
    reader = FakeReader({"s1": "სააკაშვილი კრიტიკულად", "s2": "სააკაშვილი"})

    result = validate_stance(
        gateway,
        reader,
        store,
        actor=Actor("s", "სააკაშვილი", "Saakashvili"),
        primary_provider="deepseek",
        validator_provider="gemini",
    )

    assert gateway.providers == ["gemini", "gemini"]
    assert result.compared == 2
    assert result.agreement.agree == 1
    assert len(store.validation) == 2


def test_unparsable_validator_replies_are_counted() -> None:
    """A validator that answers prose is a failed check, not an agreement."""
    from gtaf.application.validation import validate_stance
    from gtaf.domain.actors import Actor

    gateway = FakeGateway("ეს ტექსტი კრიტიკულია.")
    store = FakeStore({"s1": "critical"})

    result = validate_stance(
        gateway,
        FakeReader({"s1": "სააკაშვილი"}),
        store,
        actor=Actor("s", "სააკაშვილი", "Saakashvili"),
        primary_provider="deepseek",
        validator_provider="gemini",
    )

    assert result.unparsable == 1
    assert result.compared == 0
