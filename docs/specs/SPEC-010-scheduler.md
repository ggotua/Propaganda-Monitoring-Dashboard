# SPEC-010: Scheduling, pacing and run history

Feature:      Scheduler and run log
Priority:     P1 — the corpus can only reach the window unattended
Status:       See `SPEC-010.status`
Dependencies: SPEC-002 (collector), SPEC-001 (`runs`)
Related docs: D-014, D-016, D-018 · `STATUS.md` (measured throughput and limits)
Tier:         `[SW]` Structured

---

## 1. Overview

The measured facts make this spec urgent rather than tidy:

- the window is 43 days × 6 channels ≈ **7,000 videos**;
- throughput is ~7 s/video, and the caption endpoint caps a session at **~260 payload downloads**
  (D-018), with a cool-down longer than two hours;
- collection is exclusive: nothing may read the database while it runs (D-014).

So the corpus grows in **daily batches of a few hundred videos**, over weeks. Without scheduling, that
is a month of someone remembering to type a command. This spec makes the pipeline run itself, and makes
it stop cleanly when YouTube says no.

### Non-goals

- No daemon, no queue, no retry-with-backoff loop. Windows Task Scheduler is the trigger; this spec
  provides the policy and the entry script.
- No cloud scheduling. The collector must run from a residential IP (APP-OVERVIEW §11).
- No collection when the database is locked by a reader — it exits and waits for the next run.
- No analysis scheduling. Analysis is manual until the corpus supports it.

## 2. The decision function

`gtaf next` answers one question: **should we collect now, from which channel, and how many?**

Inputs: videos already collected today, per-channel totals, the daily budget.

| Condition | Decision |
|---|---|
| Videos collected today ≥ `daily_budget` | **wait**, with the count and the reason |
| Under budget | **collect** the channel with the *fewest* videos stored, limit = `min(batch_limit, budget − collected_today)` |

Two properties matter more than the heuristic:

1. **The budget is measured, not guessed.** D-018 recorded ~260 payload downloads before a 429, so the
   default budget is **200** — a margin for listing requests and retries.
2. **Round-robin by coverage, not by schedule.** Picking the least-covered channel spreads the corpus
   across channels instead of exhausting one, which is what an agenda comparison will need.

The function is deliberately deterministic and testable offline: it reads counts, not the network.

## 3. Daily run script

`scripts/run_daily_collection.ps1` is the Task Scheduler entry point:

1. call `gtaf next`; if the decision is "wait", log and exit 0;
2. otherwise call `gtaf collect --channel <chosen> --limit <limit> --skip-existing`;
3. on exit 5 (blocked) log it and exit 0 — a scheduled run that failed because YouTube rate-limited is
   not a failed schedule, and a non-zero exit would make Task Scheduler retry into the same limit;
4. on exit 4 (database locked) log and exit 0 for the same reason;
5. on any other non-zero exit, exit with that code so the scheduler's history shows a real failure.

## 4. Run history

`gtaf runs [--limit N]` prints recent runs: id, stage, status, start, items, error summary. This is the
operational view that D-018's pacing depends on — "how much did we collect today" must be answerable
without reading the JSON log.

## 5. Acceptance criteria (EARS)

- **FR-1** WHEN `gtaf next` runs, THE SYSTEM SHALL print a decision (collect or wait), the chosen
  channel, the limit, and the reason.
- **FR-2** IF videos collected today ≥ daily budget, THE SYSTEM SHALL decide "wait" and SHALL NOT
  propose a channel.
- **FR-3** WHEN under budget, THE SYSTEM SHALL choose the active channel with the fewest stored videos.
- **FR-4** THE SYSTEM SHALL cap the proposed limit at the remaining daily budget.
- **FR-5** WHEN a channel already has zero videos, it SHALL be preferred over a channel with some.
- **FR-6** WHEN `gtaf runs` runs, THE SYSTEM SHALL list recent runs newest-first with status and items.
- **FR-7** THE SYSTEM SHALL NOT write to the database from either command.
- **FR-8** WHEN the daily script sees exit 5 or 4, it SHALL log and exit 0; any other failure SHALL
  propagate its exit code.

