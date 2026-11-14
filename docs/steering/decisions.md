# decisions.md — Architecture decisions (ADR-lite, append-only)

Rules for this file: entries are never deleted or rewritten. A changed decision gets a
new entry, and the old one is marked `Superseded by D-00N`. An `Accepted` decision binds
the SPECs like a steering file: if a SPEC or an implementer wants to contradict one,
stop and ask — never reverse it quietly.

---

## D-001: Rigor tier follows the artifact's tag, not the session's mood

Status: Accepted (2026-11-11)

Context: This system contains two kinds of work that fail in different ways. The
software `[SW]` (collector, normaliser, DuckDB schema, Streamlit workbench, Quarto
export) fails by breaking, and is checked by tests and static tools. The analytical
`[DA]` / `[ML]` modules (topics, entities, ABSA, framing, agenda dynamics) fail by
producing a defensible-looking wrong number, and are checked by validity review,
Math Verification and Source Traceability. SDD-V2 and SDD-DA each contain gates aimed
at only one of those failure modes. Both workflows put the choice of rigor tier at
Stage 0, before any document is written.

Decision: `[SW]` artifacts run SDD-V2 at the **Structured** tier. `[DA]` and `[ML]`
artifacts run SDD-DA at the **Formal** tier. Every SPEC carries its tag in its title
and in `FEATURE-PLAN.md`; the tag, not the author's judgement on the day, selects the
gate set.

Rejected:
- SDD-V2 for everything — it has no Devil's Advocate pass, no Math Verification Gate
  and no Source Traceability Check, which are precisely the failure modes of a framing
  analysis that will be read by diplomats.
- SDD-DA for everything — running validity review on a `yt-dlp` wrapper is ceremony
  with no payoff, and is the over-specification Stage 0 exists to prevent.
- A single merged hybrid workflow — then every gate needs a fresh "does this apply
  here?" judgement per SPEC, which is the exact decision the Gatekeeper Table removes.

Consequences: Two gate sets must be held in mind at once, and a SPEC that is genuinely
both kinds (SPEC-005, LLM gateway plus provider benchmark, is the first) has to declare
a dominant tag and run the stricter gate. Analytical specs cost more than software
specs. Revisit if: `[SW]` code starts producing numbers that reach a report (then it
inherits the `[DA]` gates), or the validity review finds nothing on three consecutive
`[DA]` specs (then Formal was overkill for this corpus).

---

## D-002: Build from scratch; reuse only through a written audit

Status: Accepted (2026-11-11)

Context: An older, unfinished app for this same problem exists. Copying from it is the
fastest-looking move and the most expensive one to undo: its data model, caption
handling and chart code encode assumptions nobody has audited, and `APP-OVERVIEW.md`
§5–§6 already fixes a different data model (DuckDB, `video_id`/`segment_id` keys,
method contract). Reuse that silently imports a foreign model into a design that has
already chosen another, and the mismatch surfaces mid-spec rather than now.

Decision: The new system is built from scratch. No file, module or snippet is copied
from the older app until it appears as a row in `docs/REUSE-AUDIT.md` with a `reuse`
verdict and a stated reason. A module qualifies for `reuse` only with a clean
input/output, no hidden state, and no dependency the new design rejects. Reading the
older app for ideas is allowed; copying without an audit row is not.

Rejected:
- Fork or continue the older app — unfinished, scope already drifted, never audited.
- Refactor the older app into the new shape — pays the audit cost *plus* migration
  debt, with no code saved against the reference.
- Ignore it entirely — discards possibly-working caption or DB code without measuring
  it, which makes the estimate for SPEC-002 an unmeasured guess.

Consequences: Some code is written twice. The audit costs roughly one session and is
read-only, so it cannot damage the older app. Every reused module carries the extra
risk that its assumptions match `APP-OVERVIEW.md`'s model; the audit's Risk column is
where that risk is recorded, not prose in a chat. Revisit if: the audit finds a large
module that clears the reuse bar cleanly — reuse then becomes a per-module decision,
never a bulk one.

---

## D-003: Reports are produced every two months (6 per year)

Status: Accepted (2026-11-11)

Context: `KICKOFF.md` Task 0 asked whether "bimonthly" meant every two months or twice
a month. `APP-OVERVIEW.md` contains no report cadence at all — the word does not appear
in it — so the cadence was undefined rather than ambiguous. It is not a detail: the
agenda-dynamics method (M6) compares topic share across periods, and those periods must
have a fixed length or the comparison is between arbitrary windows. George chose on
2026-11-11.

Decision: A report every two months — 6 reports per year.

Rejected:
- Twice a month (24 per year) — that implies a near-real-time monitoring product with a
  different collector SLA, a different validation budget and a different UI. Daily
  collection (APP-OVERVIEW §4) is required either way; this decision governs reporting
  only.
- Left open — leaves the M6 comparison window undefined and makes the first report's
  period a silent assumption.

Consequences: Six reporting windows per year, each covering about two months of
bulletins. Monthly aggregation stays available in the workbench as an analytical view
but is not a scheduled deliverable, so no monthly export path needs building.
Revisit if: the audience asks for a monthly cycle, or the first two reports show that
two-month windows are too coarse to see a frame shift that matters.

