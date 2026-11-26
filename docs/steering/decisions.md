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

---

## D-025: Gemini free tier is the primary LLM; DeepSeek is the paid validator

Status: Accepted (2026-11-14). Measured with live calls; amends the role assumption in D-010.

Context: D-010 said the SPEC-005 benchmark chooses the primary provider on measured Georgian quality
and cost, with DeepSeek as the default until then. Probing both keys on 2026-11-14 changed the picture:

- **DeepSeek**: `HTTP 200`, 6 prompt + 1 completion tokens, reply `OK` — the key has balance, so it is
  usable, and it is metered per token.
- **Gemini**: `HTTP 200` on `gemini-3-flash-preview`, and the key sees 49 models supporting
  `generateContent`. Google AI Studio keys carry a **free tier**, so marginal cost is zero within quota.
- **Model names churn fast.** `gemini-2.5-flash` and `gemini-2.5-flash-lite` return *"no longer
  available to new users"* (`404`), `gemini-flash-latest` returned `503` (high demand), and
  `gemini-3.8-flash` timed out. Only `gemini-3-flash-preview` answered.
- **Reasoning tokens are real.** "Say OK" cost `promptTokenCount: 2`, `candidatesTokenCount: 1` but
  `totalTokenCount: 26` — 23 were thinking tokens. A cost model that counts only prompt+completion
  understates usage by an order of magnitude on short prompts.

Decision:
1. **Gemini free tier is the primary** for bulk work (topic labels, segmentation prompts). The binding
   constraint for this project is budget, not capability, and free beats cheap.
2. **DeepSeek is the validator**, used on samples only. D-010's requirement stands: the validator is a
   different vendor, so the two are structurally independent.
3. The gateway **must not hardcode one model name**: it takes an ordered fallback chain and moves on
   when a model is retired, overloaded or times out.
4. **Token accounting uses `totalTokenCount`**, and records `serviceTier`, because reasoning tokens are
   billed and quota is consumed by them.
5. **Free-tier data use is recorded as a caveat**: the free tier permits Google to use prompts to
   improve its products; the paid tier does not. The corpus is public broadcast output, so this is
   acceptable for this project, but it must be stated in the methodology, not assumed away.

Rejected:
- **DeepSeek as primary for parity** — pays per token on thousands of segments to gain nothing the
  benchmark could prove; free-with-quota is the better default for a research budget.
- **A single hardcoded model** — measured to break twice in ten minutes of probing.
- **Counting only prompt and completion tokens** — measured 26 total against 3 visible.
- **Assuming the free tier means unlimited** — it has RPM/RPD quotas, which the gateway must surface as
  a distinct error rather than retrying blindly.

Consequences: the benchmark's job shrinks from "which provider" to "is the free model good enough on
Georgian", which is the question that matters and the one a human must judge (D-010). Quota, not money,
becomes the operational constraint on LLM work — a good problem, and one that affects SPEC-014/015's
batch sizes. Revisit if: the free tier's terms change, its quotas drop below what a report needs, or the
benchmark shows the free model is not good enough for Georgian framing work.

---

## D-026: Measured free quota is ~11 calls/day, so batch jobs run on DeepSeek

Status: Accepted (2026-11-14). Measured the day it was written. **Amends D-025's role split.**

Context: D-025 made Gemini's free tier the primary for *bulk* work on the reasoning that free beats
cheap. The very first batch job tested that assumption and broke it:

- labelling the 30 topics through Gemini failed with `HTTP 429 — "You exceeded your current quota"`
  after **11 live calls in total** that day (1 probe + benchmark calls + 1 check);
- the same job through DeepSeek labelled **30 topics in 30 calls for $0.004608**, with no quota error;
- the gateway behaved correctly at the failure: it stopped the provider rather than rotating models to
  dodge the quota (SPEC-005 FR-5), which is why the limit was visible instead of hidden.

So the free quota is roughly an order of magnitude *smaller* than one batch, and money is not the
binding constraint it was assumed to be: thirty bilingual topic names cost **half a cent**.

Decision:
1. **Gemini free tier is for light, interactive work** — probes, spot checks, a handful of labels, the
   smoke test. Its quota is a hard daily wall, not a budget to plan around.
2. **Batch jobs run on DeepSeek.** Cost is negligible at corpus scale (30 topics = $0.0046; a 1,000-call
   framing pass would be roughly $0.15) and there is no daily cap to design around.
3. **The validator rule still holds (D-010)**, but its economics change: when the primary is DeepSeek,
   the validator is Gemini *while quota allows*, and a **human** otherwise. Validation must not silently
   become "the same vendor twice" just because the free tier is exhausted.
4. **Quota exhaustion is a scheduling fact, not an exception to retry.** `label-topics` failing with
   `QuotaExceededError` is the correct, honest outcome.

Rejected:
- **Retry Gemini later in the day** — the quota is daily; waiting hours for 30 labels that cost half a
  cent in the meantime is a bad trade.
- **Reduce labels to fit the quota** — labelling 10 of 30 topics produces a corpus with unexplained
  holes exactly where the biggest clusters are.
- **Second Gemini key** — dodging a quota with a second identity is the same class of mistake as
  rotating IPs to dodge a caption block (D-024).

