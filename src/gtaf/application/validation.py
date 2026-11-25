"""Cross-vendor validation use case (SPEC-016).

Takes labels produced by one vendor and asks a model from a *different* vendor to label the same segments
independently, then measures agreement. D-010 is enforced here, not in a document: the vendor check runs
before any call is made, because two models from one vendor share blind spots and their agreement is not
evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from gtaf.domain.actors import Actor
from gtaf.domain.llm import PROVIDER_CHAINS, require_different_vendors
from gtaf.domain.stance import PROMPT_VERSION, build_prompt, parse_stance
from gtaf.domain.validation import Agreement, compare


class Gateway(Protocol):
    """Subset of the LLM gateway this use case needs."""

    def ask(self, prompt: str, *, prompt_version: str, provider: str) -> object:
        """Return a response with ``text`` and ``model``."""
        ...


class ValidationStore(Protocol):
    """Persistence for primary labels and validation results."""

    def stance_labels(self, target: str, *, prompt_version: str) -> dict[str, str]:
        """Return segment id to primary label."""
        ...

    def store_validation(self, rows: Sequence[tuple[str, str, float]], *, validator_model: str) -> int:
        """Write ``(segment_id, validator_label, agreement)`` rows."""
        ...

    def validated_segments(self, validator_model: str) -> set[str]:
        """Return segment ids already validated by this model."""
        ...

    def validation_labels(self, validator_model: str) -> dict[str, str]:
        """Return the validator's label per segment."""
        ...


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of a validation pass.

    Attributes:
        target: Actor validated.
        primary_provider: Vendor that produced the labels.
        validator_provider: Vendor that checked them.
        compared: Items both labellers covered.
        agreement: The measured agreement.
        unparsable: Replies the validator produced that could not be read.
        cost_usd: Spend for this pass.
    """

    target: str
    primary_provider: str
    validator_provider: str
    compared: int
    agreement: Agreement
    unparsable: int
    cost_usd: float


def cumulative_agreement(
    store: ValidationStore, *, target: str, validator_model: str
) -> Agreement:
    """Recompute agreement over everything validated so far.

    Args:
        store: Persistence holding the validator's labels.
        target: Actor whose primary labels are compared.
        validator_model: Model that produced the stored verdicts.

    Returns:
        Agreement over all stored pairs.

    Notes:
        The free tier allows about eleven calls a day, so a 50-item check is assembled from several runs.
        Recomputing from storage — rather than from the last batch — is what makes that accumulation
        honest: a good first day and a bad second are averaged, not cherry-picked.
    """
    primary = store.stance_labels(target, prompt_version=PROMPT_VERSION)
    validated = store.validation_labels(validator_model)
    return compare(primary, validated)


def validate_stance(
    gateway: Gateway,
    reader: object,
    store: ValidationStore,
    *,
    actor: Actor,
    primary_provider: str,
    validator_provider: str,
    limit: int = 50,
    method: str = "drift",
) -> ValidationResult:
    """Validate stored stance labels with a different vendor.

    Args:
        gateway: LLM gateway.
        reader: Segment source, used to rebuild the prompt text.
        store: Primary labels and validation persistence.
        actor: Target person.
        primary_provider: Provider whose labels are being checked.
        validator_provider: Provider that checks them; must be a different vendor.
        limit: Maximum items to validate.
        method: Segmentation the labels were produced on.

    Returns:
        The agreement, including per-class rates and disagreements.

    Raises:
        VendorConflictError: If both providers belong to the same vendor (D-010).
    """
    primary_spec = PROVIDER_CHAINS[primary_provider][0]
    validator_spec = PROVIDER_CHAINS[validator_provider][0]
    require_different_vendors(primary_spec, validator_spec)

    primary = store.stance_labels(actor.actor_id, prompt_version=PROMPT_VERSION)
    segments = dict(
        (segment_id, text) for segment_id, text in reader.list_segments(method)  # type: ignore[attr-defined]
    )
    already = store.validated_segments(validator_spec.model)

    validator_labels: dict[str, str] = {}
    unparsable = 0
    cost = 0.0
    # Skip what earlier runs already checked, so a daily batch accumulates instead of repeating the same
    # items. The Gemini free tier allows about eleven calls a day, so a 50-item check needs several runs.
    candidates = [item for item in sorted(primary) if item not in already]
    for segment_id in candidates[:limit]:
        text = segments.get(segment_id)
        if text is None:
            continue
        response = gateway.ask(
            build_prompt(text, target_en=actor.en, target_ka=actor.ka),
            prompt_version=PROMPT_VERSION,
            provider=validator_provider,
        )
        cost += float(getattr(response, "cost_usd", 0.0))
        parsed = parse_stance(str(getattr(response, "text", "")), segment_text=text)
        if parsed is None:
            unparsable += 1
            continue
        validator_labels[segment_id] = parsed.label

    agreement = compare(primary, validator_labels)
    if validator_labels:
        store.store_validation(
            [
                (item, label, 1.0 if primary[item] == label else 0.0)
                for item, label in validator_labels.items()
            ],
            validator_model=validator_spec.model,
        )

    return ValidationResult(
        target=actor.actor_id,
        primary_provider=primary_provider,
        validator_provider=validator_provider,
        compared=agreement.n,
        agreement=agreement,
        unparsable=unparsable,
        cost_usd=round(cost, 6),
    )
