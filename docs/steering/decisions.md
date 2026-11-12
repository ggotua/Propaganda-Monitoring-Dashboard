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