---

## D-004: Architecture — layered modular monolith with a domain core and adapters

Status: Accepted (2026-11-12). Decided by the agent under George's explicit delegation of
2026-11-12 ("make decisions as senior software engineer"), recorded here rather than left
implicit.

Context: `APP-OVERVIEW.md` §7 requires methods to be pluggable behind one contract, §8
requires swapping LLM providers after a benchmark, and §5/§11 require the collector to run
on a different machine from analysis. `REUSE-AUDIT.md` establishes greenfield: there is no
legacy structure to preserve, so layering costs nothing in fidelity to existing code.

Decision: **ARCH-OPTIONS Option B.** One Python package in four layers: `domain/` (segments,
methods, run contract — no I/O, importable in a bare REPL), `application/` (use cases),
`infrastructure/` (yt-dlp, DuckDB repository, LLM gateway, Quarto), `presentation/`
(Streamlit). Dependencies point inward.

Two cheap invariants are adopted from Option C immediately, without its machinery: raw
caption files are **immutable once written**, and `runs` holds a **per-stage watermark**, so
a later move to incremental processing is a query change rather than a redesign.

Rejected:
- Option A (batch pipes-and-filters) — cannot express provider interchange or the
  collector/analysis split as an enforceable boundary, and leaves the single-writer
  collision between scheduler and workbench unmanaged.
- Option C now (incremental framework) — spends the design budget on watermarks before
  anything has measured that a full rebuild is expensive. Its one genuinely valuable
  property is captured above as an invariant, at near-zero cost.
- Waiting for the benchmark/probe to inform the choice — neither input discriminates
  between these options; both are agnostic to layering.

Consequences: roughly one to two extra sessions of wiring across SPEC-001 and SPEC-005, and
the layer boundary must actually be checked in Stage 5 (a grep for framework imports in
`domain/`), or this decays into Option A with more folders. Revisit if: the six methods are
final and the provider has not changed for six months (the adapters were then overhead), or
a measured full rebuild exceeds 30 minutes — the pre-agreed trigger to adopt Option C's
real machinery.

---

## D-005: Exactly one writer; readers are read-only; no lock-file dependency

Status: Accepted (2026-11-12). Agent decision under the same delegation.

Context: DuckDB permits one read-write process per file. `APP-OVERVIEW.md` §4 promises a
daily scheduled collection *and* an interactive workbench over the same file, so the
collision is a normal operating condition, not an edge case — and a silent one if unhandled.

Decision: DuckDB's own file lock is the mutual-exclusion mechanism; no advisory lock library
is added. Three rules follow from it:
1. The Streamlit workbench opens the database with `read_only=True` and never writes.
2. "Run or refresh a method" in the workbench (§9) dispatches a **subprocess**
   (`python -m gtaf.cli run-method …`) and polls `runs`; the Streamlit process itself never
   holds a write connection.
3. The scheduled collector treats a DuckDB lock error as a **normal, logged "workbench
   busy" outcome**: it exits non-zero with a clear message, retries nothing, and leaves the
   window marked incomplete in `runs`.

Rejected:
- An advisory lock file around every write — reimplements a guarantee DuckDB already
  provides, and introduces a second truth about who owns the file.
- Optimistic retry loops on the lock — turns a legible failure into an intermittent one.
- A separate analytics database refreshed by copy — real complexity, deferred until a
  measured read-contention problem exists.

Consequences: collection cannot run while the workbench has the file open for writing — which
it never does, by rule 1 — and a method refresh shows a progress state rather than blocking
the UI. Revisit if: read-only Streamlit concurrency becomes insufficient (e.g. multi-user
hosting), or a second machine must read the same file (that is a move to a server DB, not a
patch).

---

## D-006: Method contract takes an injected context, not ambient side effects

Status: Accepted (2026-11-12). Agent decision under the same delegation. **Supersedes §7's
`run(segments, params)` signature** in `APP-OVERVIEW.md`.

Context: `APP-OVERVIEW.md` §7 declares every method `run(segments, params) -> DataFrame` and
calls it pure, while §8 requires every method's LLM calls to be cached, costed and logged in
`llm_calls`. A function cannot both be free of effects and write a cost row. As written, the
contract is false, and the cheapest way to satisfy it silently is a module-level global
client — which destroys testability and reproducibility at once.

Decision: the contract becomes `run(segments, ctx)` where `ctx` is an explicit, passed-in
context exposing `ctx.llm(prompt, …)`, `ctx.cache`, and `ctx.meter`. A method receives no
database handle, reads no environment variable, and defines no module-level client. "Pure"
is redefined as **no ambient state**: given the same segments and a context returning the
same responses, the method yields the same output. Tests pass a `FakeCtx` that records
prompts and returns fixtures.

Rejected:
- Keep `run(segments, params)` and let the gateway be global — makes methods untestable
  offline and hides cost attribution.
- Have the runner diff outputs to log cost — cannot attribute cost per segment.
- Return `(DataFrame, call_log)` — forces every method to thread bookkeeping it may not use,
  and makes non-LLM methods carry LLM-shaped signatures.

