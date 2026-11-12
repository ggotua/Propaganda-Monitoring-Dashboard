# SPEC-002: Collector — channel inventory, caption metadata, raw json3

Feature:      Collector
Priority:     P1 (the pipeline cannot start without data)
Status:       See `SPEC-002.status` — this line is for human reference only
Dependencies: SPEC-001 (schema, config, CLI, logging)
Related docs: `APP-OVERVIEW.md` v0.2 §4–§6, §11 · `decisions.md` D-004, D-005, D-009, D-012 ·
              `FEASIBILITY.md` (measured 2026-11-12) · `ANALYSIS-BRIEF.md` §4
Tier:         `[SW]` Structured (SDD-V2 Stage 2)

---

## 1. Overview

Collects, for each configured channel, the videos published since the archive start (2026-10-01),
records their caption metadata in `videos`, stores the caption track as an immutable raw `json3` file
on disk, and loads cue rows into `captions`. Idempotent: re-running a window must not duplicate a
row.

This spec is written against measurement, not assumption (`FEASIBILITY.md`):

- 100 % of sampled videos have **automatic Georgian** captions; **none** have manual captions.
- **≈69 % of titles match no configured programme**, so `programme_id` is `NULL` for most videos and
  that is a reported number, not a defect.
- Durations span **1.4–130 minutes**; both bulletins and single-story clips are in scope.
- Per-video conditions (age gate, removed video) occur and must never abort a run.

### Non-goals

- No text normalisation, no sentence merging (SPEC-003).
- No segmentation (SPEC-004/006). No topic/entity/sentiment work.
- No LLM calls: this stage costs nothing but bandwidth and time.
- No scheduling wiring (SPEC-010); the command is manual for now.
- No full-archive backfill in this spec's acceptance criteria — the command supports it, but a
  bounded, verifiable run is what "done" means here.

---

## 2. Architecture placement (D-004)

| Layer | Module | Responsibility |
|---|---|---|
| `domain` | `domain/collector.py` | `VideoMeta`, `CaptionTrack`, `ProgrammeMatch`; pure matching and classification rules |
| `application` | `application/collect.py` | the use case: plan → fetch → store, with a `VideoSource` and `Repository` protocol |
| `infrastructure` | `infrastructure/youtube.py` | yt-dlp adapter implementing `VideoSource` |
| `infrastructure` | `infrastructure/raw_store.py` | immutable raw `json3` files under `data/raw/` |
| `infrastructure` | `infrastructure/repository.py` | DuckDB upserts for channels, programmes, videos, captions |
| `presentation` | `cli.py` | new `collect` subcommand — the composition root wires the adapters |

The use case depends only on the two protocols, so the whole collector is testable offline with a
fake source that returns fixtures. **No test may touch the network.**

---

## 3. Behaviour

### 3.1 Collection plan

For each active channel in `channels.yaml` (or the one named by `--channel`):

1. Upsert the channel and every programme for it from config (so the DB reflects committed config,
   and a removed programme is visible as unconfigured rather than deleted — history is evidence).
2. List recent uploads with **`playlistend` set** (`--listing-limit`, default 120). This is
   mandatory: without it yt-dlp paginates the entire upload history.
3. Keep uploads whose `published_at ≥ --since` (default `2026-10-01`), newest first.
4. For each keeper, up to `--limit` per channel: fetch metadata, classify the programme, write raw
   captions, upsert `videos` and `captions`.

### 3.2 Caption classification (measured rules)

- `caption_kind`: `manual` if `subtitles` has a non-transcript track, else `auto` if
  `automatic_captions` does, else `none`.
- **`live_chat` and `live_chat_replay` are never transcripts** and are excluded from both dictionaries
  before classification. Counting viewer chat as captions overstates coverage (found in the probe).
- `caption_lang`: prefer `ka`, then `ka-orig`, `en`, `ru`, else the lexicographically smallest
  remaining key, else `""`.
- A video with `none` is **still recorded** in `videos` with `status = skipped_no_caption`. A skipped
  video is data: it belongs in the denominator of every coverage figure.

### 3.3 Programme matching

Case-insensitive substring match against the channel's configured `title_patterns`, longest pattern
first, ties broken by `programme_id`. No match → `programme_id = NULL`. **Never guess**, and never
assign a programme from another channel's patterns.

### 3.4 Raw storage (immutable)

`data/raw/<channel_id>/<broadcast_date_local>/<video_id>.json3`, UTF-8.

- Written **only if absent**. An existing file is never overwritten or truncated: it is the
  irreplaceable artefact (D-004), and a re-run must be able to trust it.
