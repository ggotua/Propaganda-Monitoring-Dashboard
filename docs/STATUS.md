# STATUS — GTAF

Last updated: 2026-11-13. Branch: `spec-000-kickoff`, tracking `origin`
(`github.com/ggotua/Propaganda-Monitoring-Dashboard`).
Sessions: (1) kickoff · (2) architecture decisions · (3) SPEC-001 written · (4) SPEC-001 implemented ·
(5) feasibility measured · (6) SPEC-002 implemented.

## Where the project stands

**Collection was halted by a rate limit; the pipeline now runs collect → normalise → segment.** The
second backfill reached 262 videos before the caption endpoint returned `HTTP Error 429` for every
request. The cause is fixed (D-018 — a 429 on a caption payload now stops the run instead of being
mistaken for a per-video skip), and a verification run confirmed it: exit 5 on the first 429, one
event, instead of 119. SPEC-003 and SPEC-004 are both implemented.

**Current corpus: 262 videos, 9 days (2026-11-04 … 2026-11-12), ~87k cues, all auto `ka`,
2,355 segments covering 62.4 hours of broadcast.** The backfill to 2026-10-01 is a multi-day
operation in paced batches, because the caption endpoint's per-session budget is ~260 payload
downloads.

**Foundation and collector both exist and are verified.** SPEC-001 gives the schema, config, logging
and CLI; SPEC-002 gives a working collector — 86 tests, ruff/mypy clean, and a live run that stored
3 videos, 875 caption cues and 3 immutable raw payloads. A window has been collected end to end for
the first time.

**What is still missing:** text normalisation and everything downstream of it. No sentences, no
segments, no topics, no report.

### Corpus so far (2026-11-13)

| Quantity | Value |
|---|---|
| Videos stored | **245** — Imedi only |
| Date coverage | 2026-11-04 … 2026-11-12 — **9 of the 43 days in the window** |
| Caption cues | 87,482 |
| Caption kind | 245 auto, 0 manual, 0 missing |
| Raw `json3` files | 245 |
| Database size | 13.3 MB |
| Skipped (age-gated) | 26 ≈ 9.7 % of in-window attempts — recoverable only with cookies |
| Unclassified titles | 243 of 300 listed ≈ **81 %** (worse than the 69 % probe estimate) |

**The corpus is about 3.5× larger than APP-OVERVIEW assumed.** Imedi publishes ~27 videos/day, not
8–15, so covering the full window needs ~1,300–1,500 listing entries per channel and roughly **13
hours** of collection for all six. `--listing-limit 300` silently truncated this run to nine days —
a coverage parameter I had treated as a safety valve.

One environment question is now settled: **the analysis stays on Python 3.13.1** (D-019) — the whole
BERTopic/UMAP/numba chain imports cleanly there, so the fallback to 3.12 is not needed.

**Collection is still blocked by the caption endpoint.** A probe two hours after the first 429 was
refused again, so the quota is hours-scale rather than minutes. At ~250 payload downloads per window
the 7,000-video backfill is a **multi-week** operation, not a multi-day one — which changes the plan
more than any code written this month.

### What feasibility established

| Finding | Value | Effect |
|---|---|---|
| Caption availability | **99 of 99** sampled videos captioned; 0 gaps in any channel × type cell | No channel is dropped for lack of captions |
| Caption kind | **100 % automatic, 0 % manual** | Actor dictionary is mandatory; ASR quality unmeasured |
| Language | Georgian `ka` on all 99 | No translation step needed |
| Volume sampled | 29.0 h across 13 dates | ~2.2 h/day captioned in the sampled window |
| Programme attribution | **≈69 % of titles match no programme** | Agenda analysis runs at **channel × date**, not programme level |
| Durations | 1.4 – 130 min | Segmentation must handle clips, bulletins and one live stream differently |

## What works today

```
gtaf init-db <path>        creates the schema, idempotent, version-gated
gtaf schema-version <path> prints the stored schema version
gtaf check-config          validates channels.yaml + programmes.yaml, all violations at once
gtaf doctor                interpreter, duckdb, pydantic, yaml, write probe
python -m gtaf …           same, without the console script
```

## Decisions recorded

All in [`docs/steering/decisions.md`](steering/decisions.md), each with rejected alternatives and
a revisit trigger. D-001…D-010 were taken on 2026-11-12 under George's delegation; D-011 and D-012
were taken during implementation.

