# SPEC-001: Foundation — repo skeleton, configuration, DuckDB schema, logging

Feature:      Foundation
Priority:     P1 (every other spec depends on it)
Status:       See `SPEC-001.status` — this line is for human reference only
Dependencies: None
Related docs: `APP-OVERVIEW.md` v0.2 §5.1, §6, §7, §11 · `decisions.md` D-004, D-005, D-007,
              D-009, D-011 · `ANALYSIS-BRIEF.md` (approved)
Tier:         `[SW]` Structured (SDD-V2 Stage 2)

---

## 1. Overview

This spec builds the floor the rest of the system stands on: the package layout chosen in
D-004, the two configuration files that name the corpus, the DuckDB schema including D-009's
four additions, structured logging, and a CLI with enough commands to create and verify a
database. It creates **no collector, no network call, no method, and no UI**.

Scope is deliberately narrow because this spec is the one that gets hard to change later:
table shapes and the writer model are expensive to revise once data exists.

### Non-goals of this spec

- No collection (`SPEC-002`), no normalisation (`SPEC-003`), no segmentation (`SPEC-004`).
- No Streamlit, no charts, no Quarto export.
- No LLM client, no `llm_calls` writes (the table is created, not used).
- No `res_<method>` tables (methods create their own in their specs; §5.4 states the contract).
- No installer, no CI workflow, no Docker.

---

## 2. Package layout

`src/` layout, one distribution named `gtaf`. Imports flow **inward only**: `domain` imports
nothing from the other three; `infrastructure` and `presentation` may import `domain` and
`application`; `application` may import `domain` and abstract ports, never `infrastructure`
concrete classes (D-004). Stage 5 verifies this by grepping `domain/` for framework imports.

```
src/gtaf/
  __init__.py
  cli.py                     # argparse entry point: init-db, check-config, doctor, schema-version
  domain/
    __init__.py
    models.py                # frozen dataclasses: Channel, Programme, Video, Caption, Segment, Run
    invariants.py            # pure predicates: is_valid_caption_span, local_date_matches, ...
    method.py                # MethodContext protocol + Method contract types (no implementation)
  application/
    __init__.py
    initialize.py            # use case: create/verify a database at a path
    config.py                # use case: load + validate config, aggregate all violations
  infrastructure/
    __init__.py
    db.py                    # connect(path, read_only) + schema version gate
    migrations/
      001_init.sql           # the DDL in §5
    config_io.py             # YAML reading, pydantic models for channels.yaml/programmes.yaml
    logging_setup.py         # JSON-lines logger
  presentation/
    __init__.py              # empty; SPEC-008 fills it
config/
  channels.yaml
  programmes.yaml
tests/
  conftest.py
  test_config.py
  test_schema.py
  test_migrations.py
  test_cli.py
logs/                        # gitignored except .gitkeep
pyproject.toml
requirements.lock            # pinned, committed
```

`domain/` must import only the standard library and `dataclasses`/`typing`. If a future
change needs `duckdb` there, that is a design error, not an import.

---

## 3. Configuration files

Two YAML files, validated at load time, never at use time. Both are committed; they are
data, not secrets.

### 3.1 `config/channels.yaml`

```yaml
schema_version: 1
channels:
  - channel_id: imedi
    name_en: Imedi
    name_ka: იმედი
    youtube_handle: "@tvimedi"
    active: true
  # ... rustavi2, postv, gpb, formula, pirveli
```

Rules:
- `channel_id` matches `^[a-z][a-z0-9_]{1,30}$` and is unique.
- `youtube_handle` starts with `@`, is unique across channels, matches `^@[A-Za-z0-9._-]{2,50}$`.
- `name_en` non-empty; `name_ka` optional.
- **No `youtube_channel_id` field.** The `UC…` identifier is resolved by the collector and
  stored in `channels.youtube_channel_id`. The six identifiers seen during research came from
  third-party aggregator sites and are therefore *unverified*; hard-coding them in a committed
  config would launder an unverified claim into the schema. Handles are what George confirmed.

