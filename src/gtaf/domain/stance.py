"""Stance toward a named person (SPEC-013).

Pure prompt construction and reply parsing. The heavy intellectual caution lives here: a model labelling
the *tone of a segment* is not measuring what a speaker believes, and the label set includes ``unclear``
precisely so the model has an honest option instead of being forced to choose sides.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

PROMPT_VERSION = "stance-v1"

LABELS: tuple[str, ...] = ("supportive", "critical", "neutral", "unclear")


@dataclass(frozen=True, slots=True)
class StanceLabel:
    """One model judgement.

    Attributes:
        label: One of :data:`LABELS`.
        confidence: Model-reported confidence in ``[0, 1]``.
        rationale: Short reason, stored so a reviewer can see why.
    """

    label: str
    confidence: float
    rationale: str


def build_prompt(text: str, *, target_en: str, target_ka: str) -> str:
    """Render the stance prompt for one segment.

    Args:
        text: Segment text (Georgian ASR output).
        target_en: Target person's English name.
        target_ka: Target person's Georgian name.

    Returns:
        A prompt asking for strict JSON.

    Notes:
        Three instructions do the work: judge the framing *of this text*, not the real world; do not guess
        when the text does not evaluate the person; and answer in JSON because anything else cannot be
        stored. The ``unclear`` option is offered before the substantive labels so the model is not nudged
        toward picking a side.
    """
    return (
        "შენ ხარ ქართული ტელევიზიის ტექსტების ანალიტიკოსი. განსაზღვრე, როგორ არის წარმოდგენილი "
        f"მოცემულ ტექსტში პიროვნება: {target_ka} ({target_en}).\n"
        "შესაძლო პასუხები: supportive (დადებითად), critical (კრიტიკულად), neutral (ნეიტრალურად), "
        "unclear (ტექსტი არ აფასებს ამ პიროვნებას ან გაურკვეველია).\n"
        "წესები: შეაფასე მხოლოდ ეს ტექსტი, არა რეალობა. თუ ტექსტი არ აფასებს პიროვნებას, აირჩიე "
        "unclear და ნუ გამოიცნობ. არ დაამატო განმარტება JSON-ის გარეთ.\n"
        'უპასუხე მხოლოდ JSON-ით: {"label": "...", "confidence": 0.0-1.0, "rationale": "..."}\n\n'
        f"ტექსტი:\n{text[:800]}"
    )


def parse_stance(text: str) -> StanceLabel | None:
    """Parse a model reply into a label.

    Args:
        text: Raw reply, possibly wrapped in a code fence.

    Returns:
        The label, or None when the reply is unusable.

    Notes:
        An unparsable reply is **not** coerced to ``neutral``. "The model said something we could not read"
        and "the model found neutrality" are different facts, and merging them would inflate the neutral
        share — the most comfortable answer and therefore the one a bug would hide behind.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    label = str(data.get("label") or "").strip().lower()
    if label not in LABELS:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(max(confidence, 0.0), 1.0)
    rationale = str(data.get("rationale") or "").strip()[:300]
    return StanceLabel(label=label, confidence=confidence, rationale=rationale)


def summarise(labels: list[str]) -> dict[str, int]:
    """Count labels, keeping ``unclear`` visible.

    Args:
        labels: Parsed labels.

    Returns:
        Counts per label, with zeros included.

    Notes:
        Every label appears in the result even at zero, so a reader cannot mistake "absent from the output"
        for "not measured".
    """
    counts = {label: 0 for label in LABELS}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return counts
