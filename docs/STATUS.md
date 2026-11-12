# STATUS — GTAF

Last updated: 2026-11-12. Branch: `spec-000-kickoff`, tracking `origin`
(`github.com/ggotua/Propaganda-Monitoring-Dashboard`).
Sessions: (1) kickoff · (2) architecture decisions · (3) SPEC-001 written · (4) SPEC-001 implemented ·
(5) feasibility measured.

## Where the project stands

**The foundation exists and is verified, and feasibility is no longer unknown.** SPEC-001 is
implemented — package skeleton, corpus configuration, DuckDB schema, JSON logging, four CLI commands
— with 47 tests passing and ruff/mypy clean. The caption probe produced real numbers: 99 videos,
100 % auto-captioned in Georgian, zero manual captions.

**No collector and no data yet.** One environment question remains open: whether the CPU embedding
chain installs on Python 3.13.1 (D-007), which is *unproven* rather than failed.

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

## Gate state

| Gate | Status |
|---|---|
| G0 — orient, handles, cadence, older-app path | **Closed** (2026-11-11) |
| G1 — Analysis Brief | **Approved** |
| G1 — Architecture | **Decided** — Option B (D-004) |
| G3 — Feasibility | **Closed (measured 2026-11-12)** — 99/99 captioned, 0 manual; D-008 still requires SPEC-002's full backfill to re-measure across the whole archive |
| Remote | **Closed** — pushed, verified against the remote |
| SPEC-001 | **Approved and implemented** — evidence in the spec's Implementation Status |
| D-007 interpreter chain | **Open, unproven** — `spikes/bertopic_chain_check.py` exits 3 (absent ≠ incompatible) |

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
  when it is poisoned, or run the suite unconfined. 47 tests pass this way.
- **Python 3.13.1 has no tz database on Windows**; `zoneinfo("Asia/Tbilisi")` needs `tzdata`.
  D-012 avoids it with a fixed UTC+4 constant.
- **yt-dlp needs `playlistend`** when listing a channel or it paginates the whole upload history
  (it reached page 293, very likely triggering YouTube's bot check).
- Workspace permissions were repaired once (missing `WRITE_OWNER`); undo script and report in
  `D:\Data analysis\acl-repair-20261111\`.

## Next session, in order

1. Write **SPEC-002** (collector), now informed by measurement rather than guesses:
   - `[SW]` Structured; channel→video listing with `playlistend`, `json3` captions to
     `data/raw/<channel>/<date>/<video_id>.json3` (immutable), upsert keyed on `video_id`.
   - Programme matching from `config/programmes.yaml`, expecting **≈69 % `NULL`** — the collector
     must report per-channel coverage so an empty channel is visible.
   - Per-video skips (age gate, removed, live chat) must never abort a run; only client-level blocks
     stop it. This was learned the hard way in the probe.
   - Exclude non-transcript caption tracks (`live_chat`) from `caption_kind`.
   - Accept both bulletin-length and clip-length videos, and flag live streams > 2 h.
2. Then SPEC-003 (normaliser) on a 30-video sample, measuring ASR *quality* — the one thing
   feasibility did not measure.
3. `docs/steering/{tech-stack,conventions,principles}.md` are now written from what is true rather
   than invented.