### 3.2 `config/programmes.yaml`

```yaml
schema_version: 1
programmes:
  - programme_id: imedi_news_evening
    channel_id: imedi
    name_en: Evening News
    name_ka: საღამოს ამბები
    type: news
    title_patterns: ["ამბები", "სიახლე"]
    playlist_ids: []
    active: true
```

Rules:
- `programme_id` unique, `^[a-z][a-z0-9_]{1,40}$`.
- `channel_id` must exist in `channels.yaml` (configuration-level referential integrity, checked
  before any database is opened).
- `type` ∈ `{news, talk, interview}`.
- At least one of `title_patterns`, `playlist_ids` must be non-empty; otherwise the programme is
  unclassifiable and must not be in the file.
- A programme that cannot be identified from real data must not be invented: the collector
  records `programme_id = NULL` and the video as unclassified. An empty guess is worse than a
  NULL (this is the same rule that made the feasibility spike record `unknown`).

### 3.3 Validation behaviour

All violations are collected and reported together, with file and YAML path
(`programmes.yaml: programmes[3].channel_id: unknown channel 'imedi2'`), because fixing
configuration one error per run is the difference between one edit and ten.

---

## 4. Interpreter and dependency gate (D-007, D-011)

`gtaf doctor` reports, and exits non-zero if any required check fails:

| Check | Requirement |
|---|---|
| Python version | `>=3.12`; records `3.13.1` as "accepted, see D-007" |
| `duckdb` import + version | pinned in `requirements.lock` |
| `pydantic` import + version | v2 |
| `yaml` import | PyYAML |
| SQLite/DuckDB file write probe | creates a temp DB in the OS temp dir and drops it |

D-011 moves the *heavy* chain check (BERTopic → UMAP → numba → HDBSCAN →
sentence-transformers) **out of this spec** into `spikes/bertopic_chain_check.py`, run once
under the D-007 two-hour box and reported in `docs/STATUS.md`. Reason: installing a
CPU-embedding stack to validate a schema would make the foundation spec's dependency set
five times larger for no schema benefit, and a failed install would block work that does not
need it. The decision to stay on 3.13 or fall back to 3.12 is still made by that check, before
SPEC-007 — the placement moved, the gate did not.

---

## 5. Database schema

DuckDB, single file, `data/gtaf.duckdb` (gitignored). All instants are **UTC, naive
`TIMESTAMP`**; local dates are separate `DATE` columns derived at ingest (D-009). DuckDB's
`TIMESTAMPTZ` is deliberately not used: it invites the belief that comparison is
timezone-aware when the stored value is an instant.

### 5.1 Migration `001_init.sql`

