"""Agreement between two labellers (SPEC-016).

Raw agreement is a bad measure when one class dominates: two labellers who both answer `unclear` 95 % of the
time agree 90 % by construction, learning nothing. Cohen's kappa subtracts the agreement expected from the
marginals, so a high rate that comes from laziness cannot pass.

Pure functions only; the vendors live in the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Agreement:
    """Agreement between a primary and a validator labeller.

    Attributes:
        n: Items both labellers labelled.
        agree: Items with the same label.
        rate: ``agree / n``.
        kappa: Cohen's kappa; 0 is chance, 1 is perfect, below 0 is worse than chance.
        per_class: ``(class, agree, total)`` for the primary labeller's classes.
        disagreements: ``(item, primary_label, validator_label)`` for review.
    """

    n: int
    agree: int
    rate: float
    kappa: float
    per_class: tuple[tuple[str, int, int], ...] = ()
    disagreements: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)


def cohens_kappa(primary: list[str], secondary: list[str]) -> float:
    """Return Cohen's kappa for two label sequences.

    Args:
        primary: Labels from the first labeller.
        secondary: Labels from the second, aligned.

    Returns:
        Kappa, or 0.0 when the expected agreement is 1 (nothing to correct).

    Notes:
        ``kappa = (po - pe) / (1 - pe)`` where ``po`` is observed agreement and ``pe`` the agreement expected
        from the two marginals. Worked example in the tests: 10 items, 8 agreeing, marginals giving
        ``pe = 0.54`` → ``kappa = 0.26 / 0.46 = 0.565``.
    """
    if not primary or len(primary) != len(secondary):
        return 0.0
    total = len(primary)
    observed = sum(1 for a, b in zip(primary, secondary, strict=False) if a == b) / total
    classes = set(primary) | set(secondary)
    expected = sum(
        (primary.count(label) / total) * (secondary.count(label) / total) for label in classes
    )
    if expected >= 1.0:
        return 0.0
    return (observed - expected) / (1.0 - expected)


def compare(
    primary: dict[str, str], secondary: dict[str, str]
) -> Agreement:
    """Compare two labellings over the items they share.

    Args:
        primary: Item id to primary label.
        secondary: Item id to validator label.

    Returns:
        The agreement, including per-class rates and the disagreements.

    Notes:
        Only shared items count. An item the validator never saw is not a disagreement — counting it as one
        would make coverage look like accuracy.
    """
    shared = sorted(set(primary) & set(secondary))
    if not shared:
        return Agreement(n=0, agree=0, rate=0.0, kappa=0.0)

    first = [primary[item] for item in shared]
    second = [secondary[item] for item in shared]
    agree = sum(1 for a, b in zip(first, second, strict=False) if a == b)

    classes: dict[str, list[int]] = {}
    for item in shared:
        bucket = classes.setdefault(primary[item], [0, 0])
        bucket[1] += 1
        if primary[item] == secondary[item]:
            bucket[0] += 1

    per_class = tuple((label, values[0], values[1]) for label, values in sorted(classes.items()))
    disagreements = tuple(
        (item, primary[item], secondary[item]) for item in shared if primary[item] != secondary[item]
    )
    return Agreement(
        n=len(shared),
        agree=agree,
        rate=agree / len(shared),
        kappa=cohens_kappa(first, second),
        per_class=per_class,
        disagreements=disagreements,
    )
