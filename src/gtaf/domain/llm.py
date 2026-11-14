"""LLM domain types and cost rules (SPEC-005).

Prices and model names are **data**, not constants buried in logic: they change, and a wrong price
is invisible because it still produces a plausible number. Every rule here is covered by a
hand-worked test.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

# When the price table below was last checked. Printed by `gtaf llm-check`, so a stale table is
# visible rather than silently wrong.
PRICES_CHECKED_ON = date(2026, 11, 14)

VENDOR_GEMINI = "google"
VENDOR_DEEPSEEK = "deepseek"


class LLMError(RuntimeError):
    """Base class for gateway failures."""


class BudgetExceededError(LLMError):
    """Raised before a call whose estimated cost would exceed the remaining monthly budget."""


class QuotaExceededError(LLMError):
    """Raised on HTTP 429 — the free tier's limit. Never retried: retrying deepens it (D-025)."""


class ProviderUnavailableError(LLMError):
    """Raised when every model in a provider's fallback chain failed."""


class ModelUnavailableError(LLMError):
    """Raised for a model that is retired, overloaded or timing out.

    Retrying this on the *next* model in the chain is correct: the provider is fine, this model is
    not. A quota error is different and must never advance the chain (SPEC-005 FR-5).
    """


class VendorConflictError(LLMError):
    """Raised when a validator shares a vendor with the primary (D-010)."""


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """A callable model and its price.

    Attributes:
        model: API model id, e.g. ``gemini-3-flash-preview``.
        vendor: Vendor key, e.g. ``google``; used to enforce D-010.
        input_usd_per_mtok: USD per million input tokens (0 for free-tier models).
        output_usd_per_mtok: USD per million output tokens.
        free_tier: True when the model is billed at zero under the free quota.
    """

    model: str
    vendor: str
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    free_tier: bool = False


# Ordered fallback chains, measured 2026-11-14 (D-025): `gemini-2.5-flash` and
# `gemini-2.5-flash-lite` were retired mid-probe with 404, `gemini-flash-latest` returned 503,
# `gemini-3.8-flash` timed out, and `gemini-3-flash-preview` answered. Keep several.
GEMINI_CHAIN: tuple[ModelSpec, ...] = (
    ModelSpec("gemini-3-flash-preview", VENDOR_GEMINI, 0.0, 0.0, free_tier=True),
    ModelSpec("gemini-3.5-flash", VENDOR_GEMINI, 0.0, 0.0, free_tier=True),
    ModelSpec("gemini-flash-latest", VENDOR_GEMINI, 0.0, 0.0, free_tier=True),
)

# DeepSeek's published per-million rates at the date above; paid, so used on samples, not on bulk.
DEEPSEEK_CHAIN: tuple[ModelSpec, ...] = (
    ModelSpec("deepseek-chat", VENDOR_DEEPSEEK, 0.27, 1.10),
)

PROVIDER_CHAINS: dict[str, tuple[ModelSpec, ...]] = {
    "gemini": GEMINI_CHAIN,
    "deepseek": DEEPSEEK_CHAIN,
}

PRIMARY_PROVIDER = "gemini"
VALIDATOR_PROVIDER = "deepseek"


@dataclass(frozen=True, slots=True)
class Usage:
    """Token counts for one call.

    Attributes:
        input_tokens: Prompt tokens as reported by the provider.
        output_tokens: Completion tokens, excluding reasoning where the provider separates them.
        total_tokens: All billed tokens, **including reasoning** — the number quota is charged
            against.
    """

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """A completed (or cached) model response.

    Attributes:
        text: The model's reply.
        provider: Provider key that answered.
        model: Model id that answered.
        usage: Token counts.
        cost_usd: Cost of this call; 0 when cached or free-tier.
        cached: True when served from `llm_calls` rather than the network.
        service_tier: Provider-reported tier, when it reports one.
    """

    text: str
    provider: str
    model: str
    usage: Usage
    cost_usd: float
    cached: bool = False
    service_tier: str | None = None


def estimate_tokens(text: str) -> int:
    """Estimate prompt tokens from character count.

    Args:
        text: Prompt text.

    Returns:
        Estimated tokens.

    Notes:
        Georgian is tokenised worse than English — roughly one token per 2 characters, not per 4.
        The estimator deliberately **over**-estimates (divides by 2) because it feeds a budget
        guard: being conservative refuses a call slightly too early, which is far cheaper than
        overshooting a cap.
        It is only used for the pre-call estimate; actual cost uses the provider's reported counts.
    """
    return max(1, len(text) // 2)


def estimate_cost(spec: ModelSpec, input_tokens: int, output_tokens: int) -> float:
    """Return the cost of a call in USD.

    Args:
        spec: Model and prices.
        input_tokens: Prompt tokens.
        output_tokens: Completion tokens.

    Returns:
        Cost in USD, computed per million tokens.

    Notes:
        Integer token counts times a per-million rate, so the arithmetic is checkable by hand — see
        ``test_cost_arithmetic_is_hand_verified``.
    """
    if spec.free_tier:
        return 0.0
    return (
        input_tokens * spec.input_usd_per_mtok / 1_000_000
        + output_tokens * spec.output_usd_per_mtok / 1_000_000
    )


def call_hash(*, provider: str, model: str, prompt_version: str, prompt: str) -> str:
    """Return the cache key for a call.

    Args:
        provider: Provider key.
        model: Model id.
        prompt_version: Version tag of the prompt template.
        prompt: Fully rendered prompt.

    Returns:
        Hex sha256 of the four fields joined with a separator.

    Notes:
        The version is part of the key, so editing a prompt never serves a stale cached answer
        (FR-6 boundary in SPEC-005 §6).
    """
    material = "\x1f".join((provider, model, prompt_version, prompt))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def require_different_vendors(primary: ModelSpec, validator: ModelSpec) -> None:
    """Enforce D-010: the validator must be a different vendor.

    Args:
        primary: Model that produced a finding.
        validator: Model that checks it.

    Raises:
        VendorConflictError: If both share a vendor. Two models from one vendor share blind spots,
            so their agreement is not independent evidence — and reporting it as agreement is worse
            than reporting nothing.
    """
    if primary.vendor == validator.vendor:
        raise VendorConflictError(
            f"validator {validator.model!r} is from {validator.vendor!r}, the same vendor as "
            f"primary "
            f"{primary.model!r}; a validator must be a different vendor (D-010)"
        )