```sql
CREATE TABLE schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO schema_meta (key, value) VALUES ('schema_version', '1');

CREATE TABLE channels (
    channel_id         TEXT PRIMARY KEY,
    name_en            TEXT NOT NULL,
    name_ka            TEXT,
    youtube_handle     TEXT NOT NULL UNIQUE,
    youtube_channel_id TEXT,
    active             BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE programmes (
    programme_id   TEXT PRIMARY KEY,
    channel_id     TEXT NOT NULL REFERENCES channels(channel_id),
    name_en        TEXT NOT NULL,
    name_ka        TEXT,
    type           TEXT NOT NULL CHECK (type IN ('news','talk','interview')),
    title_patterns TEXT[] NOT NULL DEFAULT [],
    playlist_ids   TEXT[] NOT NULL DEFAULT [],
    active         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE videos (
    video_id             TEXT PRIMARY KEY,
    channel_id           TEXT NOT NULL REFERENCES channels(channel_id),
    programme_id         TEXT REFERENCES programmes(programme_id),
    published_at         TIMESTAMP NOT NULL,
    broadcast_date_local DATE NOT NULL,
    title                TEXT NOT NULL,
    duration_s           INTEGER CHECK (duration_s >= 0),
    caption_kind         TEXT NOT NULL CHECK (caption_kind IN ('manual','auto','none')),
    caption_lang         TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL CHECK (status IN ('pending','captioned','skipped_no_caption','failed')),
    first_seen_at        TIMESTAMP NOT NULL
);
CREATE INDEX idx_videos_channel_date ON videos(channel_id, broadcast_date_local);
CREATE INDEX idx_videos_programme     ON videos(channel_id, programme_id);

CREATE TABLE captions (
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    idx      INTEGER NOT NULL CHECK (idx >= 0),
    start_s  REAL NOT NULL CHECK (start_s >= 0),
    end_s    REAL NOT NULL,
    text     TEXT NOT NULL,
    PRIMARY KEY (video_id, idx),
    CHECK (end_s > start_s)
);
CREATE INDEX idx_captions_video ON captions(video_id, idx);

CREATE TABLE segments (
    segment_id TEXT PRIMARY KEY,
    video_id   TEXT NOT NULL REFERENCES videos(video_id),
    start_s    REAL NOT NULL CHECK (start_s >= 0),
    end_s      REAL NOT NULL,
    text       TEXT NOT NULL,
    title_ka   TEXT,
    title_en   TEXT,
    seg_method TEXT NOT NULL CHECK (seg_method IN ('llm','texttiling','fixed')),
    seg_version TEXT NOT NULL,
    CHECK (end_s > start_s)
);
CREATE INDEX idx_segments_video ON segments(video_id, start_s);

CREATE TABLE runs (
    run_id      TEXT PRIMARY KEY,
    stage       TEXT NOT NULL,
    method      TEXT,
    params_json TEXT NOT NULL DEFAULT '{}',
    model       TEXT,
    started_at  TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    n_items     INTEGER NOT NULL DEFAULT 0,
    cost_usd    DECIMAL(10,4) NOT NULL DEFAULT 0,
    status      TEXT NOT NULL CHECK (status IN ('running','ok','failed','blocked')),
    watermark   TEXT,
    error       TEXT
);
CREATE INDEX idx_runs_stage ON runs(stage, started_at);

CREATE TABLE llm_calls (
    call_hash      TEXT PRIMARY KEY,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    input_tokens   INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens  INTEGER NOT NULL CHECK (output_tokens >= 0),
    cost_usd       DECIMAL(10,6) NOT NULL CHECK (cost_usd >= 0),
    response_json  TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL
);

CREATE TABLE validation (
    run_id         TEXT NOT NULL REFERENCES runs(run_id),
    segment_id     TEXT NOT NULL REFERENCES segments(segment_id),
    validator_model TEXT NOT NULL,
    agreement      REAL CHECK (agreement BETWEEN 0 AND 1),
    human_label    TEXT,
    PRIMARY KEY (run_id, segment_id)
);
```

### 5.2 Why no foreign-key reliance

DuckDB's referential-integrity enforcement is incomplete across operations and versions. The
`REFERENCES` clauses above are documentation and best-effort; **enforcement is in code** —
every insert path asserts that its parent exists, in the same transaction, before writing
(`domain/invariants.py` predicates called by the application layer). A reviewer must not read
`REFERENCES` as a guarantee.

### 5.3 Time conventions

- `published_at`: UTC instant, naive.
- `broadcast_date_local`: `DATE`, computed once at ingest as
  `published_at.astimezone(Asia/Tbilisi).date()`.
- Reporting windows and "evening" are defined on `broadcast_date_local`.
- Invariant asserted on insert:
  `broadcast_date_local == local_date(published_at, 'Asia/Tbilisi')`.
  Storing the derived date is deliberate duplication: it makes the window column indexable and
  puts the conversion in one place (D-009). A recomputation mismatch is a bug, not a convention
  choice.

### 5.4 Result table contract (created by method specs, not here)

Every `[ML]`/`[DA]` spec that adds a method creates `res_<method>` with at least:

```sql
segment_id     TEXT PRIMARY KEY REFERENCES segments(segment_id),
run_id         TEXT NOT NULL REFERENCES runs(run_id),
method_version TEXT NOT NULL
```

`method_version` is mandatory (D-009): a re-run under changed logic must be distinguishable
from the old result without consulting timestamps.

### 5.5 Idempotency

- Re-running `001_init.sql` on an empty path creates everything; on an existing DB it is a
  no-op because the migration runner checks `schema_meta` first.
- All future inserts use `INSERT … ON CONFLICT (… ) DO UPDATE`, keyed on natural keys
  (`video_id`, `(video_id, idx)`, `segment_id`), so a re-run of any stage cannot duplicate rows.
- Migration files are **append-only**: `002_…` never edits `001_…`.

---

## 6. Invariants

These are assertions (not exceptions — see the exception/assertion rule): a violation means the
pipeline is wrong and must fail at the point of violation.

| ID | Invariant | Where enforced |
|---|---|---|
| INV-1 | `schema_meta.schema_version` equals the only version the code knows (currently `1`) | connection open, every process |
| INV-2 | `videos.video_id` is unique | PK + upsert |
| INV-3 | Captions for a video have `idx` contiguous from 0 | ingest assertion (post-write check) |
| INV-4 | Every caption has `end_s > start_s >= 0` | CHECK + domain predicate |
| INV-5 | `broadcast_date_local` equals the Tbilisi date of `published_at` | ingest assertion |
| INV-6 | Every `programme_id` referenced by a video exists, and its `channel_id` equals the video's | ingest assertion |
| INV-7 | Every segment lies inside `[0, duration_s]` of its video | segment ingest assertion |
| INV-8 | `runs.status = 'ok'` implies `finished_at IS NOT NULL` | run finaliser |
| INV-9 | No `res_*` row exists without `method_version` | method writer contract |

---

## 7. Logging

One JSON object per line to `logs/app.jsonl`, plus human-readable lines to stderr.
`logs/` is gitignored except `.gitkeep`.

Each record: `ts` (UTC ISO-8601), `level`, `event` (short stable key), `run_id` (nullable),
`stage`, and event-specific fields. Required events for this spec:

| event | level | fields |
|---|---|---|
| `db.created` | info | path, schema_version |
| `db.opened` | info | path, read_only, schema_version |
| `db.version_unsupported` | error | found, supported |
| `db.locked` | warning | path, reason — the D-005 "workbench busy" outcome |
| `migration.applied` | info | file, from_version, to_version |
| `config.loaded` | info | n_channels, n_programmes, path |
| `config.invalid` | error | n_violations, violations[] |
| `doctor.report` | info | python, duckdb, checks[] |

Rules: never log a full prompt or a caption body at info level (they are the corpus and may be
large); log lengths and hashes instead. Never log a token, key or `.env` value — there is no
exception to this one.

---

## 8. Acceptance criteria (EARS)

- **FR-1** WHEN `gtaf init-db <path>` runs and `<path>` does not exist, THE SYSTEM SHALL create
  the database, all §5.1 tables and `schema_version=1`, and exit 0.
- **FR-2** IF the database's `schema_version` is not the supported value, THE SYSTEM SHALL
  refuse to proceed, exit 3, and name both the found and supported versions.
- **FR-3** WHEN `gtaf init-db` runs twice on the same path, THE SYSTEM SHALL be idempotent —
  no duplicate rows, exit 0.
- **FR-4** IF one or more configuration violations exist, THE SYSTEM SHALL report **all** of them
  with file and path, and exit 2.
- **FR-5** IF a programme references a `channel_id` absent from `channels.yaml`, THE SYSTEM SHALL
  reject the configuration.
- **FR-6** IF two channels declare the same `youtube_handle`, THE SYSTEM SHALL reject the
  configuration.
- **FR-7** WHEN `gtaf check-config` runs on valid configuration, THE SYSTEM SHALL print channel
  and programme counts and exit 0.