Consequences: `run(segments, params)` in APP-OVERVIEW §7 is amended; the registry entry is
unchanged and non-LLM methods simply ignore `ctx`. Revisit if: a method genuinely needs
multi-turn interaction with a tool other than the LLM (then `ctx` grows a narrow interface,
not a general one).

---

## D-007: Python 3.13.1 first, with a pre-approved fallback to 3.12

Status: Accepted (2026-11-12). Agent decision under the same delegation.

Context: the installed interpreter is Python 3.13.1 and the project has no stack installed.
`APP-OVERVIEW.md` §11 already flags that BERTopic's chain (UMAP → numba → llvmlite, HDBSCAN)
may lag a new interpreter. Choosing an interpreter badly is cheap to avoid now and expensive
to unwind after the schema and CLI exist.

Decision: a **decision rule, not a guess.** SPEC-001 first attempts the full chain on 3.13.1
with a hard two-hour box. If any of `numba`, `llvmlite`, `umap-learn`, `hdbscan`,
`sentence-transformers` fails to import or install, the project moves to Python 3.12
immediately — that fallback is pre-approved and is not a new decision. Exact versions are
pinned in a committed lockfile; the chosen interpreter is recorded in `tech-stack.md`.

Rejected:
- Declaring 3.12 now — pays an unverified cost (a second interpreter install) to dodge an
  unverified risk.
- Declaring 3.13 final — bets the foundation on a chain nobody has tested here.
- Trying to keep both — doubles the environment matrix for no benefit at this scale.

Consequences: SPEC-001 carries an environment gate before any schema work. Revisit if: the
3.13 attempt passes but a later method's dependency does not, which re-opens the fallback for
that method only.

---

## D-008: Caption availability is measured continuously by the collector, not by a gate

Status: Accepted (2026-11-12). Agent decision under the same delegation. **Amends KICKOFF
Task 3 and re-scopes G3.**

Context: the one-off feasibility probe is blocked (YouTube bot check, `FEASIBILITY.md`), and
it was designed to measure something the collector must record anyway: `caption_kind`,
`caption_lang` and `duration` for every video it encounters, including skipped ones. A spike
that duplicates the collector's own future output is a gate on a number that will exist
soon for free.

Decision: feasibility becomes a **derivative of collection**. SPEC-002 records caption
metadata for every video seen; the first successful run over 2026-10-01 → present produces
the feasibility table, and that table — not the spike — is what gates later phases. The spike
remains available as a standalone tool, no longer on the critical path. Two scope rules are
fixed in advance so the first table cannot trigger an improvised decision:
1. **A channel with low caption coverage is kept, not dropped.** Its coverage is reported as a
   caveat on every agenda figure. Dropping a channel would silently change the research
   question, which is a scope decision, not a data-cleaning one.
2. **No report, and no scope reduction, may rest on an estimated caption rate.** Only the
   measured table counts.

Rejected:
- Blocking SPEC-001/002 on the probe — the skeleton, schema and config do not depend on
  caption rates, so the block would idle the only work that is actually ready.
- Shipping the spike's numbers as the feasibility table — same numbers, but measured once,
  without the daily refresh the collector gives for free.
- Deciding per-channel inclusion now — cannot be decided honestly before the table exists;
  the rule above makes the eventual decision mechanical.

Consequences: G3 changes from "run the probe first" to "SPEC-002's first run must produce the
table before SPEC-007 or any report". `FEASIBILITY.md` is retained as the record of the
blocked attempt and of the three ways the eventual numbers can mislead.

---

## D-009: Three schema additions and one time convention, before SPEC-001 locks it

Status: Accepted (2026-11-12). Agent decision under the same delegation. **Extends §6.**

Context: reviewing the §6 data model against the tasks already specified turned up three
absences with near-term consequences: `videos` has `caption_kind` but no `caption_lang`, so
the feasibility table and any Georgian-vs-other analysis cannot be produced from the schema;
there is no recorded schema version, so a DuckDB file in the wild cannot be migrated
knowingly; and nothing distinguishes a UTC instant from a Tbilisi broadcast evening, which
matters because "evening news" and two-month windows are local-time concepts while storing
local time is how historical dates drift.

Decision:
1. Add `videos.caption_lang TEXT` (preferred language code, empty when none).
2. Add a `schema_meta(key TEXT PRIMARY KEY, value TEXT)` table holding `schema_version`;
   every migration script sets it, and the app refuses to run against a version it does not
   know.
3. Store all instants as UTC `TIMESTAMP`; add `videos.broadcast_date_local DATE` derived at
   ingest using Asia/Tbilisi. Window boundaries and "evening" are computed from the local
   date column, never from the UTC instant.
4. Every `res_<method>` table carries `method_version`, mirroring `segments.seg_version`, so a
   re-run under a changed method cannot be mistaken for the old result.

Rejected:
- Deriving local dates at query time — pushes a correctness rule into every query, and one
  forgetful `date_trunc('month', published_at)` silently produces a wrong window.
- Storing local time — Georgia currently observes no DST, which makes the bug invisible until
  it isn't.
- A general migration framework — YAGNI; one version key plus idempotent scripts is enough
  for a single-user DuckDB file.

