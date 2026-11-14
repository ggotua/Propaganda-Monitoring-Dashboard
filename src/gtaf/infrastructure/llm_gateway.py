"""LLM gateway: cache, cost metering, budget guard, model fallback (SPEC-005).

The gateway is the only place a prompt leaves the machine. Four properties are enforced here rather
than left to discipline: a call is never paid for twice, every call is costed, a call that would
exceed the budget is refused before it is sent, and a retired or overloaded model advances to the
next in the chain while a quota error stops the provider.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from gtaf.domain.llm import (
    BudgetExceededError,
    LLMResponse,
    ModelSpec,
    ModelUnavailableError,
    ProviderUnavailableError,
    QuotaExceededError,
    Usage,
    call_hash,
    estimate_cost,
    estimate_tokens,
)
from gtaf.infrastructure.llm_providers import Completion, Transport

# Worst-case output used for the pre-call estimate, matching `maxOutputTokens` in the transports.
MAX_OUTPUT_TOKENS = 512


class CallStore(Protocol):
    """Persistence for the call cache and the spend meter."""

    def get_cached_call(self, key: str) -> str | None:
        """Return the stored payload for a call hash, or None."""
        ...

    def store_call(
        self,
        key: str,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        payload_json: str,
    ) -> None:
        """Persist one call."""
        ...

    def spent_between(self, start: datetime) -> float:
        """Return the total cost recorded since ``start``."""
        ...


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    """Configuration for one gateway instance.

    Attributes:
        monthly_budget_usd: Hard cap; a call that would exceed it is refused.
        env_label: Where the budget came from, for the report line.
    """

    monthly_budget_usd: float
    env_label: str = "GTAF_MONTHLY_BUDGET_USD"


def month_start(moment: datetime | None = None) -> datetime:
    """Return the first instant of the current UTC month.

    Args:
        moment: Override for the current instant.

    Returns:
        Naive UTC datetime at the start of the month, matching the storage convention.
    """
    now = moment or datetime.now(UTC).replace(tzinfo=None)
    return datetime(now.year, now.month, 1)


class Gateway:
    """Single entry point for every LLM call."""

    def __init__(
        self,
        transports: Mapping[str, Transport],
        store: CallStore,
        *,
        config: GatewayConfig,
        chains: Mapping[str, Sequence[ModelSpec]],
    ) -> None:
        """Initialise the gateway.

        Args:
            transports: Provider key to transport.
            store: Cache and spend meter.
            config: Budget configuration.
            chains: Provider key to ordered model fallback chain.
        """
        self._transports = transports
        self._store = store
        self._config = config
        self._chains = chains

    def ask(
        self, prompt: str, *, prompt_version: str, provider: str
    ) -> LLMResponse:
        """Answer a prompt, using the cache and the provider's fallback chain.

        Args:
            prompt: Fully rendered prompt.
            prompt_version: Version tag; part of the cache key.
            provider: Provider key to call.

        Returns:
            The response, with ``cached`` set when served from storage.

        Raises:
            QuotaExceededError: The provider is rate limited. Not retried, not rerouted (FR-5).
            BudgetExceededError: The estimated cost would exceed the monthly cap (FR-3).
            ProviderUnavailableError: Every model in the chain failed.
        """
        chain = self._chains.get(provider)
        transport = self._transports.get(provider)
        if not chain or transport is None:
            raise ProviderUnavailableError(f"no transport or chain configured for {provider!r}")

        for spec in chain:
            key = call_hash(
                provider=provider, model=spec.model, prompt_version=prompt_version, prompt=prompt
            )
            cached = self._store.get_cached_call(key)
            if cached is not None:
                return self._from_cache(cached, spec, provider)

            self._guard_budget(spec, prompt)

            try:
                completion = transport.complete(spec, prompt)
            except ModelUnavailableError:
                # This model is retired, overloaded or timed out — the provider is fine, move on.
                continue
            except QuotaExceededError:
                # Rotating models to dodge a quota is the same mistake as rotating IPs (D-025).
                raise

            cost = estimate_cost(
                spec, completion.usage.input_tokens, completion.usage.output_tokens
            )
            payload = {
                "text": completion.text,
                "input_tokens": completion.usage.input_tokens,
                "output_tokens": completion.usage.output_tokens,
                "total_tokens": completion.usage.total_tokens,
                "service_tier": completion.service_tier,
            }
            self._store.store_call(
                key,
                provider=provider,
                model=spec.model,
                prompt_version=prompt_version,
                input_tokens=completion.usage.input_tokens,
                output_tokens=completion.usage.output_tokens,
                cost_usd=cost,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
            return LLMResponse(
                text=completion.text,
                provider=provider,
                model=spec.model,
                usage=completion.usage,
                cost_usd=cost,
                cached=False,
                service_tier=completion.service_tier,
            )

        raise ProviderUnavailableError(
            f"every model in the {provider!r} chain failed: {[s.model for s in chain]}"
        )

    def _guard_budget(self, spec: ModelSpec, prompt: str) -> None:
        """Refuse a call whose worst-case cost would exceed the remaining budget.

        Args:
            spec: Model about to be called.
            prompt: Prompt text, for the token estimate.

        Raises:
            BudgetExceededError: If the estimate would overshoot. Nothing is sent and no row is
                written.
        """
        spent = self._store.spent_between(month_start())
        worst_case = estimate_cost(
            spec, estimate_tokens(prompt), MAX_OUTPUT_TOKENS
        )
        if spent + worst_case > self._config.monthly_budget_usd:
            raise BudgetExceededError(
                f"refusing call: spent {spent:.4f} + estimated {worst_case:.4f} USD would exceed "
                f"the {self._config.monthly_budget_usd:.2f} USD monthly cap "
                f"({self._config.env_label})"
            )

    def _from_cache(self, payload: str, spec: ModelSpec, provider: str) -> LLMResponse:
        """Rebuild a response from a stored payload.

        Args:
            payload: JSON stored in `llm_calls.response_json`.
            spec: Model that produced it.
            provider: Provider key.

        Returns:
            The cached response with cost 0 and ``cached=True``.
        """
        data = json.loads(payload)
        usage = Usage(
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            total_tokens=int(data.get("total_tokens", 0)),
        )
        return LLMResponse(
            text=str(data.get("text", "")),
            provider=provider,
            model=spec.model,
            usage=usage,
            cost_usd=0.0,
            cached=True,
            service_tier=data.get("service_tier"),
        )


__all__ = ["MAX_OUTPUT_TOKENS", "CallStore", "Gateway", "GatewayConfig", "month_start"]


def fake_completion(text: str, input_tokens: int = 10, output_tokens: int = 5) -> Completion:
    """Build a Completion for tests.

    Args:
        text: Reply text.
        input_tokens: Prompt tokens.
        output_tokens: Completion tokens.

    Returns:
        A Completion with total tokens as the sum.
    """
    return Completion(
        text=text,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens),
    )
