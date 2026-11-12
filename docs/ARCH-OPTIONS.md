# ARCH-OPTIONS — architecture decision input for G1

Status: **decided 2026-11-12 — Option B.** Recorded as
[D-004](steering/decisions.md). This document keeps the full trade-off analysis that led to
that choice; the choice itself, with its rejected alternatives and revisit trigger, is in the
decision log.

Inputs used: `APP-OVERVIEW.md` v0.1 (§5 architecture, §6 data model, §7 method contract,
§8 LLM strategy, §9 interfaces, §11 constraints) and
[REUSE-AUDIT.md](REUSE-AUDIT.md).

**What the reuse audit changes about this decision.** It removes one whole family of
options rather than adjusting the remaining ones. There is no older codebase to
extend, wrap, port or gradually replace: the older app contains nine docstring stubs and
thirteen empty files, and not a line of program code. "Extend the old app", "keep the old
dashboard and grow it" and
"strangler-fig the old pipeline" are therefore not options at all — not because they were
weighed and rejected, but because there is nothing there to extend. All three options
below are greenfield. The audit does carry forward three *design* shapes (M5's
narrative/frame output fields, quotation-based discourse markers, and the JSON-only
cross-channel comparison prompt); every option can absorb them, so they do not
discriminate between the options.

---

## Option A — Batch pipes-and-filters over a file-backed DuckDB

**What it is:** One executable per stage
(`collect.py` → `normalise.py` → `segment.py` → `run_method.py` → `export_report.py`).
Each stage reads a table or file, writes a table or file, and is invoked by Windows Task
Scheduler. Streamlit opens the DuckDB file read-only to present results; it never writes.

**Named style:** Pipes-and-filters (batch), with a single shared file store as the
boundary between filters.

**Optimizes for:** the shortest path to a working vertical slice (SPEC-001 → SPEC-009),
trivial idempotency (re-running a filter overwrites its own output), and per-stage
testability — a stage can be run by hand on one channel and one day without a runner.
It matches the `[SW]` Structured tier exactly: one developer, local PC, no service to
operate.

**Costs:** no orchestration, so ordering, retries and "did last night's run finish?" are
each hand-rolled in Task Scheduler plus the `runs` table. Nothing can run concurrently:
DuckDB is single-writer, so a collector run during an open workbench session is a
write conflict, not a queue. CPU-only embeddings make the 2026-10-01 backfill a long
sequential loop.

**When you would regret it:** the moment two writers need the same file at once — a
backfill running while the daily run fires, or a second analyst opening the workbench
while the scheduler collects. That is not hypothetical here: §4 already promises
"daily forward" collection *and* an interactive workbench, and §11 already notes the
collector may later move to a home PC while analysis runs elsewhere — which this shape
cannot express.

**How the reuse audit affects it:** favours it. With no legacy code to respect, the
cheapest correct structure for a greenfield first slice is the one with the fewest moving
parts.

---

## Option B — Modular monolith with a domain core and adapters

**What it is:** A single installable Python package with four internal layers: `domain/`
(segments, methods, the run contract — plain Python, no I/O), `application/` (use cases
such as collect-window, run-method, build-report), `infrastructure/` (yt-dlp adapter,
DuckDB repository, LLM gateway, Quarto renderer) and `presentation/` (the Streamlit app).
Dependencies point inward; the domain can be exercised in a REPL with no database and no
network.

**Named style:** Layered modular monolith, ports-and-adapters (hexagonal) internally.

**Optimizes for:** the pluggable-method promise in §7 and the provider-independent
gateway in §8. Adding a method is a module plus a registry entry; swapping DeepSeek for
Gemini after SPEC-005's benchmark touches one adapter, not every call site. It also makes
the Layer Boundary Verification in Stage 5 meaningful rather than decorative, and it is
the only option that keeps the LLM gateway from leaking `llm_calls` writes into "pure"
method functions — the current §7 contract (`run(segments, params) -> DataFrame`) cannot
log cost or cache hits without an effect, so the gateway has to be injected or the
"pure" claim is false.