Consequences: SPEC-001's DDL includes all four items; migrations are explicit table rebuilds
(DuckDB's `ALTER` surface is narrow). Revisit if: a second time zone enters the corpus.

---

## D-010: Primary LLM is a benchmark outcome; validator vendor difference is not

Status: Accepted (2026-11-12). Agent decision under the same delegation.

Context: §8 defers the provider choice to the SPEC-005 benchmark, which is correct. But two
things must not be left to that benchmark: the validation topology (risk R3, LLM-validates-LLM
circularity) and what happens when the monthly budget is exhausted mid-run.

Decision: the SPEC-005 benchmark chooses the **primary** provider on measured Georgian quality
and cost; until it reports, DeepSeek is the default primary because the binding constraint is
the ~USD 20/month ceiling, not capability. Two rules are fixed regardless of its result:
1. The validator is **always a different vendor** from the primary. Agreement between two
   versions of one vendor's model is not evidence and is never reported as such.
2. The gateway estimates cost before a call and refuses to start a run whose estimate would
   exceed the remaining monthly budget, exiting non-zero. It never degrades silently to a
   cheaper model mid-run.

Rejected:
- Letting the benchmark also choose the validation topology — it answers "which is better",
  not "how do we know", and the second question is the one that protects the reports.
- Hard-coding DeepSeek permanently — forgoes a measurement that already has a spec.
- Stopping mid-run on budget exhaustion — produces half a window, which is worse than no
  window because it looks complete.

Consequences: SPEC-005 must report cost per 1,000 Georgian tokens as a first-class result, not
an afterthought. Revisit if: a vendor publishes a Georgian-specific model whose validation
independence is credible, or the budget changes by an order of magnitude.

---

## D-011: The interpreter gate runs as a spike, not inside SPEC-001's dependency set

Status: Accepted (2026-11-12). Agent decision under the same delegation. **Amends the placement
of D-007**; D-007's trigger and fallback are unchanged.

Context: D-007 said "SPEC-001 first attempts the full chain". Writing SPEC-001 made the cost of
that placement visible: the chain is BERTopic → UMAP → numba → llvmlite → HDBSCAN →
sentence-transformers, i.e. a CPU embedding stack. Installing all of it to validate a DuckDB
schema would make the foundation spec's dependency set roughly five times larger, and a failed
install there would block work that has no exposure to embeddings at all.

Decision: the chain check moves to `spikes/bertopic_chain_check.py`, run once under the same
two-hour box, and its outcome is recorded in `docs/STATUS.md`. It must still complete **before
SPEC-007** (topics) and before SPEC-006 (segmentation) choose their engines. SPEC-001's own
dependencies are `duckdb`, `pydantic`, `pyyaml` only.

Rejected:
- Keeping it in SPEC-001 as originally worded — couples a heavy, unrelated dependency decision
  to the foundation, and turns a greenfield schema into a hostage of numba's release schedule.
- Deferring it to SPEC-007 outright — too late: SPEC-006's segmentation design depends on
  whether embeddings are available on this interpreter at all.

Consequences: the interpreter decision is made by a disposable spike rather than by the spec, and
`gtaf doctor` only verifies the light stack. Revisit if: the spike shows the chain works on
3.13.1, in which case no further action is needed and this entry is simply the record of where
the check lives.

---

## D-012: Tbilisi local date is a fixed UTC+4 offset, not `Asia/Tbilisi` via `zoneinfo`

Status: Accepted (2026-11-12). Agent decision under the same delegation. **Implements D-009's
intent with a different mechanism**; D-009's schema requirement (a local `DATE` column derived at
ingest) is unchanged.

Context: implementing D-009 surfaced a Windows-specific fact. Python's `zoneinfo` has no system
time-zone database on Windows, so resolving `Asia/Tbilisi` requires the `tzdata` package — a new
third-party dependency, which SPEC-001's Boundaries section says must be asked for first. Georgia
has observed a fixed UTC+4 with no daylight saving since 2005, and this corpus starts 2026-10-01,
so the tz database would contribute nothing but a dependency.

Decision: `TBILISI_OFFSET = timezone(timedelta(hours=4), "Asia/Tbilisi")` in
`domain/invariants.py`, used by the single `local_date_of` function. Boundaries are asserted by
tests: `2026-10-31T21:30Z → 2026-11-01`, `19:30Z → 2026-10-31`, and `20:00Z` exactly at midnight.

Rejected:
- Add `tzdata` — a dependency bought for zero accuracy across this corpus's date range.
- Pass a fixed offset at each call site — duplicates the rule D-009 exists to centralise.
- Store UTC only and convert in queries — the failure mode D-009 was written to prevent.

Consequences: correct for every date this project will handle, and wrong in principle for any
historical date before 2005 or a future DST reintroduction. Both are one constant away, and the
constant carries a comment saying so. Revisit if: the corpus acquires pre-2005 material, or
Georgia changes its offset.

---

## D-013: DuckDB 2.0 enforces foreign keys — writes must respect that

Status: Accepted (2026-11-13). Established by implementing and testing SPEC-002; **corrects a factual
assumption in SPEC-001 §5.2**, which asserted the opposite.

Context: SPEC-001 §5.2 claimed DuckDB's referential-integrity enforcement was incomplete and that
`REFERENCES` was documentation only. Implementing the collector disproved it: the database rejected a
programme for an unconfigured channel, a video naming a missing programme, and a caption outliving its
video. Three write patterns then failed in ways that took real debugging:

