"""Interpreter gate (D-007, D-011): can the CPU embedding chain run on this interpreter?

Purpose
-------
Decide, before SPEC-006/SPEC-007 commit to an engine, whether the analysis stack works on the
interpreter this project actually has (3.13.1) or whether it must fall back to 3.12.

This script installs nothing and therefore **cannot conclude a compatibility failure from an
absence**. Three outcomes are distinguished deliberately:

- ``ok``       — imports cleanly.
- ``missing``  — not installed. Says nothing about compatibility; the install must be attempted.
- ``broken``   — installed but fails to import (typically ABI/LLVM mismatch). This *is* a
                 compatibility failure and is what the D-007 fallback exists for.

Usage
-----
    .venv\\Scripts\\python.exe spikes/bertopic_chain_check.py
    .venv\\Scripts\\python.exe spikes/bertopic_chain_check.py --json

Exit codes
----------
0   every module imports — stay on this interpreter (D-007)
1   at least one module is installed but broken — fall back to 3.12 (D-007)
2   interpreter below the accepted minimum — fall back
3   inconclusive: modules are merely absent, so nothing is proven either way.
    Install the chain (see docs/STATUS.md) and re-run before deciding.
"""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
from dataclasses import dataclass

# Ordered by dependency depth: a failure here usually explains the ones after it.
REQUIRED_CHAIN: tuple[tuple[str, str], ...] = (
    ("numpy", "numerical base"),
    ("numba", "JIT compiler UMAP and HDBSCAN rely on"),
    ("llvmlite", "numba's LLVM binding - the usual blocker on a new interpreter"),
    ("umap_learn", "UMAP, imported as umap"),
    ("hdbscan", "density clustering"),
    ("sklearn", "scikit-learn, HDBSCAN's modern home"),
    ("sentence_transformers", "embedding models"),
    ("bertopic", "topic modelling"),
)

MINIMUM_PYTHON = (3, 12)

MISSING, BROKEN, OK = "missing", "broken", "ok"


@dataclass(frozen=True)
class Check:
    """One import check result."""

    module: str
    role: str
    kind: str
    detail: str

    @property
    def ok(self) -> bool:
        """True when the module imported cleanly."""
        return self.kind == OK

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable mapping of this result."""
        return {"module": self.module, "role": self.role, "kind": self.kind, "detail": self.detail}


def check_module(module: str, role: str) -> Check:
    """Attempt to import one module and classify the outcome.

    Args:
        module: Import name, not distribution name (``umap_learn`` imports as ``umap``).
        role: One-line explanation of why the chain needs it.

    Returns:
        A ``Check`` whose ``kind`` is ``ok``, ``missing`` (ModuleNotFoundError — simply not
        installed) or ``broken`` (any other import failure). ``detail`` carries the version when
        available, otherwise the exception, truncated to keep output readable.
    """
    try:
        imported = importlib.import_module(module)
    except ModuleNotFoundError:
        return Check(module, role, MISSING, "not installed")
    except Exception as exc:  # noqa: BLE001 - any non-absence failure is a compatibility signal
        return Check(module, role, BROKEN, f"{type(exc).__name__}: {exc}"[:300])
    version = getattr(imported, "__version__", "version unknown")
    return Check(module, role, OK, str(version))


def summarise(python_too_old: bool, checks: list[Check]) -> tuple[str, int]:
    """Decide the verdict from the individual results.

    Args:
        python_too_old: Whether the running interpreter is below ``MINIMUM_PYTHON``.
        checks: All import results.

    Returns:
        A ``(verdict, exit_code)`` pair where verdict is one of ``interpreter_too_old``,
        ``fallback_required``, ``inconclusive`` or ``chain_ok``.
    """
    if python_too_old:
        return "interpreter_too_old", 2
    if any(check.kind == BROKEN for check in checks):
        return "fallback_required", 1
    if any(check.kind == MISSING for check in checks):
        return "inconclusive", 3
    return "chain_ok", 0


def run() -> int:
    """Run the chain check, print it, and return the process exit code."""
    parser = argparse.ArgumentParser(
        description="Check the CPU embedding chain on this interpreter"
    )
    parser.add_argument("--json", action="store_true", help="emit a single JSON object")
    args = parser.parse_args()

    python_too_old = sys.version_info[:2] < MINIMUM_PYTHON
    checks = [check_module(module, role) for module, role in REQUIRED_CHAIN]
    verdict, exit_code = summarise(python_too_old, checks)

    if args.json:
        print(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "executable": sys.executable,
                    "minimum_python": ".".join(str(part) for part in MINIMUM_PYTHON),
                    "python_ok": not python_too_old,
                    "checks": [check.as_dict() for check in checks],
                    "verdict": verdict,
                },
                indent=2,
            )
        )
        return exit_code

    n_missing = sum(1 for check in checks if check.kind == MISSING)
    n_broken = sum(1 for check in checks if check.kind == BROKEN)

    print(f"interpreter : {platform.python_version()}  ({sys.executable})")
    print(f"minimum     : {'.'.join(str(part) for part in MINIMUM_PYTHON)}")
    print()
    for check in checks:
        label = {OK: "OK  ", MISSING: "NONE", BROKEN: "FAIL"}[check.kind]
        print(f"  [{label}] {check.module:<22} {check.detail}")
        if not check.ok:
            print(f"           needed for: {check.role}")
    print()

    if verdict == "interpreter_too_old":
        print("VERDICT: interpreter below minimum - fall back to 3.12 per D-007.")
    elif verdict == "fallback_required":
        print(f"VERDICT: {n_broken} module(s) installed but failing to import.")
        print("         That is a compatibility failure: fall back to 3.12 per D-007.")
    elif verdict == "inconclusive":
        print(
            f"VERDICT: INCONCLUSIVE - {n_missing} of {len(checks)} modules are "
            f"simply not installed."
        )
        print("         Absence proves nothing about compatibility. Install the chain, re-run,")
        print("         and only then apply D-007's rule. Do not downgrade the interpreter yet.")
    else:
        print("VERDICT: chain imports cleanly. Stay on this interpreter (D-007).")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())