**Costs:** more structure than a five-week solo build normally justifies — folders,
protocols and constructor wiring before the first chart exists. The layering is only
worth anything if it is policed; unpoliced it decays into Option A with extra directories,
which is the worst of both. Roughly one to two extra sessions of set-up spread across
SPEC-001 and SPEC-005.

**When you would regret it:** if the six planned methods are the final set and the LLM
provider never changes. Then the ports cost real hours and bought nothing. The regret is
specifically about *provider and storage interchange*, not about testing — the domain core
paying for itself is much more likely than the adapters doing so.

**How the reuse audit affects it:** neutral-to-favourable. The audit found no legacy
module whose shape could be preserved, so nothing is lost by imposing layers from the
start — but it also means there is no messy legacy boundary the layering is there to
protect against, which is normally the strongest argument for it.

---

## Option C — Incremental, run-manifest pipeline over an append-only raw layer

**What it is:** Treats every collection as an immutable batch: raw json3 caption files and
their manifests are never rewritten; every stage is a projection keyed by `video_id` /
`segment_id`; each stage records a watermark in `runs` (already in §6) so a rerun processes
only what is missing or whose `method_version` changed. A full rebuild stays possible but is
the exception.

**Named style:** Event-driven / log-structured batch pipeline (immutable input log plus
idempotent projections).

**Optimizes for:** the two things this project will actually do repeatedly — a **daily
incremental** run (a few new videos) and a **re-run after a method change** (one method over
the whole archive). It also makes the reproducibility promise in §3 cheap: raw captions and
the manifest are the durable truth, and every derived table can be rebuilt from them. Cost
tracking per run falls out of the same bookkeeping.

**Costs:** bookkeeping is the product. Watermarks, version columns, and partial-failure
states must be designed in SPEC-001 rather than discovered later, and "what is the current
state?" becomes a query over manifests instead of `SELECT * FROM segments`. Getting a
watermark wrong is a silent gap in the data, which is worse than a slow rerun.

**When you would regret it:** if the whole archive processes in a couple of minutes. Then
every watermark is overhead protecting a rerun nobody minds paying for, and the `runs` table
becomes a diary rather than a control mechanism.

**How the reuse audit affects it:** mildly favours it. The old system had no notion of a run
manifest or a watermark — its empty `.github` workflow implies a fire-and-forget daily job
with Google Sheets as the only state — so there is no precedent here to inherit, and the
`runs` / `llm_calls` tables in §6 are already half of this design.

---

## What the options do not decide

These are separable and can be decided inside a SPEC, so they are not presented as
architecture choices: LLM provider (SPEC-005 benchmark), embedding model (SPEC-006/007),
segmentation method (SPEC-006), and the prevalent-topic threshold (SPEC-007/015).

## Two constraints that apply to all three

- **Python 3.13.1 is the installed interpreter**, and §11 already flags BERTopic's
  dependency chain (UMAP/HDBSCAN) as possibly lagging it. Whatever option is chosen, SPEC-001
  has to verify that chain installs on 3.13.1 or pin an older interpreter — this is a
  precondition, not a trade-off between options.
- **The collector must remain separable from analysis** (§5, §11): YouTube blocks datacenter
  IPs, so collection lives on a residential machine. Options B and C express this as an
  adapter boundary; Option A expresses it as "run these scripts elsewhere", which is the
  same intent with weaker enforcement.

---

## Decision (made 2026-11-12)

```
Chosen:        Option B — layered modular monolith, domain core + adapters
Reason:        §7 (pluggable methods) and §8 (provider swap after benchmark) and
               §5/§11 (collector separable from analysis) are interchange
               requirements, and only B expresses them as enforceable boundaries.
               The reuse audit left no legacy structure to preserve, so the
               layering cost is not paid twice. Option C's one valuable property
               (immutable raw layer + per-stage watermarks) is adopted as an
               invariant now, without its framework.
Revisit if:    the six methods are final and the provider unchanged for six months
               (adapters were overhead), or a measured full rebuild exceeds
               30 minutes (the trigger to adopt C's real machinery).
Migration path: add a watermark column per stage to `runs`, switch stage entry
               points to "process only rows newer than the watermark", measure the
               full-rebuild time before and after.
```

Full rationale and rejected alternatives: [D-004](steering/decisions.md).
The three options above remain as the record of what was weighed, not as live choices.
