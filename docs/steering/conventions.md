# conventions.md — how code in this project is written

Style guide: **PEP 8, enforced by ruff** (line length 100, `target-version = py312`). Deviations
from PEP 8: none deliberate. Type checking: **mypy `strict`** over `src/` only (tests are checked by
running them, not by annotations).

## Naming

- Modules and functions: `snake_case`. Classes: `PascalCase`. Constants: `UPPER_SNAKE`.
- Identifiers that end up in the database are **slugs**: `channel_id` matches
  `^[a-z][a-z0-9_]{1,30}$` (`imedi`, `rustavi2`, `postv`), programme ids likewise. Display names in
  Georgian live in `name_ka`, never in an id.
- Log events are dotted and stable: `db.created`, `config.invalid`, `doctor.report`. Treat them as
  an API — downstream scripts match on them.

## Layering (D-004)

- `domain/` imports **only** the standard library. If a change needs `duckdb` or `pydantic` there,
  that is a design error, not an import.
- `application/` depends on `domain` and on **protocols it declares itself**. It never imports a
  concrete adapter; the composition root injects one.
- `infrastructure/` implements those protocols and may import `application` (for error types).
- `presentation/` talks to use cases, not to SQL.
- `cli.py` is the single composition root. It is the only module that knows which adapter is real.

## Errors and exit codes

- Exceptions for conditions that are *unusual but expected* (bad config, missing file, lock held):
  the caller handles them. Assertions/invariant predicates for conditions that should be
  *impossible*: they fail loudly at the point of violation.
- Never `except: pass`. A blind `except Exception` must carry a justification comment; `BLE` is
  enabled precisely so this is visible in review.
- CLI exit codes are interface, not implementation: `0` ok, `1` error, `2` config invalid,
  `3` unsupported schema version, `4` database locked. Tests assert them.
- Configuration errors aggregate: report **every** violation in one run, each naming the file and
  the YAML path.

## Time

- Every instant is stored as **UTC, naive `TIMESTAMP`**. Never local time in a database column.
- A local date is a separate `DATE` column, computed once at ingest via
  `domain.invariants.local_date_of`. Tbilisi is a fixed UTC+4 constant (D-012); do not scatter
  offsets.
- Reporting windows and "evening" are defined on the local date column, never on the UTC instant.

## SQL

- Migrations are **append-only**: `001_init.sql` is never edited after it has run against a
  non-throwaway database; changes go in `002_*.sql`.
- Migration files use **full-line comments only** — the runner drops comment lines before splitting
  on `;`, so a trailing comment or a semicolon in a statement line breaks it.
- Inserts are idempotent: read the row, then insert or `UPDATE` only the differing columns.
  **Do not use `INSERT … ON CONFLICT DO UPDATE` on a table that other tables reference** — DuckDB
  implements it as delete-then-insert and the constraint check rejects it (D-013).
- **DuckDB 2.0 enforces `FOREIGN KEY` constraints.** Parent rows cannot be updated while children
  reference them, and a same-transaction child delete is not seen by the check: commit the child
  delete first, then update the parent.
- Referential integrity is therefore enforced by the database; assertions in code cover what the
  schema cannot express (cue contiguity, date consistency, segment bounds).

## Logging

- JSON lines, one object per line, via `log_event(logger, level, event, **fields)`.
- Never log a caption body or a full prompt at info level — log lengths, ids or hashes. The corpus
  is large and is the product.
- Never log a secret, token or `.env` value. No exceptions.

## Tests

- Name tests as behaviour: `test_caption_with_zero_length_is_rejected`, not `test_caption_2`.
- Fixtures build their own inputs; a test needing invalid config must not be able to leave the
  committed `config/` invalid.
- Every numeric threshold gets boundary pairs (`0`, `1`, `-1`; `end_s == start_s` vs
  `end_s = start_s + 0.001`). Bugs live at the boundary.
- A bug fix ships with the regression test that fails on the old code.

## Documentation in code

- Every public function/class: docstring with purpose, args, returns, and any non-obvious behaviour.
- Comments explain **why**, not what. "Skip rather than break, because listings are newest-first
  in practice but treating that as a guarantee would truncate a channel" is a useful comment;
  "# loop over entries" is not.

## Commits

`type(scope): summary [SPEC-00N]` — e.g. `feat(foundation): implement SPEC-001 … [SPEC-001]`.
Docs-only decisions use `docs(decisions): … [D-00N]`. One logical change per commit; a fix carries
its regression test in the same commit.
