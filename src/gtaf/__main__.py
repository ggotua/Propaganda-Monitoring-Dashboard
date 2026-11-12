"""Allow ``python -m gtaf …`` in addition to the installed ``gtaf`` console script."""

from __future__ import annotations

from gtaf.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