- **FR-8** WHILE another process holds a write lock on the database, THE SYSTEM SHALL exit
  non-zero with a message containing `database is locked`, and SHALL NOT retry (D-005).
- **FR-9** IF a caption insert has `end_s <= start_s`, THE SYSTEM SHALL reject the row.
- **FR-10** IF a video insert has `broadcast_date_local` inconsistent with `published_at`, THE
  SYSTEM SHALL fail the insert with an assertion naming the expected date.
- **FR-11** THE SYSTEM SHALL write every log record as a single JSON object on one line, and
  SHALL parse back as JSON.
- **FR-12** WHEN `gtaf doctor` runs, THE SYSTEM SHALL report Python version, DuckDB version and
  a pass/fail line per required import, exiting non-zero if any fails.
- **FR-13** WHERE `read_only=True` is requested, THE SYSTEM SHALL open the database read-only and
  SHALL fail any write attempt rather than silently writing.

Completion means: every FR above has a passing test, `ruff check` and `mypy --strict` are clean
on `src/`, and a fresh `init-db` produces a database that `gtaf schema-version` reads back as 1.

---

## 9. Examples (EP + BVA) — these become the tests

| # | Given | When | Expected |
|---|---|---|---|
| 1 | no file at path | `init-db path` | exit 0, `schema_version=1` |
| 2 | existing v1 DB | `init-db path` | exit 0, row counts unchanged |
| 3 | DB with `schema_version=0` | any command | exit 3, message names 0 and 1 |
| 4 | DB with `schema_version=2` | any command | exit 3, message names 2 and 1 |
| 5 | `handle: "@tvimedi"` | `check-config` | valid |
| 6 | `handle: "tvimedi"` (no `@`) | `check-config` | exit 2, path-qualified error |
| 7 | two channels both `@postv` | `check-config` | exit 2, duplicate-handle error |
| 8 | programme `channel_id: imedi2` | `check-config` | exit 2, unknown-channel error |
| 9 | programme `type: documentary` | `check-config` | exit 2, enum error |
| 10 | programme with empty patterns and empty playlists | `check-config` | exit 2 |
| 11 | caption `start_s=1.0, end_s=1.0` | insert | rejected (boundary: not `>`) |
| 12 | caption `start_s=1.0, end_s=1.001` | insert | accepted (just above boundary) |
| 13 | caption `idx` sequence `0,1,3` | post-write check | INV-3 assertion fails |
| 14 | video `published_at=2026-10-31T21:30Z` | insert | `broadcast_date_local=2026-11-01` (Tbilisi is UTC+4, crosses midnight) |
| 15 | video `published_at=2026-10-31T19:30Z` | insert | `broadcast_date_local=2026-10-31` (boundary: 23:30 local) |
| 16 | open DB, second process `init-db` | second command | exit non-zero, `database is locked`, no retry |

Cases 11/12 and 14/15 are the boundary pairs; 9 and 10 are equivalence partitions of the
"invalid programme" class.

---

## 10. Requirements mapping

| Requirement | Design decision / section |
|---|---|
| FR-1 | §5.1 DDL + `application/initialize.py` |
| FR-2, FR-13 | `infrastructure/db.py` version gate + `read_only` connection |
| FR-3 | §5.5 idempotency; migration runner checks `schema_meta` |
| FR-4 | §3.3 aggregate validation in `infrastructure/config_io.py` |
| FR-5, FR-6 | §3.1/§3.2 cross-file referential rules |
| FR-7 | `cli.py check-config` |
| FR-8 | D-005 + §7 `db.locked` event |
| FR-9 | §5.1 `CHECK (end_s > start_s)` |
| FR-10 | §5.3 invariant INV-5 |
| FR-11 | §7 `logging_setup.py` JSON formatter |
| FR-12 | §4 `doctor` |

---

## 11. Boundaries

✅ **Always** — proceed without asking:
- Add or extend a test for an existing FR.
- Improve an error message to include the offending value.
- Add a log event that §7 already names.