Consequences: the monthly budget guard (default $20) now protects a spend that is realistically cents,
so it will not bind; its value is as a backstop against a bug that calls in a loop. The
`provider` argument exists precisely so this split is a flag, not a rewrite. Revisit if: the free tier's
quota rises above ~1,000 calls/day (then D-025's original split becomes right), or DeepSeek's prices
change materially.

---

## D-027: Segmentation cuts where meaning drifts, not where the clock says

Status: Accepted (2026-11-14). Settled by measurement, not preference.

Context: SPEC-004 shipped 90-second fixed windows as a disposable unit, and every topic figure since has
been a figure about windows rather than about stories. SPEC-006 asked for real segmentation. Three rules
were implemented and compared on 20 real videos (190–282 segments), using the same multilingual embedding
model the topic stage uses, and scored by one metric that is not circular:

- **intra** — mean similarity of adjacent sentences *inside* a segment (higher = coherent);
- **inter** — mean similarity of the last sentence of one segment to the first of the next (lower =
  the boundary actually marks a change);
- **gap = intra − inter**, the only number that measures what a boundary is for.

| method | segments | median s | intra | inter | **gap** |
|---|---|---|---|---|---|
| fixed 90 s | 190 | 96.3 | 0.4626 | 0.4776 | **−0.0150** |
| pause | 281 | 64.7 | 0.4619 | 0.4767 | **−0.0148** |
| drift | 282 | 52.1 | 0.4961 | 0.2792 | **+0.2169** |

Two findings, one of them uncomfortable:

1. **Time-based boundaries are anti-correlated with topic change.** Both fixed and pause produced a
   *negative* gap: the sentence across a boundary was slightly *more* similar to its predecessor than an
   average in-segment pair. Cutting by the clock does not merely miss topics — it mixes them.
2. **Pause-aware cutting does not help.** The intuitive rule ("people pause between topics") measured
   identically to the arbitrary one (−0.0148 vs −0.0150) and produced 48 % more segments for nothing.
   The intuition is wrong, or the pauses in this corpus are breath, not structure.

Drift — cut where similarity to the next sentence falls below the video's own 25th percentile — is the
only rule whose boundaries separate meaning, by two orders of magnitude on this gap.

Decision:
1. **Drift becomes the segmentation method** (`seg_method = "drift"`, version 1).
2. **Fixed windows remain the control**, because every existing figure was computed on them and a claim
   cannot be compared to a baseline that was overwritten.
3. **Pause is kept in code but not adopted**: measured, documented, and available as a control; it is not
   wired into the pipeline because a method with no measured benefit is a liability.
4. **The threshold is computed per video**, not globally: a flat bulletin and a heated interview have
   different similarity scales, and a global cut-off would shatter one and merge the other.

Rejected:
- **Adopt pause because it sounds right** — the measurement says it is indistinguishable from windows.
- **A global similarity threshold** — measured per-video distributions differ; a global value would be a
  hidden tuning knob that works on one channel and fails on another.
- **Keep windows and lower the claim** — the whole point of segmentation is to make topic shares mean
  something; keeping a unit that mixes topics and then disclaiming it is worse than fixing it.

Consequences: segment counts rise roughly 50 %, so the corpus must be re-segmented and **topics must be
re-run and re-labelled** — a segment id change invalidates `res_topics`, and a stale join would silently
mix methods. Drift segmentation also adds a local embedding pass (~18k sentences, minutes on CPU, no
API cost). The 3.9 % of segments shorter than 15 s suggests `min_s` needs tuning before the rebuild.
Revisit if: a better boundary signal appears (speaker turns, scene changes from video metadata), or the
re-run shows the gap does not survive at corpus scale.

### Addendum, 2026-11-14: the corpus-scale rebuild, and what it did not fix

The rebuild ran: **4,837 drift segments** (from 2,355 fixed), 62 topics, 1,849 unclassified = **38.2 %**,
against the fixed baseline's 38.6 % on 2,355 segments and 30 topics.

The improvement is real where it was measured and absent where it is usually claimed:

- the boundary gap survived at corpus scale (the mechanism is not sample size);
- topic count **doubled** (30 → 62) and the largest cluster fell from 7.1 % to 5.5 %, which is what
  cleaner units should do;
- the **outlier rate did not move**. 38.2 % versus 38.6 % is noise.

That last point is the finding worth keeping: the unclassified share is a property of *the corpus and the
model* — short ASR-noisy passages, a 0.4 `max_df`, HDBSCAN's density assumptions — and **not** an artefact
of cutting by the clock. Anyone expecting better segmentation to shrink the grey mass now has a measured
answer. The next lever is the model (embedding choice, density parameters) or the corpus (more channels),
not the boundary rule.

Two engineering notes from the rebuild, both recorded in SPEC-006: segment ids had to become
method-scoped (a fixed and a drift segment can begin on the same millisecond), and DuckDB 2.0 cannot drop
a CHECK constraint, so widening the allowed `seg_method` values required a table rebuild with its index
dropped first.

---

## D-028: WER is 12.3 % (an upper bound), so NER proceeds with a dictionary — not on raw strings

Status: Accepted (2026-11-20). Measured, then applied to a gate.

Context: G-5 in `ANALYTICAL-POLICY.md` blocks any named claim until caption WER is measured and
≤ 30 %, plus an entity-level agreement check. WER was the last unmeasured quantity in the pipeline, and
it needed a human ear: the corpus has **100 % automatic captions and no manual ones**, so there is no
clean text to compare against.

Measurement (one clip, 373 shared words, reference = the published article about the same report):

| Metric | Raw | With number rules |
|---|---|---|
| WER | 13.3 % | **12.3 %** |
| CER | 4.7 % | **4.3 %** |
| sub/del/ins | 31/13/6 | 29/11/6 |

Of the 46 errors, roughly **16 are wrong word spacing**, **13 are editorial differences** (the article is
written prose, not a transcript) and **17 are genuine recognition errors**. Adjusted estimates — labelled
estimates, not measurements — are ≈8 % ignoring spacing and ≈4–5 % ignoring editorial drift too.

Decision:
1. **The WER half of G-5 passes** (12.3 % ≤ 30 %, and as an *upper bound* the true ASR rate is lower).
   NER and actor extraction may be built.
2. **Not on raw strings.** The dictionary and fuzzy matching are mandatory because the failures are
   concentrated exactly in names: `დიჰმის` for დირჰამის, `ეშალოვნები` for ეშელონებიდან, plus split names
   like `ნურმა გომედოვი`. A string-exact lookup would silently drop them.
3. **The entity half of G-5 stays open.** WER is a word-level average; it cannot certify that *names*
   are right. The 50-mention ≥ 0.80 agreement check still gates every named claim, and now it is the only
   thing standing between NER output and a report.
4. **This number is not the corpus number.** The reference was an article rather than an audio
   transcript, and the clip was clean narration. Stratified re-measurement (narration / hearing /
   street) is required before any report cites a WER.

Rejected:
- **Treating 12.3 % as the error rate.** It is an upper bound that includes editorial rewriting; quoting
  it as "our captions are 12 % wrong" would overstate the problem in one direction and understate it in
  another, because the clean-narration sample flatters the corpus.
- **Waiting for a perfect transcript before building NER.** The gate is a threshold, not a certification;
  the dictionary requirement absorbs the known failure mode, and the entity check catches the rest.
- **Extrapolating to the whole corpus.** WER is a function of audio conditions, and those correlate with
  content — hearings and protests are both the worst audio and the most interesting material.

Consequences: NER work is unblocked with a specified guardrail. The remaining risk is **systematic, not
random**: if overlapping speech degrades recognition most, and overlapping speech is concentrated in the
confrontational material this project exists to study, then entity errors will cluster in the most
reportable content. That is the reason the next measurement is stratified rather than larger. Revisit if:
the stratified entity-level rate exceeds ~30 % in hearings or street audio, which would make the
dictionary mandatory *and* force every named claim to state its audio condition.

---

## D-029: Dictionary-first actor matching, calibrated by audit — and E501 is off

Status: Accepted (2026-11-20). Two decisions recorded together because they were made in the same hour
and both are about where effort belongs.

### Part 1 — actors are matched by dictionary, not by a model

Context: D-028 unblocked entity work but showed the failures concentrate in names. A general NER model for
Georgian would either not exist or produce output nobody can audit; a dictionary plus explicit rules
produces failures that are visible and countable.

Decision: match a 15-entry dictionary of public figures with 21 Georgian case endings, plus fuzzy matching
constrained by both **length** and **edit distance**. Every threshold was set by auditing real matches
(SPEC-011 §5): 62 → 0 → 6 → 4 fuzzy matches across four iterations, with the false positives named
(`გააცრია` "sifted", `მდინარე` "river", `მედია` "media", `გიხარია` "I'm glad").

Rejected: a ratio-only threshold (iteration 2 collapsed recall, iteration 1 leaked common nouns — the same
ratio scores both, which is why length and edit distance are needed); a general NER model (unauditable);
fuzzy matching below 7 characters (`მელია` matched four ordinary words).

Consequences: counts are **lower bounds** — an actor outside the dictionary is invisible, not invented.
That is the right failure direction for an analytical claim.

### Part 2 — E501 is disabled; `ruff format` owns line width

Context: holding `E501` at 100 columns meant that every docstring sentence longer than the column cost a
round trip to re-wrap, and re-wrapping prose to fit a column makes it read worse, not better. Across
SPEC-006 and SPEC-011 this consumed dozens of edits that changed nothing a reader cares about.

Decision: `E501` leaves the select list; `ruff format` (line-length 100) keeps **code** consistent
mechanically. The per-file `E501` exceptions for the Streamlit page, the report renderer and the spikes
are therefore removed — they existed only to work around this.

Rejected: keeping E501 and accepting the churn (it crowded out real review); raising the column to 120
just moves the arbitrary line; disabling the formatter instead would trade one mechanical rule for none.

Consequences: prose may exceed 100 columns; code does not. Revisit if a second contributor wants a hard
column rule for reviews.

---

## D-030: Co-occurrence is counted per broadcast, because per segment there is almost nothing

Status: Accepted (2026-11-20). Measured before writing the default.

Context: SPEC-012 defines an edge as two actors mentioned in the same segment — the strictest, cleanest
claim ("discussed in the same few seconds"). Implemented and run on the corpus, it produced:

- **21 of 4,837 segments** mention two or more known actors — **0.43 %**, six pairs at min 2;
- the same data grouped by **video**: **47 of 262 broadcasts** mention two or more — **17.9 %**, 22 repeated
  pairs, 14 at min 3.

The reason is structural, not a bug: drift segmentation cut the median unit to 52 seconds, and a segment is
one story. Two named people rarely share one story; a half-hour bulletin mentions several. The stricter
unit throws away 98 % of the co-occurrence evidence the corpus actually contains.

Decision:
1. **`unit = video` is the default** for the network, recorded on every result and printed with the
   denominator. The edge means "mentioned in the same broadcast".
2. **`unit = segment` stays available** for the strict claim, and the CLI states which is in use.
3. **Jaccard accompanies every pair**, with both actors' individual counts, because raw co-occurrence ranks
   fame rather than association.

Rejected:
- **Keep segment as the default and report six edges** — technically correct and analytically useless; it
  would have been a chart that says "this corpus has no networks", which is a statement about the unit.
- **Change the segmentation back to have bigger segments** — that would discard the measured improvement in
  boundary quality (D-027) to serve a downstream convenience.
- **Report only raw counts at video level** — with 262 videos and 15 names, counts alone rank whoever is
  mentioned most; Jaccard shows concentration.

Consequences: every network figure must say "same broadcast", and the wording in the CLI, report and docs
does. A video-level edge is a much weaker claim than a segment-level one, and the difference is now
explicit rather than buried in a parameter. Revisit if: the corpus gains channels and months (then segment
level may become dense enough to be the better default), or the dictionary grows enough that two names
sharing a story becomes common.

---

## D-031: A mention the ASR invented is excluded by a title/role check, and the exclusion is reported

Status: Accepted (2026-11-21). Found by review, fixed by a checkable rule.

Context: the G-8 review found three segments about **President Kavelashvili** addressing COP31 that contain
the literal string `მიხეილ სააკაშვილი`. The ASR substituted a famous surname. No matching rule could catch
this — the string really is in the text — and it exposed a gap in G-5's meaning: that gate validated "the
name appears in the text", not "the person was on air".

Decision:
1. **Role/title contradiction excludes a segment.** An actor whose role is `ex-president` in a segment that
   speaks of `პრეზიდენტი` without `ყოფილი` (former) is a contradiction; so is the reverse.
2. **Two presidents matching in one segment** is a transcription error, not a political event: excluded.
3. **Exclusions are counted and printed**, never silent. The CLI reports `excluded N (title/role
   contradiction)` with up to five example segment ids and reasons, and `ActorScan` carries them.
4. **Kavelashvili joins the dictionary**, so the substitution produces an ambiguity instead of a lonely,
   confident match.

Measured effect: **75 of 365 matched segments excluded (20 %)**, Saakashvili 108 → **84**, and the excluded
examples inspected by hand are genuinely about Kavelashvili (two spell his name correctly, one as the ASR
variant `ყავალაშვილი`, which the fuzzy matcher finds).

Rejected:
- **Publish both guarded and unguarded counts side by side** — tempting, but a reader will pick the larger
  number and the caveat will not survive; the exclusion is reported as a count and a reason instead.
- **Title heuristics for every role** — MP, analyst, party founder are too fluid; false alarms would erode
  trust in the guard and hide real mentions.
- **Dropping every segment mentioning `პრეზიდენტი` after 2024** as first suggested — that discards genuine
  coverage of the presidency, which is itself analytically interesting.

Consequences: mention counts are now **conservative** — they exclude a fifth of matched segments, some of
which may be genuine references to Saakashvili phrased without the word "former". The direction is
deliberate: undercounting a famous figure is visible as a gap; overcounting him fabricates airtime. The
trade-off is recorded here and in `G8-VALIDATION.md`, and the guard is a rule a reader can check, unlike a
model's judgement. Revisit if: a reliable second signal (video description, programme metadata) can
disambiguate without discarding segments.

---

## D-032: The caption block is re-armed by attempts; back off a week, and list via RSS

Status: Accepted (2026-11-25). Measured on the day the backoff expired.

Context: `gtaf next` released collection on 2026-11-25 after the 72-hour cap, and the attempt returned
`429` again — eleven days after the original block. Probing found something more specific than "a long
cool-down":

- a **single hand-made caption request** for a Formula video returned `HTTP 200` and 105 KB of `json3`;
- a **collect run** (listing, then the same video) returned `429` on its first caption fetch;
- once the run had failed, even single requests 429ed for a while.

So the limiter behaves like a **budget that every attempt re-arms**, and our own retry schedule was the thing
keeping it closed: a daily task that tries 120 videos is not waiting out a block, it is renewing it.

Decision:
1. **Backoff base 24 h, cap one week** (168 h), replacing 12 h/72 h. A run that fails must not come back the
   next day to fail again.
2. **Listing prefers the channel RSS feed** (`feeds/videos.xml`), which carries the newest ~15 uploads and
   costs no caption quota; yt-dlp's listing is used only when more than 15 are requested.
3. **One attempt is one small request set.** The scheduler's job is to probe gently, not to drain the budget.

Rejected:
- **Retry daily until it works** — measured to be the cause of the eleven-day block.
- **Drop the scheduled task entirely** — loses the chance to collect the moment the block lifts.
- **Rotate IPs or add cookies to dodge the limit** — D-015 declined evasion for age gates for the same
  reason: a pipeline that depends on evading a limiter breaks silently later.

Consequences: collection may now stay idle for a week at a time, so the opposition channels that the G-8
review needs (Formula, TV Pirveli — already configured, zero videos) may not arrive this month. The RSS path
is still a real improvement: it removes the heaviest request from every run and is tested. Revisit if: a
measured window shows the limiter is time-based after all, or a paid/authenticated route becomes available.

---

## D-033: The block is at the IP level — only a different egress IP helps

Status: Accepted (2026-11-26). Measured with a second, independent client.

Context: after D-032 changed the retry shape, a direct question remained — is our code path the problem, or
the IP? Two independent clients were tested against the same videos:

| Client | Result |
|---|---|
| our yt-dlp path (metadata + caption payload) | `HTTP 429` on the caption fetch, both channels |
| `youtube-transcript-api 1.2.5` (independent library, its own protocol) | `IpBlocked` on the same two videos |
| a single hand-made request after 11 days idle (25 Nov) | `200 OK`, then `429` on the next |

The second client is decisive: it does not share our code, our headers or our request shape, and it reports
the block explicitly as **IpBlocked**. Our implementation is not the cause.

Decision:
1. **Accept the IP block as an external constraint.** No further tuning of clients, throttles or listing is
   expected to help; D-032's weekly backoff stays.
2. **Add proxy support** (`gtaf collect --proxy`, `gtaf probe --proxy`), wired into both the yt-dlp options and
   the caption fetch. A different egress IP is the one lever the evidence supports.
3. **Add `gtaf probe`** — one caption request, no listing — so a human can test a proxy or another network
   without spending a run. It distinguishes three states: blocked, reachable-but-no-captions, and working.

Rejected:
- **Try another transcript library as the fix** — measured: it reports the same block.
- **Rotate user agents or headers** — the second client already sends its own; the block is not fingerprint-based.
- **Automate proxy rotation into the pipeline** — it is a paid service and an evasion decision that belongs to
  the project owner, not a default.

Consequences: collection resumes only when the egress IP changes (proxy, VPN, mobile hotspot) or YouTube lifts
the block. Everything downstream that needs more data — opposition channels, the incumbent-criticism test —
is gated on that. Revisit if: a proxy is configured and `gtaf probe` returns OK, or a hotspot attempt succeeds.

### Addendum, 2026-11-26: the "make it look like a home PC" levers were tested and do not help

The suggestion was that YouTube treats our requests as coming from a server, and that imitating a home PC
fixes it. Five variants were tried on one blocked Formula video; every one still returned `429` on the caption
payload, and none produced a `json3` file:

| Variant | Command flags | Result |
|---|---|---|
| browser TLS fingerprint | `--impersonate chrome` (with `curl_cffi` installed) | 429 |
| JS runtime for tokens | `--js-runtimes node`, plus impersonation | 429 |
| IPv4 only | `--force-ipv4`, plus the above | 429 |
| alternate player clients | `--extractor-args youtube:player_client=mweb,ios,web_embedded` | 429 |
| independent client | `youtube-transcript-api 1.2.5` | `IpBlocked` |

Two facts make the "server IP" theory unlikely on this machine. The public address is **212.58.102.238,
AS16010 Magticom Ltd, Tbilisi** — a residential ISP, not a hosting provider — and no proxy environment
variable is set (`HTTP(S)_PROXY`, `ALL_PROXY` all unset). So YouTube is not objecting to the network's
reputation; it is capping **this address after heavy use**, which is the volume behaviour D-018 measured.

The one untested local lever that genuinely changes the session from "anonymous client" to "a person's
browser" is **cookies from a signed-in browser** (`--cookies-from-browser` or an exported `cookies.txt`). That
requires the owner's decision — D-015 declined cookies for age gates precisely because they expire and fail
silently — so it is proposed rather than assumed.

---

## D-034: Two corpora, one pipeline — web publications become the primary source, broadcast stays as the reference

Status: Accepted (2026-11-26). Requested as a major architectural decision by the project owner.

Context: the broadcast corpus is frozen. YouTube blocks transcript access from this IP at the transport layer
(D-033: 429 in our client, `IpBlocked` in an independent one, and five client-side workarounds all fail). The
corpus has not grown since 14 November: **263 videos, one channel, 11 days**. Everything analytical is capped
by that — including the question the dashboard exists to answer, whether a model can see criticism of an
incumbent, which needs an opposition source.

The same two channels publish text on their own sites, and those sites are reachable now:

| Site | Reachable | Listing | robots.txt | Programs present |
|---|---|---|---|---|
| imedi.ge | yes, 106 KB archive page | `/archive` | `Allow: /`, disallows `/api/`, `/preview/` | yes — `ქრონიკა`, `გადაცემ` sections |
| formulanews.ge | yes, 70 KB listing | `/Category/All` | disallows `/tag`, `/news/%` (ambiguous; no RSS) | not yet inspected |

So the decision is not "scraping instead of YouTube" but **which corpus carries which claim**.

Decision:
1. **Two corpora, never merged.** `publications` (web articles and programme pages) and `segments` (broadcast
   transcripts) are separate tables with separate units. Every figure states its corpus; no share, count or
   comparison mixes them.
2. **Web becomes the primary source for agenda and framing** while broadcast is blocked, because it is the only
   corpus that can grow — and because it contains the opposition channel that the bias question needs.
3. **Broadcast stays as the reference corpus.** It is the only ground truth about what actually aired, and it
   is what a future unblocked collection extends. It is not deleted and not deprecated.
4. **A concordance study gates the substitution.** Before any web figure may be described as what the channel
   *broadcast*, measure the overlap: Imedi web vs Imedi broadcast over 3–13 November, comparing topic mix and
   actor mentions. If agreement is low, the web corpus is a different product and must be described as
   "what the site published", never as airtime.
5. **Unit of analysis is the publication**, not the segment: one article, or one programme-page item. Programme
   pages are first-class because the brief prioritises news and political programmes, and the site labels them.
6. **Storage respects copyright and robots.** Title, URL, publication time, source, programme, a short excerpt
   and an embedding are stored; the body text is transient (a git-ignored cache), used for analysis and not
   redistributed. Imedi is fetched fully (robots allows); **Formula starts headline-only**, because its
   `robots.txt` disallows `/news/%` and the intent is unclear — the owner can lift that restriction.

Rejected:
- **Wait for YouTube** — 11 days of waiting produced nothing, and the block is transport-level.
- **Rotating residential proxies now** — unverified for this block, a recurring cost, and an evasion decision
  that belongs to the owner; the `--proxy` path exists for when they choose it.
- **Treat web text as equivalent to the broadcast** — the tempting shortcut. A site article and a bulletin
  segment differ in register, length and audience; assuming equivalence is exactly the unmeasured leap this
  project's gates exist to prevent.
- **Drop the broadcast corpus** — it is the only evidence about actual airtime, and the only thing a future
  collection extends.

Consequences: the project is now **media monitoring of two channels across two media**, with broadcast as the
reference corpus rather than the sole input. The stance-bias question becomes answerable within days instead of
weeks. The cost is a new obligation: every published number must name its corpus, and the report gains a
corpus-provenance line. Revisit if: YouTube unblocks and broadcast grows, or the concordance study shows the
two corpora disagree so much that they must be reported as separate products.

---

## D-035: Publication stance is labelled on the excerpt, and the labels are length-sensitive

Status: Accepted (2026-11-26). Measured on ~800 stored publications.

Context: the web corpus reached 797 publications (400 TV Pirveli, 393 Imedi, 4 via listing RSS) and the stance
pipeline ran on four actors. Two results conflict, and the conflict is the finding:

| Actor | Imedi (pro-government) | TV Pirveli (opposition) |
|---|---|---|
| Ivanishvili | critical 1 | **critical 4, unclear 5** |
| Kobakhidze (PM) | supportive 1, neutral 5 | neutral 16, unclear 7, **critical 0** |
| Bochorishvili (FM) | supportive 2, neutral 22 | neutral 2, unclear 1 |

So the model **does** produce `critical` for a government-side figure when the text is polemical (Ivanishvili,
4 of 9 in the opposition outlet) — which answers the question that motivated the web corpus. It produces none
for the prime minister in the same outlet, which at first looked like the same blindness we were testing for.

Reading the texts says otherwise. The TV Pirveli articles about Kobakhidze are **reports of what he said**
(`"კაცურიც არ არის ეს ყველაფერი"`, `კობახიძე ადასტურებს…`, `…იხუმრა`). An outlet that quotes a politician
without editorialising is not criticising him, and `neutral` is a defensible label. The outlet's own polemic
appears in other pieces — the Ivanishvili ones — and there the model found it.

One methodological check was run: for six articles labelled `neutral`, the full body (up to 3,000 characters)
was fetched and relabelled. **All six moved to `unclear`** — not to `critical`. More text made the model less
decisive, not more critical, because a full article contains other speakers' statements and the model stops
being sure whose stance it is reading.

Decision:
1. **Publication stance is labelled on title + a 400-character excerpt.** It is what the pipeline stores, it
   keeps cost predictable, and the full-text experiment shows no gain in the direction that matters.
2. **The length sensitivity is recorded as a known weakness.** A label is a statement about the stored text,
   not about "the article"; where an analysis needs the full body, it must say so and re-measure.
3. **`unclear` on publications is not treated as evidence of neutrality.** With a 400-character input the model
   produces `unclear` for 7 of 23 PM articles; a share that large is a boundary problem, matching the 66.7 %
   cross-vendor disagreement on this class measured earlier (SPEC-016).

Rejected:
- **Store the full body to label it** — the experiment shows it degrades the label to `unclear`, and it would
  mean storing full article text, which D-034 avoids on copyright grounds.
- **Report the PM's zero `critical` as model blindness** — the texts do not support it; that would be a
  conclusion the data does not carry.
- **Merge publication and broadcast counts into one stance share** — forbidden by D-034, and the two now
  visibly differ in kind.

Consequences: publication stance is usable for **cross-leaning comparison within the web corpus**, and it is
not interchangeable with broadcast stance. The Ivanishvili result is the first evidence that the model can see
criticism of the incumbent side; the PM result is a reminder that "no criticism labelled" usually means "no
criticism written". Revisit if: a human labels 30 web publications to give the publication stance its own G-8
figure, or a longer excerpt shows a different pattern.

### Addendum, 2026-11-26: the excerpt was too short, and the labels moved

The excerpt cap was raised from 400 to **1,500 characters** after the concordance study showed the 400-character
setting was biasing it (D-036). Relabelling on the longer text changed the counts, in the direction the reading
of the texts predicted:

| Actor | Source | At 400 chars | At 1,500 chars |
|---|---|---|---|
| Ivanishvili | TV Pirveli (opposition) | critical 4, unclear 5 | **critical 7, unclear 14**, neutral 1, supportive 1 |
| Kobakhidze | TV Pirveli (opposition) | critical 0, neutral 16, unclear 7 | **critical 0**, neutral 16, unclear 7 |

So the earlier "all six moved to `unclear`" finding was an artefact of how the body was extracted in that
experiment — raw paragraph joining put the sidebar in the text. With the navigation-aware extractor, more text
finds **more** criticism where the criticism exists, and still finds none where the outlet only quotes the
politician. D-035's decision stands; its 400-character setting does not.

---

## D-036: Website and broadcast are concordant on the 3–13 November window — after fixing the excerpt length

Status: Accepted (2026-11-26). First measurement of the concordance that D-034 §4 requires before web figures
may be called airtime.

Context: the comparison uses Imedi only, because it is the only channel with both corpora. Window 3–13 November
2026: **4,837 broadcast segments** against **125 web publications** whose sitemap `lastmod` fell in the window.
The metric is the Spearman correlation of per-actor mention shares (same matcher in both corpora), over the 14
actors that appear in at least one of them.

Result: **rho = 0.736**, above the 0.7 threshold — the verdict is "site attention tracks airtime on this window".

The number is only reportable because of a correction worth recording. The first run, on 400-character
excerpts, gave **rho = 0.651** and the verdict "not airtime". A sensitivity check re-extracted the same 125
pages at 1,500 characters and rho rose to **0.736**. Broadcast segments are compared on up to 2,000 characters
of speech; comparing them against a 400-character web excerpt systematically depresses web mention shares, and
the "failure" was an artefact of the measurement, not a property of the channel.

For reference, a naive full-page extraction gave zero web mentions for every actor, because Imedi pages carry
about 9,600 characters of other stories below the article; the navigation-aware extractor is what makes the
comparison meaningful at all.

Decision:
1. **Web excerpts are 1,500 characters**, not 400. Applies to concordance and to publication stance, so the two
   measurements describe the same input.
2. **The concordance verdict is window-specific and actor-bounded.** It licenses the sentence "on 3–13 November,
   Imedi's site attention tracked its airtime across 14 actors". It does not license "the site equals the
   broadcast" in general, and it says nothing about Formula, whose broadcast side does not exist.
3. **Re-run the concordance whenever either side grows substantially.** A single window with 125 publications is
   a check, not a certificate.

Rejected:
- **Report 0.651 as the result** — it measured the excerpt setting, not the channel.
- **Report 0.736 without recording the 0.651 run** — the first number is the evidence that the parameter
  matters, and hiding it would make the final figure look sturdier than it is.
- **Apply the verdict to Formula** — no broadcast corpus exists for it (D-033); that remains a separate gap.

Consequences: the project can now use Imedi web data as a *stated* proxy for its airtime on this window, with
the correlation printed next to the figure. Every other channel's web data stays "what the site published".
Revisit if: a second window or a larger sample moves rho below 0.7, which would withdraw the licence.

---

## D-037: The publication G-8 failed on `critical`, and the review sheet was defective

Status: Accepted (2026-11-26). First human review of publication stance.

Context: a human reviewer labelled 30 publications against the model. Two things came out of it, and the first
is about my instrument, not the model.

**The sheet did not say which target each row was labelled for.** The sample pooled Kobakhidze and Ivanishvili,
and `write_sample` omitted the `target` column, so the reviewer had to assume one. The reported 21/30 = 70 %
therefore mixes two questions: rows whose stored label was about Ivanishvili were scored against a human
labelling of Kobakhidze. **70 % is not a G-8 figure and is not recorded as one.**

What the review did establish, and what was done about each:

| Finding | Status |
|---|---|
| `critical` assigned from the article's overall tone, not its target: 4 of 5 critical labels sat on pieces attacking Ivanishvili or "the regime" that never named Kobakhidze | **Fixed in prompt v3** — target pinning, such text is `unclear` |
| Self-praise in reported speech labelled inconsistently (`supportive` once, `neutral` twice for the same genre) | **Fixed in prompt v3** — measured: `supportive` 1 → 0 on the sample |
| Model misses criticism actually aimed at Kobakhidze: human found 4 in 30, model caught 1 (later 0) | **Open** — v3 did not fix it |
| Mild support goes uncaught (a defence of his refusal of Western demands labelled `unclear`) | **Open** |
| "Check whether the model receives the title" | **Checked: it does** — `text = f"{title}. {excerpt}"` in `stance_web.py`. The row was seen and judged `neutral`, which is a judgement, not a missing input |

Decisions:
1. **The review sheet carries a per-row `target`**, and scoring is **per target** with its own floor. A pooled
   sheet without targets is now refused rather than scored.
2. **Prompt v3** adds target pinning and the reported-self-praise rule (see `STANCE-RULES.md` §0).
3. **`human_label` was not the problem and stays empty by default** — the model column sits beside it; the defect
   was the missing target, not a leading label.
4. **G-8 for the publication corpus is recorded as FAILED**, on the class that matters. The model does not label
   as `critical` the criticism a human reader finds in the opposition outlet's coverage of the prime minister.
   Treat publication stance as indicative, never as a validated measurement.

Rejected:
- **Report 70 % as the web G-8** — two questions were averaged into one number, and the sheet that produced it
  could not be scored correctly.
- **Count the four Ivanishvili-attack labels as correct** — under a Kobakhidze target they are wrong; under an
  Ivanishvili target they may be right. Without the target column the row cannot be judged at all, which is why
  the instrument, not the model, was the first thing to fix.
- **Treat prompt v3 as the fix for under-detection** — measured: Kobakhidze `critical` remains 0 in the
  opposition outlet after v3. The rule that moved labels was the target pin, which makes the model *more*
  conservative, not more sensitive.

Consequences: the web corpus's stance numbers must be published with "model-labelled, G-8 failed" attached.
Improving implicature detection needs either a stronger model on this task or a prompt built around quoted
questions and headline framing, and that is a separate experiment. Revisit if: the re-run review on the
target-aware sheet reaches 0.80 overall with `critical` above 50 %.

---

## D-038: The negative wording of the target rule caused the recall collapse; v4 states it positively

Status: Accepted (2026-11-26). Follows D-037, on a second human review.

Context: the v3 review scored **19/30 (63 %)**, or 21/30 if `neutral` and `unclear` are merged. The reviewer's
diagnosis was specific and is the reason this decision exists: the rule "label only if the target is named or
clearly implicated" was read by the model as **"only if the article is mainly about him"**. So instead of
rejecting off-target criticism, the model rejected criticism that names the target whenever the article had
another focus. `unclear` went from 7 to 9 of 23 on the Kobakhidze sample, and recall collapsed: of **11**
critical publications it caught **4**, and **0 of 2** supportive.

Two things were also confirmed as fixed: `neutral` became reliable (11 of 12 neutral labels correct) and the
self-praise quote-headlines became consistently neutral.

Decision — the prompt states the rule **positively** (`stance-v4`):

> If the text names the target and attributes an action, motive or quality to him, label the stance of **that
> attribution** — the article does not need to be mainly about him.

plus the single named exception (text that never names and never clearly implicates the target is `unclear`),
and **five few-shot examples drawn from this batch**, two of them supportive, as the reviewer proposed. A
sentence was also added making the **headline** part of the evaluated text ("if the headline says he 'joked' or
'lied', that is a stance and must be labelled").

Measured on the same 52 publications:

| Target / source | v3 | v4 |
|---|---|---|
| Kobakhidze / TV Pirveli `critical` | **0** | **3** |
| Kobakhidze / TV Pirveli `unclear` | 9 | **1** |
| Ivanishvili / TV Pirveli `critical` | 6 | **14** |
| Ivanishvili / TV Pirveli `unclear` | 15 | **6** |
| Ivanishvili / Imedi `supportive` | 0 | **1** |

Spot-checked against the reviewer's own list: v4 recovers **all three** Kobakhidze pieces they named (the
Khukhashvili "eating Mdinaradze means eating Kobakhidze", the Kharazishvili honour, the "joked about the threat"
headline) and **all four** Ivanishvili pieces (Goszewska's sanctions demand, Khukhashvili's metaphor, the baobab
story, the unkept Ponichala promise), plus the Zarkua defence as `supportive`.

On the reviewer's third suggestion — one label per target, so a piece can be critical of both — the pipeline
already works that way: stance is rendered and stored **per target**, so the Khukhashvili article now carries
`critical` under both Ivanishvili and Kobakhidze. No code change was needed; what was missing was a sample that
said which target each row belonged to (D-037).

Rejected:
- **Treat v4 as validated** — it is not. The counts moved in the direction the reviewer predicted and match the
  cases they named, but the labels were not re-reviewed by a human. Until they are, the web-corpus G-8 stays
  FAILED and these numbers are a hypothesis with evidence, not a passing gate.
- **Merge `neutral` and `unclear` to lift the score from 63 % to 70 %** — convenient, and it would hide the
  boundary that the review was specifically checking.
- **Add examples without a positive rule** — examples alone leave the model inferring the rule from five cases,
  and the misreading came from the rule's wording.

Consequences: the sheet was regenerated for a third review (`reports/g8-web-review-v4.csv`, with the target
column and v4 labels). If that review reaches 0.80 overall with `critical` recall above half, the publication
corpus earns its first G-8 pass. Revisit if: the re-review scores `critical` poorly again, which would say the
problem is the model's reading of implicature, not the prompt's wording.

---

## D-039: v4 scores 26/30 on the sheet it was tuned on — conditional pass, not a gate

Status: Accepted (2026-11-26). Third review, same 30 publications, human labels unchanged from the previous run.

Context: the reviewer kept their labels and re-scored v4 against them: **26/30 = 87 %** (27/30 if a borderline
row is counted). Ivanishvili 11/12, Kobakhidze 15/18. `critical` recall rose from 4 of 11 to **10 of 11**, and
every case the reviewer had named — Goszewska, Khukhashvili, the baobabs, the Ponichala promise, the
Kharazishvili honour, the "joked" headline — is now labelled `critical`. `neutral` stayed clean, so the fix
introduced no false positives. Zarkua's defence became the one `supportive` hit.

That is above the 0.80 gate. It is **not** recorded as a pass, for the reviewer's own reason and it is decisive:
**these are the same 30 publications that v2, v3 and v4 were all tuned against**, and v4's examples were drawn
from them. 87 % measures the fitting.

The four residual disagreements, all informative:

| Row | Human | Model | Reading |
|---|---|---|---|
| #24 Minsk audience with "Kobakhidze's and Putin's representatives" | critical | neutral | the one real miss — criticism of a named action of his |
| #14 Kartvelishvili defending the refusal of Western demands | supportive | neutral | support expressed as **defence** is still invisible; only praise is caught |
| #12 "after years of war propaganda, Ivanishvili's team…" | unclear | critical | borderline; the model's call is defensible |
| #23 Minsk press release | unclear | neutral | no practical difference — neither label carries a stance |

Decision:
1. **`review-web --exclude-reviewed`** drops every publication that appeared in an earlier
   `g8-web-review*.csv`, so a held-out draw cannot reuse tuned material. The first such draw excluded 37
   publications and produced `reports/g8-web-heldout.csv` (40 rows).
2. **The web-corpus G-8 stays CONDITIONAL**: v4 passes on tuned material, and the held-out run decides.
3. **`supportive` is declared unmeasurable on this corpus** until a source with commentary exists. Measured
   over 8 targets and roughly 200 labelled publications, `supportive` totals **three** rows. The reason is
   structural, not a prompt defect: Imedi has no opinion section (its categories are all news), TV Pirveli's
   programme pages carry video and no prose, and our own v3 rule converts the most common praise genre —
   reported self-praise — into `neutral` by design. A 40-row held-out draw therefore contains one supportive
   row, which cannot support a per-class rate.

Rejected:
- **Record 87 % as the pass** — the sample was chosen, and the prompt was fitted, against it.
- **Re-tune on the held-out sheet if it fails** — that would repeat the same error one level down; a failed
  held-out run means the fix does not generalise, and the honest response is a new source or a different model.
- **Force more `supportive` rows by sampling by label** — that biases the agreement figure toward the rare class,
  which is the failure mode D-038's sampling rule exists to prevent.

Consequences: the publication corpus is now at "87 % on tuned material, held-out pending", and its `supportive`
class is documented as untestable rather than reported as zero. Revisit if: the held-out sheet scores at or
above 0.80 with `critical` recall above half, which would let the conditional pass become a pass for the two
classes the corpus can measure.

