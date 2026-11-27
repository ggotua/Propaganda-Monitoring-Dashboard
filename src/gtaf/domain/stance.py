"""Stance toward a named person (SPEC-013).

Pure prompt construction and reply parsing. Two measured failures shaped this file:

1. **The model reads hostile context as a verdict on the target.** In the first G-8 review, nine of twelve
   rejected `critical` labels described hostility toward an associate — his uncle, his party, a minister of
   his era — with the target named only for identification.
2. **Rationales were invented.** Three reviews quoted words absent from the segment.

So version 2 requires the evaluation to be about this person, defines `neutral` and `unclear` by what the
text does, and demands a verbatim quote that is then checked against the segment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

PROMPT_VERSION = "stance-v5"

LABELS: tuple[str, ...] = ("supportive", "critical", "neutral", "unclear")

# How much segment text goes into the prompt. Raised from 800 after the first review: truncation removed the
# sentence that decided the label, so the same passage received different labels in different segments.
PROMPT_CHARS = 2000


@dataclass(frozen=True, slots=True)
class StanceLabel:
    """One model judgement.

    Attributes:
        label: One of :data:`LABELS`.
        confidence: Model-reported confidence in ``[0, 1]``.
        rationale: Short reason, stored so a reviewer can see why.
        quote: Verbatim words from the text that justify the label.
        quote_verified: True when ``quote`` actually occurs in the segment.
    """

    label: str
    confidence: float
    rationale: str
    quote: str = ""
    quote_verified: bool = False


def _normalise(text: str) -> str:
    """Lowercase and collapse whitespace, so a quote can be compared to the text.

    Args:
        text: Text to normalise.

    Returns:
        Normalised text.
    """
    return " ".join(text.lower().split())


def verify_quote(quote: str, text: str) -> bool:
    """Return True when the quote occurs in the segment.

    Args:
        quote: Words the model claims to quote.
        text: Segment text.

    Returns:
        True when the normalised quote is a substring of the normalised text.

    Notes:
        A review cannot check a reason the source does not contain, so a label without a verifiable quote is
        kept but marked, never silently trusted.
    """
    needle = _normalise(quote)
    if len(needle) < 8:
        return False
    return needle in _normalise(text)


def build_prompt(text: str, *, target_en: str, target_ka: str) -> str:
    """Render the stance prompt for one segment.

    Args:
        text: Segment text (Georgian ASR output).
        target_en: Target person's English name.
        target_ka: Target person's Georgian name.

    Returns:
        A prompt asking for strict JSON.
    """
    return (
        "შენ ხარ ქართული ტელევიზიის ტექსტების ანალიტიკოსი. დაადგინე, აფასებს თუ არა ტექსტი "
        f"კონკრეტულად პიროვნებას: {target_ka} ({target_en}).\n"
        "\n"
        "მთავარი წესი (დადებითი ფორმულირება): თუ ტექსტი ასახელებს "
        f"{target_ka}-ს ({target_en}) და მას მიაწერს ქმედებას, მოტივს ან თვისებას — შეაფასე "
        "სწორედ ამ მიკუთვნების დამოკიდებულება. სტატია არ უნდა იყოს ძირითადად მასზე: "
        "საკმარისია, რომ ის სახელით იყოს ნახსენები და მას რამე მიეწეროს.\n"
        "\n"
        "მხოლოდ ეს არის გამონაკლისი: თუ ტექსტი არ ახსენებს სამიზნეს სახელით და არც მკაფიოდ "
        "გულისხმობს მას (მაგ., „რეჟიმი“, „ხელისუფლება“ სხვა პირის კონტექსტში), ეს არის unclear. "
        "სამიზნის ნათესავზე, პარტიაზე ან მინისტრზე თავდასხმა, რომელიც სამიზნეს არ ახსენებს, "
        "ასევე unclear.\n"
        "\n"
        "რამდენიმე პირი ერთ ტექსტში: ტექსტი შეიძლება ერთდროულად აფასებდეს რამდენიმე "
        "სახელდებულ პირს. შეაფასე მხოლოდ სამიზნის მიკუთვნება და არა ტექსტის ზოგადი ტონი. "
        "მაგალითი: „ივანიშვილმა ბესელია ციხეში ჩასვა“ — ეს არის critical ივანიშვილის მიმართ, "
        "მაგრამ neutral ბესელიას მიმართ, რადგან ის დაზარალებულია და არა შემფასებელი. "
        "თუ სამიზნე ტექსტში მხოლოდ დაზარალებულის ან ბიზნეს პირის როლშია — neutral.\n"
        "\n"
        "მაგალითები (რეალური ტექსტებიდან):\n"
        "1. „მოვითხოვ პირად სანქციებს ივანიშვილის ოჯახისა და მისი პოლიტიკური წრის წინააღმდეგ“ "
        "— critical: მას სახელით მიეწერება ქმედება და მოთხოვნა.\n"
        "2. „ივანიშვილმა შეიძლება, ღარიბაშვილს მდინარაძე შეაჭმევინოს“ — critical: "
        "მეტაფორა მას მიაწერს მოტივს; სტატია მხოლოდ მასზე არ არის, ეს არ ცვლის მეტს.\n"
        "3. „ევროპარლამენტი თვითონ არის სანქცირებული“ — supportive: ტექსტი იცავს "
        "სამიზნეს სანქციების მოთხოვნისგან.\n"
        "4. „წითელი ხალიჩები გაშლილი გვაქვს, მაგრამ რა ფასად?“ — supportive: სამიზნის "
        "პოზიციის დაცვა დასავლური მოთხოვნების წინააღმდეგ.\n"
        "5. „კობახიძე ადასტურებს, რომ მოლაპარაკებები შესაძლოა მოსკოვში შედგეს“ — neutral: "
        "ფაქტის გადმოცემა მისივე სიტყვებით, გარეშე შეფასებისა.\n"
        "\n"
        "საკუთარი განცხადება: თუ ტექსტი გადმოსცემს სამიზნის საკუთარ სიტყვებს საკუთარი "
        "მიღწევების, გეგმების ან ქმედებების შესახებ (ციტატა ან პარაფრაზი), ეს არის neutral — "
        "ეს არის გამოცემის მიერ გადმოცემული საკუთარი შეფასება, არა გამოცემის დამოკიდებულება. "
        "თუ გამოცემა თავად ამატებს შეფასებას (სათაურში, კომენტარში, ტონში), მაშინ შეაფასე "
        "ის დამატებითი შეფასება. სათაური ტექსტის ნაწილია: თუ სათაური ამბობს, რომ სამიზნემ "
        "„იხუმრა“ ან „მოიტყუა“, ეს დამოკიდებულებაა და უნდა შეფასდეს.\n"
        "\n"
        "ლაბელების განმარტება:\n"
        "- supportive: ტექსტი ამ პიროვნებას აფასებს დადებითად (აქებს, იცავს, ამართლებს).\n"
        "- critical: ტექსტი ამ პიროვნებას აფასებს უარყოფითად (აკრიტიკებს, ადანაშაულებს).\n"
        "- neutral: ტექსტი ახსენებს და არც აქებს, არც აკრიტიკებს — ფაქტის დადგენა ან ნეიტრალური "
        "აღწერა.\n"
        "- unclear: ტექსტი საერთოდ არ აფასებს ამ პიროვნებას (მხოლოდ ახსენებს სხვის კონტექსტში), "
        "ან ტექსტი გაუგებარია. ეჭვის შემთხვევაში აირჩიე unclear.\n"
        "\n"
        "ვალდებულება: მიუთითე quote — სიტყვები, რომლებიც ზუსტად ამ ტექსტშია და რომლებიც "
        "ასაბუთებს შენს არჩევანს (მაქსიმუმ 20 სიტყვა, ზუსტი ასლი). არ შეცვალო სიტყვები, არ "
        "გამოიგონო ციტატა. თუ ციტატა ვერ იპოვე, აირჩიე unclear და quote დატოვე ცარიელი.\n"
        "\n"
        'უპასუხე მხოლოდ JSON-ით: {"label": "...", "confidence": 0.0-1.0, "quote": "...", '
        '"rationale": "..."}\n\n'
        f"ტექსტი:\n{text[:PROMPT_CHARS]}"
    )


def parse_stance(text: str, *, segment_text: str = "") -> StanceLabel | None:
    """Parse a model reply into a label.

    Args:
        text: Raw reply, possibly wrapped in a code fence.
        segment_text: The segment the reply is about, used to verify the quote.

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
    quote = str(data.get("quote") or "").strip()[:300]
    return StanceLabel(
        label=label,
        confidence=confidence,
        rationale=rationale,
        quote=quote,
        quote_verified=verify_quote(quote, segment_text) if segment_text else False,
    )


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