⚠️ **Ask first** — pause and confirm:
- Any schema change after `001_init.sql` exists (even one created by this spec).
- Adding a third-party dependency beyond `duckdb`, `pydantic`, `pyyaml` (and dev: `pytest`,
  `ruff`, `mypy`).
- Renaming a table, column or config key.
- Changing the interpreter (D-007/D-011 territory).

🚫 **Never** — hard stop:
- Commit `data/*.duckdb`, `logs/*.jsonl` or `.env`.
- Weaken an invariant or a CHECK to make a failing test pass.
- Edit `001_init.sql` after it has run against a non-throwaway database; append `002_…`.
- Write to the database from the Streamlit process (D-005).

---

## 12. Dependency and DRY check

| Dependency | Why | Alternative rejected |
|---|---|---|
| `duckdb` | Analytical SQL over the corpus; columnar scans, pandas/arrow interop, one file | **SQLite**: no columnar scan and weak aggregate performance on 175k+ rows; **PostgreSQL**: a server to operate for a single-user local tool (YAGNI) |
| `pydantic` v2 | Config validation with error aggregation (FR-4) and typed models | Hand-written dataclass validation — ~60 lines and would re-invent error paths; only justified if we wanted zero config deps |
| `pyyaml` | `safe_load` of the two committed YAML files | `ruamel` — round-trip editing is not needed; TOML would work but YAML tolerates Georgian strings and comment-heavy config better for hand editing |
| `pytest`, `ruff`, `mypy` (dev) | Tests, lint, types per Stage 5 gate | none needed |
| argparse (stdlib) | CLI of four subcommands | `typer`/`click` — a dependency for four subcommands is not worth the liability |

**No ORM** (no SQLAlchemy): the workload is analytical SQL, and an ORM would hide the joins and
aggregations the work depends on.

DRY: the Tbilisi conversion exists once (§5.3). The schema version exists once (§5.1). The
channel/programme identifier rules exist once (§3). If SPEC-002 needs a caption-span validity
check, it imports `domain/invariants.py`; it does not restate the rule.

---

## 13. Scalability check

Expected volume: 6 channels × ~8 captioned videos/day ≈ 17.5k videos/year; ~10 segments/video ≈
175k segments/year; captions ≈ 2–4M cue rows/year.

- Indexes: `videos(channel_id, broadcast_date_local)` covers every window query;
  `captions(video_id, idx)` and `segments(video_id, start_s)` cover per-video reads.
- No query runs inside a per-item loop; inserts are batched per video in one transaction.
- Input size bound: `duration_s` and caption count are validated at ingest; a single video
  contributing > 20k caption cues is rejected as malformed (name the limit in SPEC-003).
- `read_only=True` connections for every reader (D-005) — no reader ever blocks a writer, and no
  reader can corrupt a run.
- **Revisit if:** caption cues exceed ~10M rows/year (then partition raw cues to Parquet and
  keep only derived rows in DuckDB).

---

## 14. Testing requirements

- `tests/test_config.py` — cases 5–10, plus a valid file from `config/`.
- `tests/test_schema.py` — cases 11–13, 16; INV-1…INV-9 assertions.
- `tests/test_migrations.py` — cases 1–4 (fresh, idempotent, version mismatch both sides).
- `tests/test_cli.py` — cases 1, 7, 12 and exit codes.
- Timezone cases 14/15 are the ones a reviewer should read first: they are where this schema
  would silently misreport a reporting window.
- Coverage target: ≥ 80 % on changed lines; `ruff check src/ tests/` and `mypy --strict src/`
  must be clean.

---

## 15. Open questions for this spec

1. `data/raw/<channel>/<date>/<video_id>.json3` path convention is fixed here for SPEC-002's
   benefit, but created by SPEC-002 — confirm no objection.
2. The `interviews` programme `type` exists in the schema; whether it needs distinct handling
   from `talk` is deferred to SPEC-006 (segmentation).

---

## Implementation Status

STATUS: NOT STARTED — spec awaiting `.status` = `approved`.