1. `INSERT … ON CONFLICT DO UPDATE` on `channels`/`programmes` fails while child rows reference the
   row, because the upsert is implemented as delete-then-insert.
2. `UPDATE` of a parent row fails while children reference it — and the check does **not** see a
   child `DELETE` executed in the same transaction.
3. Updating a video's indexed `programme_id` is rejected even after the cue delete, until that delete
   is committed.

Decision: treat the schema's foreign keys as live constraints, and write accordingly:
- channel/programme writes are **read-then-write** — `INSERT` when absent, `UPDATE` only the columns
  that actually differ, and a no-op when nothing differs (which also makes a re-run cheap);
- `upsert_video` replaces cues in **two transactions**: commit the cue `DELETE`, then `UPDATE`/insert
  the video and its cues. The non-atomic window is accepted because the raw payload is already on
  disk and a re-run converges.

Rejected:
- Dropping the `FOREIGN KEY` clauses to keep `ON CONFLICT` — throwing away a guarantee the database is
  willing to provide, to preserve a syntax preference.
- Doing the whole thing in one transaction with ordered statements — measured not to work; the check
  evaluates before the transaction's delete is visible.
- Caching "row exists" state in the application — a second source of truth about the schema.

Consequences: two write paths are more verbose than an upsert, and `upsert_video` has a small
non-atomic window that only a crash can expose. Both are documented at the call site. Revisit if: a
later DuckDB release makes upserts on referenced parents legal, in which case this can be simplified
and this entry marked Superseded.

---

## D-014: Collection is exclusive — nothing can read the database while it runs

Status: Accepted (2026-11-13). Measured during the first backfill. **Narrows D-005**, whose
consequences claimed "readers never block a writer".

Context: D-005 established one writer plus read-only readers, and asserted that a reader would not
block a writer. The first backfill disproved the second half: opening a read-only connection while
the collector held the file failed with `IO Error: Cannot open file … because it is being used by
another process`. DuckDB's lock is exclusive for a read-write process, so "read-only readers" and
"one writer" cannot overlap — they are sequential, not concurrent.

Decision: collection is a **maintenance window**. While `gtaf collect` runs, no other process may
open the database — not the workbench, not an ad-hoc query, not a report build. Operationally:
collection runs when no one is viewing, the workbench is closed first, and a blocked reader reports
`database is locked` and stops rather than retrying (already implemented).

Rejected:
- A second database file for readers, refreshed by copy — real complexity, deferred until a measured
  read-contention problem exists (unchanged from D-005).
- DuckDB's multi-process read mode — it does not allow a concurrent writer.
- A lock file plus retry loop — reintroduces the silent-wait failure D-005 rejected.

Consequences: the workbench and a scheduled collection cannot be used at the same time, which for a
single-analyst desktop tool is acceptable but must be stated in the runbook. A long backfill
therefore blocks analysis for its whole duration — another reason backfills are chunked per channel.
Revisit if: a second machine must read the corpus while collection continues, which is the trigger to
move to a server database or a read replica.

---

## D-015: The age-gated gap is accepted and reported; cookies are an escape hatch, not a default

Status: Accepted (2026-11-13). Agent decision under George's standing delegation ("make all
decisions as senior software developer / systems analyst and continue", 2026-11-13).

Context: the first Imedi backfill skipped **26 videos (≈9.7 % of in-window attempts)** because
YouTube demands age verification. Those videos are invisible to every coverage figure. The only way
to read them is to authenticate as George — `--cookies-from-browser` or an exported cookie file.

Decision: **accept the gap, measure it, and report it.** Every coverage figure carries the skipped
count per channel. Authentication is supported as an explicit opt-in flag (`--cookies-file`) for the
case where a specific finding needs those videos, but it is never the default and never silent.

Rejected:
- **Running authenticated by default.** Three costs, one fatal: cookies expire, so the pipeline would
  break silently weeks later and look like a YouTube block; collection would run as George's personal
  identity, which is a materially different act from reading public metadata; and a corpus whose
  contents depend on a logged-in session is not reproducible by a colleague, which violates the
  project's own reproducibility bar (APP-OVERVIEW §3).
- **Dropping age-gated videos silently.** That is the failure mode this whole project exists to
  avoid: a number that looks complete and isn't.
- **Excluding Imedi from the agenda analysis.** Overreaction to a 9.7 % slice of one channel; the
  correct response is a caveat, not a scope change.

Consequences: roughly 9 % of one channel's output is systematically absent, and it is probably not
random — age gates cluster on graphic crime and conflict footage, which is exactly the content an
agenda analysis of "what do they choose to show" cares about. That makes it a **stated limitation**,
not a rounding error, and it belongs in the methodology block of every report rather than a footnote.
Revisit if: the gap exceeds ~15 % for any channel, or a specific research question turns on those
videos, in which case a one-off authenticated run recovers them into the same store.

---

## D-016: Collection is a scheduled maintenance window, not an interactive operation

Status: Accepted (2026-11-13). Agent decision under the same delegation. **Implements D-014
operationally.**