- Written before the database write, so a crash leaves an orphan file (harmless, reused next run)
  rather than a DB row pointing at nothing.
- Caption **metadata** (kind, lang) is durable even when no track exists — no file is written then.

### 3.5 Idempotency

- `videos`: `INSERT … ON CONFLICT (video_id) DO UPDATE` of mutable fields
  (`programme_id`, `duration_s`, `caption_kind`, `caption_lang`, `status`, `title`). `published_at`
  and `broadcast_date_local` are stable but written on update too — a corrected date must win.
- `captions`: `DELETE FROM captions WHERE video_id = ?` then insert, inside one transaction. Re-deriving
  identical cues therefore converges; a changed raw file is impossible by rule, so drift cannot
  silently occur.
- `channels`/`programmes`: upsert on their natural keys.

### 3.6 Run bookkeeping and failure policy

A `runs` row is opened (`stage='collect'`, `status='running'`) and finalised:

| Outcome | `runs.status` | CLI exit |
|---|---|---|
| Everything fetched (individual skips allowed) | `ok` | 0 |
| A client-level block (429, "not a bot", 403) | `blocked` | 5 |
| Unhandled error | `failed` | 1 |
| Database locked by another writer (D-005) | not opened | 4 |

`watermark` = the newest `published_at` successfully processed, so a later incremental run can start
from it (D-004's deferred Option-C machinery).

**Per-video conditions are not failures of the run.** Age-restricted, private, removed and
members-only videos are recorded in `runs.error`-adjacent reporting and counted, and the loop
continues. This is the single most important behaviour in the spec: the probe once aborted a
240-video run because one video was age-gated.

Throttle: `--throttle` seconds (default 2.0) after **every** network call, listing included.

### 3.7 Coverage report

Every run prints, per channel: listed, kept, captioned, no-caption, unclassified, skipped, errors.
`NULL` programme share is printed as a first-class number, because ≈69 % is expected and a reader who
does not see it will assume the classifier worked.

---

## 4. Acceptance criteria (EARS)

- **FR-1** WHEN `gtaf collect` runs against a channel, THE SYSTEM SHALL record every kept video in
  `videos` with `caption_kind` ∈ {manual, auto, none} and a non-empty `broadcast_date_local`.
- **FR-2** WHEN a video has captions, THE SYSTEM SHALL write `data/raw/…/<video_id>.json3` exactly
  once and SHALL NOT overwrite an existing file.
- **FR-3** WHEN `gtaf collect` runs twice over the same window, THE SYSTEM SHALL leave `videos` row
  counts unchanged and `captions` cue counts identical.
- **FR-4** IF a video's caption tracks contain only `live_chat`, THE SYSTEM SHALL record
  `caption_kind = none` and `caption_lang = ''`.
- **FR-5** WHEN a video's title matches no configured programme, THE SYSTEM SHALL store
  `programme_id = NULL` and count it as unclassified.
- **FR-6** IF one video fails to extract for a per-video reason (age gate, private, removed), THE
  SYSTEM SHALL continue the run and finish with `runs.status = ok`.
- **FR-7** IF the client is blocked (429 / "not a bot" / HTTP 403), THE SYSTEM SHALL stop, set
  `runs.status = blocked`, print the verbatim error, and exit 5 without retrying.
- **FR-8** WHEN a video is published before `--since`, THE SYSTEM SHALL not store it.
- **FR-9** WHEN `broadcast_date_local` is written, THE SYSTEM SHALL derive it from `published_at`
  using Tbilisi local time (D-012), not UTC.
- **FR-10** WHEN a channel has no captioned videos in the window, THE SYSTEM SHALL still print its
  coverage line with zeros.
- **FR-11** WHILE another process holds the write lock, THE SYSTEM SHALL exit 4 with
  `database is locked` and SHALL NOT retry.
- **FR-12** THE SYSTEM SHALL NOT make any LLM call.

Completion means: every FR has a passing test against a fake source, plus one bounded live run whose
coverage report is attached as evidence; ruff and `mypy --strict` clean.

---

## 5. Examples (these become tests)

| # | Given | When | Expected |
|---|---|---|---|
| 1 | fake source: 3 videos, all captioned `ka` | collect | 3 `videos`, 3 raw files, cues loaded |
| 2 | same fake source | collect twice | identical counts (FR-3) |
| 3 | tracks `{automatic_captions: {live_chat: [...]}}` | classify | `none`, `""` (FR-4) |
| 4 | tracks `{subtitles: {ka: [...]}, automatic_captions: {ka: [...]}}` | classify | `manual`, `ka` |
| 5 | tracks `{automatic_captions: {en: [...], ka: [...]}}` | classify | `auto`, `ka` |
| 6 | title `კურიერი 12 საათზე` on Rustavi 2 | classify | `rustavi2_news` |
| 7 | same title on Imedi | classify | `NULL` (no cross-channel matching) |
| 8 | title with no marker | classify | `NULL` |
| 9 | published `2026-09-30T20:30Z`, `--since 2026-10-01` | collect | not stored (FR-8) |
| 10 | published `2026-10-31T21:30Z` | collect | `broadcast_date_local = 2026-11-01` (FR-9) |
| 11 | source raises `VideoUnavailable` for video 2 of 3 | collect | 2 stored, run `ok`, 1 counted skipped (FR-6) |
| 12 | source raises `ClientBlocked` on video 2 | collect | run `blocked`, exit 5, verbatim message (FR-7) |
| 13 | raw file already exists with different bytes | collect | file unchanged, DB still consistent (FR-2) |
| 14 | channel with zero captioned videos | collect | coverage line printed with zeros (FR-10) |

---

## 6. Requirements mapping

| Requirement | Design decision / section |
|---|---|
| FR-1, FR-8, FR-9 | §3.1 plan, §3.5 upsert, `local_date_of` (D-012) |
| FR-2 | §3.4 immutable raw store |
| FR-3 | §3.5 idempotency (upsert + delete-then-insert) |
| FR-4 | §3.2 non-transcript exclusion |
| FR-5 | §3.3 programme matching, §3.7 report |
| FR-6, FR-7 | §3.6 failure policy |
| FR-10 | §3.7 coverage report |
| FR-11 | D-005, `infrastructure/db.py` |
| FR-12 | §1 non-goals; no gateway import in this spec |

---

## 7. Boundaries

✅ **Always**: add a test for a new FR; improve an error message; add a log event.

⚠️ **Ask first**: any schema change; a new third-party dependency; changing the raw-file layout after
`data/raw/` holds real files; raising the default throttle *down*.

🚫 **Never**: overwrite or delete a file under `data/raw/`; commit `data/raw/`; retry through a
proxy/VPN to evade a block; let a per-video error abort a run; insert a `videos` row before its raw
file exists.

---

## 8. Dependency and DRY check

No new runtime dependency: `yt-dlp` is already pinned for the collector and `json`/`pathlib` cover the
rest. `duckdb` writes are raw SQL through the existing connection helper (no ORM — see
`tech-stack.md`).

DRY: programme matching reuses the **pattern data** in `config/programmes.yaml` through the existing
loader; the matching *algorithm* lives once in `domain/collector.py` and is imported by the probe's
successor rather than re-implemented. Tbilisi conversion stays in `domain/invariants.py` (D-012).

Reuse of the probe: its measured rules (non-transcript exclusion, per-video vs client-level errors)
move into the domain module, and `spikes/caption_feasibility.py` becomes superseded by
`gtaf collect` for its own purpose — recorded in `STATUS.md` rather than deleted, because it produced
the evidence this spec rests on.

---

## 9. Scalability check

Volume: 6 channels × ~8–15 uploads/day × 365 ≈ 20–33k videos/year; ~10 segments/video later; caption
cues 2–4M/year.

- Listing is one request per channel page (bounded by `playlistend`), never one per video.
- Caption fetch is one request per video; the 2 s throttle dominates runtime (~15 min per 240 videos).
- Inserts are batched per video in one transaction; no query runs inside a loop.
- Raw files are small (a 30-minute transcript is tens of KB); 33k/year is a few GB at most.
- **Revisit if**: a full-year backfill exceeds 4 hours, then raise `--throttle` exploitation or shard
  by channel-date; or YouTube rate-limits at the default throttle, then it is raised, never bypassed.

---

## 10. Open questions

1. Whether live streams > 2 h should be excluded at collection or flagged downstream. **Proposal:**
   collect them (data is data) and flag with `duration_s > 7200`; segmentation decides. Recorded, not
   decided, because it costs nothing to collect and something to re-collect.
2. Whether `programmes` should keep rows for config entries later removed. **Proposal:** keep
   (history is evidence), mark `active = false`. Currently the upsert simply overwrites `active` from
   config, which matches this.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-13
Approved: 2026-11-13 (George)

### Files created

| Path | Purpose |
|---|---|
| `src/gtaf/domain/collector.py` | `UploadRef`, `CaptionCue`, `VideoMeta`, caption classification, programme matching, window rule, error classification |
| `src/gtaf/application/collect.py` | `VideoSource`/`RawStore`/`Repository` protocols, `collect_channel`, `run_collection`, coverage counters |
| `src/gtaf/infrastructure/youtube.py` | yt-dlp adapter, `json3` parsing, per-video vs client-level failure split |
| `src/gtaf/infrastructure/raw_store.py` | immutable raw payloads (`open("x")` — write once) |
| `src/gtaf/infrastructure/repository.py` | DuckDB writes respecting foreign keys (D-013) |
| `src/gtaf/cli.py` | `collect` subcommand + exit code 5 (blocked) |
| `tests/test_collector_rules.py` | 15 domain-rule tests (cases 3–8, 10) |
| `tests/test_collect.py` | 14 use-case tests against fakes (cases 1, 2, 9, 11–14) |
| `tests/test_repository.py` | 5 database tests incl. live idempotency and FK behaviour |

### Verification with evidence

```
Claim:     Lint clean across source, tests and spikes
Command:   .venv\Scripts\python.exe -m ruff check src/ tests/ spikes/
Exit code: 0
Summary:   All checks passed!
Verdict:   PASS

Claim:     Strict type check clean
Command:   .venv\Scripts\python.exe -m mypy
Exit code: 0
Summary:   Success: no issues found in 20 source files
Verdict:   PASS

Claim:     All collector tests pass, none touching the network
Command:   .venv\Scripts\python.exe -m pytest -q
Exit code: 0
Summary:   86 passed
Verdict:   PASS

Claim:     Live collection stores videos, cues and raw payloads (FR-1, FR-2, FR-9)
Command:   gtaf init-db data\gtaf.duckdb; gtaf collect --channel imedi --limit 3
Exit code: 0
Summary:   run ok; listed 120, kept 3, captioned 3, unclassified 2, skipped 0
           videos 3, captions 875, programmes 1, watermark 2026-11-12
           3 raw json3 files (29 KB, 462 KB, 32 KB)
           rows: imedi_news (1863 s), NULL (130 s), NULL (151 s) — all auto/ka
Verdict:   PASS

Claim:     Re-running the same window does not duplicate rows (FR-3)
Command:   gtaf collect --channel imedi --limit 3   (second run)
Exit code: 0
Summary:   videos 3, captions 875, raw files 3 — identical; only a new runs row
Verdict:   PASS
```

The `runs` table retains a `failed` row from the run where the foreign-key defect below first
surfaced. It is left in place deliberately: the history of a broken run is evidence, not clutter.

### Deviations from the original spec

1. **`upsert_video` uses two transactions, and channel/programme writes are read-then-write**
   (D-013). The spec assumed `ON CONFLICT DO UPDATE` would work. DuckDB 2.0 enforces foreign keys and
   rejects an upsert on a referenced parent, and it does not see a same-transaction child delete. The
   non-atomic window in cue replacement is documented at the call site; a crash is repaired by a
   re-run, because the raw payload is already on disk.
2. **SPEC-001 §5.2 was factually wrong and is corrected.** It claimed `REFERENCES` was documentation
   only. The database enforces it.
3. **`--limit` counts kept videos per channel**, not per programme type. The spec's §3.1 wording was
   ambiguous; per-channel is simpler and makes the coverage report interpretable.
4. **The probe (`spikes/caption_feasibility.py`) keeps its own copy of the classification rules.**
   The spec said the algorithm would exist once, in `domain/collector.py`, and the probe would be
   superseded by `gtaf collect` rather than refactored. That is what happened — the probe is retained
   only as the reproduction command behind `FEASIBILITY.md` and should be deleted once SPEC-003 lands.
5. **No `youtube_channel_id` is ever resolved or stored yet.** The column exists and the upsert
   preserves it, but this spec never needed the `UC…` id; resolving it belongs to a later increment.

### Lessons learned

- The single most valuable test in this spec is `test_age_gate_is_not_a_block`: it pins the exact
  behaviour that destroyed a 240-video feasibility run. A unit test is cheaper than that lesson was.
- DuckDB's foreign-key behaviour is not "incomplete" or "documented only" — it is enforced, with
  quirks that are only discoverable by running it. Guessing cost three iterations.
- A live re-run is the only honest proof of idempotency; the fake-repository test would pass even if
  the SQL were wrong.

### Next

SPEC-003 (normaliser) on a 30-video sample, which also measures ASR *quality* — the one question
`FEASIBILITY.md` explicitly did not answer.
