"""Gateway tests (SPEC-005 §4).

The transport is faked, so these verify the rules that protect money and evidence: a cached call
costs nothing, a call that would exceed the budget is never sent, a retired model advances the
chain, a quota error stops it, and a validator may not share the primary's vendor.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pytest

from gtaf.domain.llm import (
    BudgetExceededError,
    ModelSpec,
    ModelUnavailableError,
    ProviderUnavailableError,
    QuotaExceededError,
    Usage,
    VendorConflictError,
    call_hash,
    estimate_cost,
    estimate_tokens,
    require_different_vendors,
)
from gtaf.infrastructure.llm_gateway import Gateway, GatewayConfig
from gtaf.infrastructure.llm_providers import Completion

CHAIN = (
    ModelSpec("model-a", "google", 0.0, 0.0, free_tier=True),
    ModelSpec("model-b", "google", 0.0, 0.0, free_tier=True),
)


class FakeTransport:
    """Transport with scripted per-model behaviour."""

    def __init__(self, behaviour: dict[str, object]) -> None:
        self.behaviour = behaviour
        self.calls: list[str] = []

    def complete(self, spec: ModelSpec, prompt: str) -> Completion:
        """Return the scripted result or raise the scripted error."""
        self.calls.append(spec.model)
        result = self.behaviour[spec.model]
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, Completion)
        return result


class FakeStore:
    """In-memory cache and spend meter."""

    def __init__(self, spent: float = 0.0) -> None:
        self.cache: dict[str, str] = {}
        self.rows: list[dict[str, object]] = []
        self._spent = spent

    def get_cached_call(self, key: str) -> str | None:
        """Return a cached payload."""
        return self.cache.get(key)

    def store_call(self, key: str, **kwargs: object) -> None:
        """Record a call and its payload."""
        self.cache[key] = str(kwargs["payload_json"])
        self.rows.append({"key": key, **kwargs})

    def spent_between(self, start: datetime) -> float:
        """Return the preset spend."""
        return self._spent


def _completion(text: str = "OK") -> Completion:
    """Build a completion with small token counts."""
    return Completion(text=text, usage=Usage(3, 2, 5))


def _gateway(
    transport: FakeTransport, store: FakeStore, *, budget: float = 20.0
) -> Gateway:
    """Build a gateway over one provider."""
    return Gateway(
        {"gemini": transport},
        store,
        config=GatewayConfig(monthly_budget_usd=budget),
        chains={"gemini": CHAIN},
    )


def test_cost_arithmetic_is_hand_verified() -> None:
    """FR-9: 1000 input at $0.27/M plus 500 output at $1.10/M is $0.00082, by hand.

    1000 x 0.27 / 1_000_000 = 0.00027
     500 x 1.10 / 1_000_000 = 0.00055
                    total   = 0.00082
    """
    paid = ModelSpec("deepseek-chat", "deepseek", 0.27, 1.10)
    assert estimate_cost(paid, 1000, 500) == pytest.approx(0.00082, abs=1e-9)


def test_free_tier_models_cost_nothing() -> None:
    """A free-tier model records 0 even with large token counts."""
    free = ModelSpec("gemini-3-flash-preview", "google", 0.0, 0.0, free_tier=True)
    assert estimate_cost(free, 1_000_000, 1_000_000) == 0.0


def test_token_estimate_over_estimates_georgian() -> None:
    """The estimator divides by 2, not 4: Georgian tokenises worse, and over-estimating is safe."""
    text = "ა" * 100
    assert estimate_tokens(text) == 50


def test_cache_hit_costs_nothing_and_skips_the_network() -> None:
    """FR-1: the second identical call is served from storage with cost 0."""
    transport = FakeTransport({"model-a": _completion()})
    store = FakeStore()
    gateway = _gateway(transport, store)

    first = gateway.ask("prompt", prompt_version="v1", provider="gemini")
    second = gateway.ask("prompt", prompt_version="v1", provider="gemini")

    assert first.cached is False
    assert second.cached is True
    assert second.cost_usd == 0.0
    assert transport.calls == ["model-a"]
    assert len(store.rows) == 1


def test_different_prompt_version_is_a_different_cache_entry() -> None:
    """Changing a prompt template must never serve the old answer."""
    transport = FakeTransport({"model-a": _completion()})
    store = FakeStore()
    gateway = _gateway(transport, store)

    gateway.ask("prompt", prompt_version="v1", provider="gemini")
    gateway.ask("prompt", prompt_version="v2", provider="gemini")

    assert transport.calls == ["model-a", "model-a"]
    assert len(store.rows) == 2


def test_budget_refusal_sends_nothing() -> None:
    """FR-3: the guard runs before the request, so nothing is sent and no row is written.

    Uses a paid model on purpose: a free-tier model estimates to zero, so it could never trip the
    cap — which is exactly how the first version of this test passed for the wrong reason.
    """
    paid_chain = (ModelSpec("deepseek-chat", "deepseek", 0.27, 1.10),)
    transport = FakeTransport({"deepseek-chat": _completion()})
    store = FakeStore(spent=19.999)
    gateway = Gateway(
        {"deepseek": transport},
        store,
        config=GatewayConfig(monthly_budget_usd=20.0),
        chains={"deepseek": paid_chain},
    )

    with pytest.raises(BudgetExceededError):
        gateway.ask("x" * 4000, prompt_version="v1", provider="deepseek")

    assert transport.calls == []
    assert store.rows == []


def test_free_model_can_never_exceed_the_budget() -> None:
    """A free-tier model estimates to zero, so the guard permits it even at the cap boundary."""
    transport = FakeTransport({"model-a": _completion()})
    store = FakeStore(spent=19.999)
    gateway = _gateway(transport, store, budget=20.0)

    response = gateway.ask("x" * 4000, prompt_version="v1", provider="gemini")

    assert response.cost_usd == 0.0
    assert transport.calls == ["model-a"]


def test_retired_model_falls_back_to_the_next() -> None:
    """FR-4: a 404 advances the chain and the answer records which model served it."""
    transport = FakeTransport(
        {"model-a": ModelUnavailableError("HTTP 404: retired"), "model-b": _completion("from B")}
    )
    store = FakeStore()

    response = _gateway(transport, store).ask("prompt", prompt_version="v1", provider="gemini")

    assert response.text == "from B"
    assert response.model == "model-b"
    assert transport.calls == ["model-a", "model-b"]


def test_quota_error_stops_the_chain() -> None:
    """FR-5: a 429 is not dodged by rotating models — that is how a quota becomes a block."""
    transport = FakeTransport(
        {"model-a": QuotaExceededError("HTTP 429"), "model-b": _completion()}
    )
    store = FakeStore()

    with pytest.raises(QuotaExceededError):
        _gateway(transport, store).ask("prompt", prompt_version="v1", provider="gemini")

    assert transport.calls == ["model-a"]


def test_all_models_failing_raises_provider_unavailable() -> None:
    """A provider whose whole chain is retired reports that plainly."""
    transport = FakeTransport(
        {"model-a": ModelUnavailableError("404"), "model-b": ModelUnavailableError("503")}
    )
    with pytest.raises(ProviderUnavailableError):
        _gateway(transport, FakeStore()).ask("prompt", prompt_version="v1", provider="gemini")


def test_same_vendor_validator_is_refused() -> None:
    """D-010: a validator from the primary's vendor is not independent evidence."""
    primary = ModelSpec("gemini-3-flash-preview", "google", 0.0, 0.0, free_tier=True)
    sibling = ModelSpec("gemini-3.5-flash", "google", 0.0, 0.0, free_tier=True)

    with pytest.raises(VendorConflictError):
        require_different_vendors(primary, sibling)