Context: D-014 established that collection excludes readers. Measured throughput is ~7 s/video and
the full window is ~7,000 videos, so the backfill is ~13 hours and daily incremental collection will
be minutes. One 13-hour exclusive window is acceptable once; a recurring one is not.

Decision:
1. **Backfills are chunked per channel** and always run with `--skip-existing`, so they are resumable
   and never restart from zero.
2. **Daily incremental collection** (SPEC-010) runs at night, per channel, bounded by the `runs`
   watermark — it must not re-walk the archive.
3. **The workbench must say "collection in progress"**, not surface a raw `IO Error`. That is a
   SPEC-008 requirement, recorded here so it is not discovered by a user instead.
4. Analysis is not attempted during collection.

Rejected:
- **Running collection continuously in the background** — it would block analysis unpredictably,
  which is worse than a known window.
- **A second read-only copy** — real complexity deferred until contention is measured (unchanged from
  D-005/D-014).
- **Lowering the throttle to finish faster** — the throttle is the only thing standing between this
  project and a bot check that already cost it a full run.

Consequences: throughput is fixed at ~7 s/video, so a full rebuild is a nightly job, not an
interactive one. Revisit if: a nightly incremental run starts exceeding ~30 minutes, which would mean
the corpus grew faster than the schedule assumed.

---

## D-017: Sentences are transient — no `sentences` table

Status: Accepted (2026-11-13). Agent decision under the same delegation. Recorded while writing
SPEC-003.

Context: `APP-OVERVIEW.md` §6 has `captions` and `segments` but no `sentences`, while the pipeline
clearly needs a sentence unit between them. The obvious move — add a table — would require a migration,
a schema-version bump, ~2M rows/year, and a second copy of text that can drift from `captions`.

Decision: **no table.** A sentence is a deterministic function of `captions` plus
`NORMALISER_VERSION`: `normalise_cues` is pure, takes cues in, returns sentences out, with no clock,
no I/O and no state. Anything that consumes sentences recomputes them.

Rejected:
- **Persisting sentences.** Buys nothing analytically — `segments` already carries the timestamps
  traceability needs — and creates a copy that goes stale the moment the rules change.
- **Persisting a sentence id for annotations.** Premature: if a future method needs sentence-level
  labels, the key can be derived as `(video_id, start_s)`, and that is the moment to add the table,
  not now.
- **Treating normalisation as part of `segments`.** Would bury a rule inside a later stage, which is
  exactly the SoC failure the workflow warns about.

Consequences: every consumer must carry `normaliser_version` so results produced under different rules
are distinguishable (SPEC-003 §3.3). Recomputing 7,000 videos costs seconds, so this is cheap. Revisit
if: a method needs to store per-sentence annotations, or a downstream join requires a stable sentence
table.

---

## D-018: The caption endpoint rate-limits; collection runs in paced batches

Status: Accepted (2026-11-13). Established by measurement during the first full backfill, then fixed
in code. **Constrains D-016's schedule.**

Context: after roughly 260 caption payload downloads in one session, the caption/timedtext endpoint
began returning **`HTTP Error 429: Too Many Requests`** for every video (log: 119 `video_skipped`
events). Two problems were exposed at once:

1. **A classification bug.** `_download_text` treated every payload failure as per-video, so a
   429 became "skip this video" instead of "stop" — and the collector kept requesting, deepening the
   limit. This is the same shape as the age-gate bug that once killed a 240-video run.
2. **A capacity fact.** The metadata API tolerated ~260 requests in a session; the payload endpoint
   did not. So the sustainable rate is bounded by payload downloads, not by videos fetched.

Decision:
- A 429 or 403 on the caption payload raises `ClientBlockedError`, which marks the run `blocked` and
  exits 5 (SPEC-002 FR-7). The collector stops at the first one; it never retries.
- Collection runs in **paced batches**: `--limit` caps a run (~150 videos), runs are separated by
  tens of minutes, and `--skip-existing` makes each batch resume where the last stopped.
- The 2 s throttle stays. It is not the limiting factor at ~260 requests, but lowering it would make
  the limit arrive sooner.

Rejected:
- **Retrying after a 429 with backoff.** The run would appear to make progress while the limit
  deepened; a hard stop makes the state legible.
- **Raising the throttle to "hide" the problem.** It reduces throughput without changing the
  per-session budget, and the real constraint is total requests per window.
- **Authenticated requests to raise the quota.** Same three objections as D-015, and it would make
  collection depend on a personal session.

Consequences: the full backfill is a multi-day background operation, not a 13-hour one. Coverage
figures must state when collection was rate-limited, because a blocked run leaves a window
incomplete. Revisit if: a measured pattern shows the limit is per-hour rather than per-session, in
which case batches can be scheduled accordingly.

---

## D-019: D-007 resolved — the analysis stays on Python 3.13.1

Status: Accepted (2026-11-13). Measurement, not opinion: `spikes/bertopic_chain_check.py` exits 0.