| ID | Decision |
|---|---|
| D-001 | `[DA]`/`[ML]` → Formal SDD-DA; `[SW]` → Structured SDD-V2 |
| D-002 | Build from scratch; reuse only via `REUSE-AUDIT.md` |
| D-003 | Reports every two months, 6/year |
| D-004 | Architecture: layered modular monolith, domain core + adapters |
| D-005 | One writer; read-only readers; lock error fails loudly, never retried |
| D-006 | Method contract is `run(segments, ctx)` — injected context, no ambient state |
| D-007 | Python 3.13.1 first, pre-approved fallback to 3.12 |
| D-008 | Feasibility is collector output, not a spike gate; low-coverage channel caveated, never dropped |
| D-009 | `caption_lang`, `broadcast_date_local`, `schema_meta.schema_version`, `method_version`; UTC instants |
| D-010 | Benchmark picks primary LLM; validator always a different vendor; gateway refuses over-budget runs |
| D-011 | Interpreter chain check runs as a spike, not inside SPEC-001's dependency set |
| D-012 | Tbilisi date is a fixed UTC+4 constant (Windows has no tz database; `tzdata` not worth a dependency) |
| D-013 | DuckDB 2.0 enforces foreign keys: read-then-write upserts, and a committed cue delete before the parent update |
| D-014 | Collection is exclusive: no reader can open the database while the collector runs (corrects D-005's "readers never block a writer") |

## Gate state

| Gate | Status |
|---|---|
| G0 — orient, handles, cadence, older-app path | **Closed** (2026-11-11) |
| G1 — Analysis Brief | **Approved** |
| G1 — Architecture | **Decided** — Option B (D-004) |
| G3 — Feasibility | **Closed (measured 2026-11-12)** — 99/99 captioned, 0 manual; D-008 still requires SPEC-002's full backfill to re-measure across the whole archive |
| Remote | **Closed** — pushed, verified against the remote |
| SPEC-001 | **Approved and implemented** — evidence in the spec's Implementation Status |
| SPEC-002 | **Approved and implemented** — collector works live; 90 tests; evidence in the spec |
| SPEC-003 | **Approved and implemented** — cues → sentences, 122 tests, spot-checked on a real bulletin |
| SPEC-004 | **Approved and implemented** — 2,355 fixed-window segments over 262 videos; temporary by design (SPEC-006 replaces it) |
| Schema | **v2** — migration chain in place; `topics`/`res_topics` added; the live database migrated in place with all 263 videos and 2,355 segments intact |
| SPEC-007 | **Approved and implemented** — 30 topics over 2,355 segments, **38.6 % outliers**, mpnet chosen on measurement (D-020) |
| SPEC-008 | **Approved and implemented** — Streamlit workbench renders the real corpus with the outlier rate on the page; 141 tests |
| SPEC-009 | **Approved and implemented** — self-contained 4.8 MB HTML report, no external references, outlier rate stated three times (D-021: no Quarto) |
| D-007 interpreter chain | **CLOSED 2026-11-13** — full chain imports on Python 3.13.1 (D-019). No fallback to 3.12 |
| Embedding viability | **Validated on Georgian** — 384-dim, similar pair 0.63 vs unrelated 0.25 (`spikes/embedding_smoke.py`) |

## Waiting on the physical world

1. **The embedding-chain install**, then re-run `spikes/bertopic_chain_check.py` before SPEC-006/
   SPEC-007 choose engines.
2. **A `main` branch / merge point.** Work is on `spec-000-kickoff`; there is no `main` yet, so the
   first merge will create one.
3. ~~A successful YouTube collection run~~ — **done**: the feasibility probe ran to completion on
   2026-11-12 (99 rows), so network access to YouTube from this machine works.

## Environment findings worth keeping

These cost hours this session and will cost them again if forgotten:

- **`uv` is installed and works instantly (7 s), while pip's own networking hangs** (spins at
  ~100 % CPU, emits nothing, even unconfined). Use `uv pip install --python .venv\Scripts\python.exe`.
  If a wheel must be fetched by hand, `Invoke-WebRequest` works, pip `--no-index` installs it.
- **`python -m venv` fails here** (`ensurepip` dies cleaning a sandbox temp dir). Use
  `--without-pip`, then `uv pip install`.
- **The sandboxed shell cannot complete HTTPS** — TCP connects, TLS dies for every host, while
  the harness's own fetcher works. Network steps (git push, installs) need the unconfined path,
  one approval each.
- **pytest needs help in this sandbox.** The workspace root denies `DeleteSubdirectoriesAndFiles`,
  so pytest cannot manage its own temp dirs; pass `--basetemp=.tmp\pytest` and recreate `.tmp`
  when it is poisoned, or run the suite unconfined. 86 tests pass this way.
- **Python 3.13.1 has no tz database on Windows**; `zoneinfo("Asia/Tbilisi")` needs `tzdata`.
  D-012 avoids it with a fixed UTC+4 constant.
- **yt-dlp needs `playlistend`** when listing a channel or it paginates the whole upload history
  (it reached page 293, very likely triggering YouTube's bot check).
- Workspace permissions were repaired once (missing `WRITE_OWNER`); undo script and report in
  `D:\Data analysis\acl-repair-20261111\`.

## Next session, in order

1. **SPEC-003 (normaliser)** on a 30-video sample: merge `json3` cues into timestamped sentences,
   strip ASR artefacts, and — the part nothing has measured yet — **assess ASR quality** so the NER
   and attribution risks become evidence rather than a warning. A first qualitative read of five
   transcripts is in [`ASR-QUALITY.md`](ASR-QUALITY.md): it found `>>` speaker-turn markers (which
   softens risk R1 from "no speaker information" to "no speaker identities"), bracketed non-speech
   events, and occasional foreign-script contamination.
2. **Extend the backfill, one channel at a time**, with `--listing-limit 1500 --skip-existing`
   (300 was too small — it covered 9 of 43 days). Expect ~13 h total, so it is an overnight job and
   must be chunked; collection is exclusive, so nothing else may open the database while it runs
   (D-014).
3. **Settle D-007**: install the CPU stack, re-run `spikes/bertopic_chain_check.py`, and record the
   verdict before SPEC-006/007 choose engines.
4. Delete `spikes/caption_feasibility.py` once `gtaf collect` has replaced it in practice; it is now
   only the reproduction command behind `FEASIBILITY.md`.
2. Then SPEC-003 (normaliser) on a 30-video sample, measuring ASR *quality* — the one thing
   feasibility did not measure.
3. `docs/steering/{tech-stack,conventions,principles}.md` are now written from what is true rather
   than invented.