def test_cross_vendor_validator_is_accepted() -> None:
    """Gemini primary with a DeepSeek validator satisfies the rule."""
    primary = ModelSpec("gemini-3-flash-preview", "google", 0.0, 0.0, free_tier=True)
    validator = ModelSpec("deepseek-chat", "deepseek", 0.27, 1.10)
    require_different_vendors(primary, validator)


def test_call_hash_is_stable_and_version_sensitive() -> None:
    """The cache key covers provider, model, version and prompt."""
    first = call_hash(provider="gemini", model="a", prompt_version="v1", prompt="p")
    same = call_hash(provider="gemini", model="a", prompt_version="v1", prompt="p")
    other_version = call_hash(provider="gemini", model="a", prompt_version="v2", prompt="p")
    other_provider = call_hash(provider="deepseek", model="a", prompt_version="v1", prompt="p")

    assert first == same
    assert first != other_version
    assert first != other_provider


def test_unknown_provider_is_reported() -> None:
    """A misconfigured provider name fails loudly, not silently."""
    with pytest.raises(ProviderUnavailableError):
        _gateway(FakeTransport({"model-a": _completion()}), FakeStore()).ask(
            "prompt", prompt_version="v1", provider="nope"
        )


def test_no_key_appears_in_a_quota_error() -> None:
    """FR-8: exceptions carry the provider body, never request headers."""
    transport = FakeTransport({"model-a": QuotaExceededError("HTTP 429 quota exhausted: {}",)})
    try:
        _gateway(transport, FakeStore()).ask("prompt", prompt_version="v1", provider="gemini")
    except QuotaExceededError as exc:
        message = str(exc)
    assert "key" not in message.lower()
    assert "authorization" not in message.lower()


def test_chain_must_be_ordered_and_non_empty() -> None:
    """A provider with an empty chain is a configuration error."""
    gateway = Gateway(
        {"gemini": FakeTransport({})},
        FakeStore(),
        config=GatewayConfig(monthly_budget_usd=1.0),
        chains={"gemini": ()},
    )
    with pytest.raises(ProviderUnavailableError):
        gateway.ask("prompt", prompt_version="v1", provider="gemini")


def _unused(_: Sequence[object]) -> None:  # pragma: no cover - keeps imports honest
    """Placeholder to satisfy the linter for the Sequence import."""