Context: D-007 set a two-hour box on 3.13.1 with a pre-approved fallback to 3.12, because
BERTopic's chain (UMAP → numba → llvmlite, HDBSCAN) is the part of the stack most likely to lag a new
interpreter. D-011 moved that check out of SPEC-001 into a spike. The chain was then installed with
`uv`: torch 2.15.0, transformers 5.22.2, sentence-transformers 6.3.0, bertopic 0.17.4, umap-learn
0.6.0, hdbscan 0.8.44, numba 0.68.1, llvmlite 0.50.0, scikit-learn 1.9.1, numpy 2.5.4.

Result: **every module imports cleanly on 3.13.1.** D-007's fallback branch is not triggered and the
project stays on the installed interpreter.

Rejected:
- **Falling back to 3.12 anyway "to be safe"** — would pay a second interpreter, a second environment
  and a second lockfile to dodge a risk that has now been measured away.
- **Declaring success from the install exiting 0.** Installation and importability are different
  claims; the check imports each module in a fresh process.

Consequences: one interpreter, one environment, one lockfile. The ML stack now lives in the same venv
as the foundation, which is pinned in `requirements.lock`. Revisit if: a future dependency forces a
downgrade — and note that this chain working today is not a promise about the next release.

**A lesson recorded with the result:** the first run of the check reported `umap_learn` missing and
would have triggered a needless downgrade. The distribution is `umap-learn` but the import is `umap`.
The diagnostic had the false-negative bug it was written to prevent — "absent" read as
"incompatible". Fixed, and the module list now carries the distribution-vs-import note.

---

## D-020: mpnet-base for topics, and Georgian stopwords are mandatory

Status: Accepted (2026-11-13). Measured in `docs/TOPIC-EVAL.md`; agent decision under the standing
delegation.

Context: `APP-OVERVIEW.md` §12 left the embedding model open. SPEC-007 §2 required a measurement rather
than a preference. Two candidates were compared on 600 segments with identical parameters. Separately,
the first topic run produced clusters whose top terms were `და, რომ, ეს, არის, ამ, არ` — Georgian
function words — because `CountVectorizer` had no stopword list for Georgian.

Decision:
1. **Embedding model: `paraphrase-multilingual-mpnet-base-v2`**, chosen on outlier rate (22.8 % vs
   30.0 % for MiniLM) at ~1.9× embedding time. The spec made outlier rate the primary criterion because
   a model that discards 40 % of the corpus makes every share a lie about coverage.
2. **Georgian stopwords plus `max_df = 0.4` are mandatory** in the topic vectoriser, not optional
   tuning. The conservative list lives in `domain/topics.py`; entries are only unambiguous function
   words, because a wrong entry silently deletes real content from every topic.

Rejected:
- **MiniLM for speed.** 7 points more outliers to save 25 seconds on 600 segments is the wrong trade
  when outlier rate constrains every downstream claim.
- **No stopword list, rely on `max_df` alone.** Untested and likely insufficient: `და` appears in most
  documents, but the model also needs the rarer function words (`რომ`, `ეს`, `ამ`) suppressed.
- **A bigger Georgian stopword list from an external source.** Unmaintained lists of unknown
  provenance, and a wrong entry is invisible once applied.

Consequences: every topic run must carry the stopword version, because changing the list changes the
clusters. Measured outlier rate on the full corpus is **38.6 %**, so every share is reported beside it.
Revisit if: a Georgian-stopword source with provenance appears, or an LLM label step (SPEC-005) makes
keyword quality less load-bearing.

---

## D-021: The report is generated HTML, not Quarto

Status: Accepted (2026-11-13). Agent decision under the standing delegation. **Deviates from
`APP-OVERVIEW.md` §9**, which specifies Quarto (`format: dashboard`, `embed-resources: true`).

Context: implementing SPEC-009 required checking that toolchain. **Quarto is not installed**, and
`pandoc` is a chocolatey shim pointing at a binary that does not exist. Making Quarto work would mean
installing a ~100 MB standalone tool *and* repairing pandoc, then pinning both in a pipeline whose
reproducibility is a stated requirement (`APP-OVERVIEW.md` §3).

Decision: generate one self-contained HTML file directly from Python. Plotly's JavaScript is inlined
once (`include_plotlyjs="inline"` on the first figure, `False` afterwards), and the document contains
no external references at all — verified by a test that strips script bodies and asserts no
`src=`/`href=` points at a remote host.

Rejected:
- **Install Quarto.** Two external binaries (Quarto plus a working pandoc) to produce a single page
  whose only Quarto-specific feature would be theming. It also makes the report un-buildable on any
  machine that lacks the install.
- **CDN-linked Plotly.** The file must survive being emailed and opened offline; a CDN reference breaks
  that and is exactly what the test forbids.
- **PDF instead of HTML.** Loss of interactivity, and the audience reads on screen.

Consequences: the layout and CSS are hand-written (about 60 lines), so a future design system has no
theme to inherit. The file is ~4.8 MB, essentially all Plotly; that is the price of interactivity
without a network.

**Revisit if**: the report needs multi-page structure, PDF output, a design system, or per-section
authorship — that is the point where Quarto's install cost is repaid. Recorded in SPEC-009 §2 so the
deviation is discoverable from the spec, not only from this log.

---

## D-022: `main` is the trunk; work happens on SPEC branches; releases are tagged

Status: Accepted (2026-11-13). Agent decision under the standing delegation, executed at George's
request ("merge to main").

