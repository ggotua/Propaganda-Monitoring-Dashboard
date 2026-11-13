"""Guard: the committed env template must never contain a value.

The template is tracked by git; `.env` is not. A real key pasted into `.env.example` would be
committed and pushed on the next `git add -A`, which is exactly what nearly happened on 2026-11-13 —
the key was in the working copy of this tracked file and one commit away from leaking.

This test fails if any `NAME=value` line in the template has a non-empty value, so the mistake is
caught by the test suite rather than by a leak.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / ".env.example"

_ASSIGNMENT = re.compile(r"^(?P<name>[A-Z][A-Z0-9_]*)=(?P<value>.*)$")


def test_template_exists() -> None:
    """The template is part of the repo contract."""
    assert TEMPLATE.exists(), ".env.example is missing"


def test_no_assignment_has_a_value() -> None:
    """Every assignment in the template must be empty."""
    offenders: list[str] = []
    for number, line in enumerate(TEMPLATE.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT.match(stripped)
        if match and match.group("value").strip():
            offenders.append(f"line {number}: {match.group('name')} has a value")

    assert not offenders, (
        "Do not put secrets in .env.example (it is tracked by git): " + "; ".join(offenders)
    )


def test_template_has_no_key_shaped_strings() -> None:
    """A pasted key betrays itself by its prefix even without an assignment."""
    text = TEMPLATE.read_text(encoding="utf-8")
    for prefix in ("sk-", "AIza", "sk_live_", "ghp_"):
        assert prefix not in text, f"template contains something key-shaped: {prefix}…"