## 6. Boundaries

✅ Always: adjust the documented budget when a measurement justifies it; improve a decision message.

⚠️ Ask first: changing the channel-selection rule; running collection without `--skip-existing`; adding
a second scheduled task.

🚫 Never: retry inside the script after a 429; schedule collection while the workbench is in use; run
without `--skip-existing` on a recurring schedule.

## 7. Testing

`tests/test_schedule.py` covers the decision function with a fake connection: wait at budget, choose
least-covered channel, cap the limit, prefer an empty channel, and no writes. The PowerShell entry
script is verified by running it with `-DryRun`, which exercises the decision and prints the command it
would execute without touching the network.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-13
Approved: 2026-11-13 (standing delegation)

### Files created

| Path | Purpose |
|---|---|
| `src/gtaf/application/schedule.py` | `next_batch`, `channel_totals`, `collected_today`, `stale_runs`, `recent_runs` |
| `src/gtaf/cli.py` | `next` (human and `--json`) and `runs` commands |
| `scripts/run_daily_collection.ps1` | Task Scheduler entry point with the exit-code policy |
| `tests/test_schedule.py` | 8 tests including the two defects found below |

### Verification with evidence

```
Claim:     Lint, strict types and tests clean
Command:   ruff check src/ tests/ spikes/ ; mypy ; pytest -q
Summary:   All checks passed ; 32 files clean ; 156 passed
Verdict:   PASS

Claim:     The scheduler picks the least-covered configured channel
Command:   gtaf next
Exit code: 0
Summary:   collect
           reason: Formula has the fewest of the configured channels (0 videos);
                   182 of 200 left today; 1 run(s) left in 'running' state
           channel: formula  limit: 120
Verdict:   PASS

Claim:     Run history is legible
Command:   gtaf runs --limit 3
Exit code: 0
Summary:   topics ok 2355 | collect blocked 0 (429) | collect blocked 0 (429)
Verdict:   PASS

Claim:     The scheduled script produces the right command without collecting
Command:   powershell -ExecutionPolicy Bypass -File scripts/run_daily_collection.ps1 -DryRun
Exit code: 0
Summary:   decision printed; would run: python -m gtaf collect --channel formula
           --limit 120 --skip-existing --log-dir logs
Verdict:   PASS
```

### Two defects found by using the tool, not by testing it

1. **The scheduler picked the best-covered channel.** `channel_totals` read the `channels` table, which
   only contains channels that have been collected — so with five channels at zero videos it chose
   Imedi, the only one with data. Fixed: the population now comes from the **configuration**, with
   counts left-joined from the database. This is the kind of bug a unit test against seeded fixtures
   would have missed, because the fixture had no "configured but absent" case; it is now a test.
2. **A killed run stays `running` forever.** The backfill I terminated left a run row that never
   finalised, so the history claimed a job was still going. `stale_runs` counts rows older than six
   hours and the decision message reports them.

### Deviations from the original spec

1. **`next_batch` takes the configured channel list** rather than reading `channels` — see defect 1.
2. **The task must pass `-ExecutionPolicy Bypass`.** The machine rejects unsigned scripts, so a plain
   invocation fails with "not digitally signed". The registration snippet in the script header and §3
   now include it, and the dry run is verified with that exact form.
3. **`stale_runs` was added** beyond the spec's four acceptance criteria — it exists because the
   operational view was visibly wrong.

### Lessons learned

- A read-only decision function is easy to test and still easy to get wrong: the bug was in *which
  population* it measured, not in the arithmetic.
- Using the feature (running `gtaf next` against real data) found both defects within a minute.
  Neither was reachable from the fixture tests as originally written.

### Next

SPEC-005 (LLM gateway) is now the only P1 blocker for labels and for M4/M5, and it needs API keys.
Until then the scheduled collection can run unattended and the corpus grows daily.