Context: all work since kickoff lived on `spec-000-kickoff`, which was never meant to be a permanent
branch — it existed because there was no repository history at all. Leaving it as the only branch means
no stable reference point, nothing to tag, and a future session unable to tell what is shipped from what
is in progress.

Decision:
1. **`main` is the trunk**, created at the shipped state and pushed.
2. **Each new SPEC gets a short-lived branch** (`spec-005-llm-gateway`), merged to `main` when its tests
   and gate are green. The workflow asks for this at Structured tier and it costs one command per spec.
3. **Every shipped increment is annotated-tagged**: `v0.1.0` marks the first working pipeline
   (collect → normalise → segment → topics → workbench → report).
4. `spec-000-kickoff` stays as history; it is not deleted and not force-pushed.

Rejected:
- **Continue committing to `spec-000-kickoff` forever** — a branch named after a finished task as the
  trunk is how "what is deployed?" becomes unanswerable.
- **Rebase the whole history onto `main`** — rewrites shared history for cosmetic gain.
- **Git-flow with `develop`/`release`** — two permanent branches for a solo project is ceremony with no
  reviewer to justify it.

Consequences: one extra branch operation per spec, and discipline in keeping `main` green. The tag gives
a reproducible reference for the report format and the database schema version (v2) shipped together.
Revisit if: a second contributor appears (then PR review on `main` becomes load-bearing), or the tag
scheme needs semantic meaning beyond `v0.N.0`.

---

## D-023: Publication gates — a number may be published only when it can bear the claim

Status: Accepted (2026-11-13). Agent decision as the project's analyst.

Context: the pipeline now emits plausible figures from a corpus of 263 videos, one channel, eleven days,
with 38.6 % of segments unclassified. Every one of those properties is a reason a figure could be
technically correct and analytically false. Written warnings do not survive deadlines; thresholds do.

Decision: adopt `docs/ANALYTICAL-POLICY.md` as a **binding** gate set. Seven numeric gates, of which the
load-bearing ones are:

- **G-1** a topic share is published only with ≥ 30 segments in the cell (else counts, not percentages);
- **G-2** a topic ranking only when the outlier rate ≤ 50 %;
- **G-3** two channels may be compared only when each has ≥ 14 days and ≥ 100 videos;
- **G-4** a trend only with ≥ 3 complete bimonthly windows under one method version;
- **G-5** no actor may be named until NER agreement ≥ 0.80 on a 50-mention check **and** measured WER
  ≤ 30 %.

Rejected:
- **Vague caution ("be careful with small samples")** — unenforceable, and the person applying it is the
  person with an incentive to publish.
- **Statistical significance testing on a census of broadcasts** — the corpus is the population of what
  aired, not a sample from it; the real uncertainty is caption coverage and classification error, both
  of which are reported, not tested away.
- **A single global "quality score"** — hides which specific claim is unsupported.

Consequences: some numbers that the pipeline can compute may not be published, and the reason will be a
gate rather than a judgement call. Every published figure must carry denominator, outlier rate, date
span, channel count and method version, which makes one-line captions longer and honest. Gates change
only through a new decision entry, never by editing the policy quietly. Revisit if: the corpus reaches
6 channels × 90 days, at which point G-3 and G-4 become satisfiable rather than aspirational.

---

## D-024: The 429 block is multi-day; backoff doubles instead of retrying nightly

Status: Accepted (2026-11-14). Measured, then fixed. **Amends D-018's pacing assumption.**

Context: D-018 assumed a per-session budget of ~260 caption downloads with a cool-down of a couple of
hours, and the scheduler was built to try once a day with a 200-video budget. Measurement on
2026-11-14 disproved the cool-down estimate:

- the scheduled task ran at 03:01 and was refused immediately (`HTTP 429`);
- a single-video probe at 16:00 — **21 hours after the last successful download** — was also refused;
- the corpus stayed at 263 videos across the whole day.

So the limit is not "a couple of hours"; it is multi-day, at least for this IP after the burst of
13 November. A nightly retry therefore does not wait out the block — it re-arms it.

Decision:
1. **Backoff before budget.** When collection runs are blocked, `gtaf next` returns "wait" with a time,
   and the scheduler collects nothing.
2. **The wait doubles per consecutive block**: 12 h, 24 h, 48 h, capped at **72 h**. One successful run
   resets the chain, so a single block does not cost three days.
3. A `failed` run does **not** count as a block: a crash says nothing about the rate limit, and backing
   off for the wrong reason hides real failures.

Rejected:
- **Keep retrying nightly** — measured to deepen the block; it also makes the run history a wall of
  identical failures, which trains the reader to ignore it.
- **A fixed 24 h wait** — a guess, and the measurement says the real window can exceed it.
- **Removing the scheduled task until the limit clears** — loses the opportunity to collect the moment
  the block lifts, which nobody can predict.

Consequences: the corpus may grow only every few days, so the multi-week backfill estimate from D-018
becomes a multi-month one unless the limit is per-IP and a different residential IP is used. The daily
task stays registered but will most often log "backing off" and exit 0 — which is the intended signal,
not a failure. Revisit if: a measured block clears in under 24 h, or a channel/date pattern shows the
limit applies to listing rather than payload requests.

