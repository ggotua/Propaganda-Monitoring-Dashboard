# SPEC-016: Cross-vendor validation

Feature:      Validator — a second vendor checks the first vendor's labels
Priority:     P1 — the gate that makes any model-judged number publishable
Status:       See `SPEC-016.status`
Dependencies: SPEC-005 (gateway), SPEC-013 (stance labels), D-010 (validator must be a different vendor)
Related docs: `G8-VALIDATION.md` · `STANCE-RULES.md`
Tier:         `[SW]` Structured

---

## 1. Overview

D-010 says a validator must come from a **different vendor**, because two models from one vendor share blind
spots and their agreement is not evidence. Until now that rule lived in documents and in one exception class;
this spec makes it executable.

`gtaf validate --target X` asks a second vendor to re-label the same segments independently, then measures
agreement. The measurement is **Cohen's kappa**, not the raw rate, because raw agreement is dominated by the
majority class: two labellers who both answer `unclear` on 90 % of items agree 90 % of the time by
construction and have learned nothing.

### Non-goals

- No human replacement. Kappa between two models says they are consistent, not that they are right; a human
  review (G-8) remains the authority, and cross-vendor agreement is a cheaper first filter.
- No automatic admission: a high kappa does not close G-8 by itself.
- No third vendor (no key available).

## 2. Measures

| Measure | What it answers | Fails by |
|---|---|---|
| agreement rate | "do they say the same thing" | inflation by a dominant class |
| **Cohen's kappa** | "do they agree beyond chance" | small n if a class is rare |
| per-class rate | "is one class systematically wrong" | — |
| disagreements | "where do they differ" | — |

## 3. Acceptance criteria (EARS)

- **FR-1** WHEN primary and validator belong to the same vendor, THE SYSTEM SHALL refuse **before** any call.
- **FR-2** THE SYSTEM SHALL compute kappa from the marginals, not only the agreement rate.
- **FR-3** THE SYSTEM SHALL report per-class agreement.
- **FR-4** THE SYSTEM SHALL list disagreements with their item ids.
- **FR-5** WHEN a validator reply cannot be parsed, THE SYSTEM SHALL count it separately and SHALL NOT score
  it as agreement.
- **FR-6** THE SYSTEM SHALL count only items both labellers covered; an item the validator never saw is not
  a disagreement.
- **FR-7** WHEN the validator vendor refuses for quota, THE SYSTEM SHALL exit with the blocked code and
  explain the constraint, not raise a traceback.

## 4. Boundaries

✅ Always: state the compared count; report kappa beside the rate.

⚠️ Ask first: adding a vendor; treating kappa as a substitute for G-8.

🚫 Never: validate with the same vendor; hide unparsable replies; report a rate without its denominator.

## 5. Testing

`tests/test_validation.py` — eight tests: hand-verified kappa, the degenerate all-one-class case, shared-item
counting, per-class breakdown, disagreement listing, the vendor refusal (asserting no call was made),
unparsable handling, and the empty comparison.

---

## Implementation Status

STATUS: COMPLETE (feature), validated on 3 items only
Implemented: 2026-11-22
Approved: 2026-11-22 (standing delegation)

### Files

| Path | Purpose |
|---|---|
| `src/gtaf/domain/validation.py` | `cohens_kappa`, `compare`, `Agreement` |
| `src/gtaf/application/validation.py` | `validate_stance`, vendor check before any call |
| `src/gtaf/infrastructure/repository.py` | `stance_labels`, `store_validation` |
| `src/gtaf/infrastructure/migrations/006_validation_run.sql` | `validation.run_id` nullable, schema v6 |
| `src/gtaf/cli.py` | `gtaf validate` |
| `tests/test_validation.py` | 8 tests |

### Verification with evidence

```
Claim:     Cross-vendor comparison works end to end
Command:   gtaf validate --target saakashvili --limit 5
Exit code: 0
Summary:   compared 3 | unparsable 2 | agreement 2/3 = 66.7 % | kappa 0.500
           critical 1/1 (100 %), unclear 1/2 (50 %)
           disagreement: 4z1-a8Hhamo:drift:00001500 unclear vs neutral
Verdict:   PASS (mechanism), n=3 is not a measurement

Claim:     Same-vendor validation is refused before calling
Command:   validate_stance(primary=gemini, validator=gemini) in tests
Verdict:   PASS — VendorConflictError, and the fake gateway records no calls

Claim:     Lint, types, tests
Summary:   All checks passed ; 49 files ; 307 passed
Verdict:   PASS
```

### Three defects found by running it

1. **Output truncation.** Gemini's reasoning tokens are drawn from the same budget as the visible reply, so a
   512-token cap cut the JSON mid-object (`{"label": "critical", "confidence": 0.95` with no closing brace).
   The label became unparsable and the validator looked broken. The cap is now **2048**, in both transports
   and in the budget estimate.
2. **The cache held the broken replies.** Sixteen cached Gemini responses were truncated; a retry read them
   back and reported the same failure. They were purged, and the purge script had to be fixed too — it first
   inspected the envelope's last character instead of the `text` field inside it.
3. **`validation.run_id` was NOT NULL.** A cross-vendor check is an ad-hoc audit, not a pipeline run; forcing
   a run row per check would create empty runs. Migration 006 makes it nullable and rebuilds the table.

### The binding constraint is vendor quota, not code

The Gemini free tier allows roughly **11 calls a day** (D-026). A 50-item validation therefore spans about
five days, or needs a paid tier. That is why the live check stopped at **3 compared items**: the number is a
smoke test, not a measurement, and the CLI now exits with the blocked code and says so when quota refuses.

### Next

Run a 50-item validation across several days, or on a paid tier, and compare it with the human G-8 result.
Agreement between **models** and agreement between **a model and a human** measure different things; only the
second closes a gate, and this spec exists to make the first cheap.

### Accumulation (added 2026-11-25)

The free tier gives about eleven calls a day, so a 50-item check cannot happen in one run. Two changes make
it a multi-day accumulation rather than a repeated attempt:

1. **Skip what is already validated.** `validated_segments(validator_model)` filters the candidates, so each
   run adds the next batch. Before this, every run re-checked the same first items and the total never grew.
2. **Store the validator's label** (migration 007, `validation.validator_label`). The earlier table kept only
   a 0/1 flag, which cannot produce kappa or per-class rates. Now the statistic is recomputed from
   **everything** checked so far, so a good day cannot hide a bad one.

```
gtaf validate --target saakashvili --limit 10    # one daily batch, skips the already-checked
gtaf validate --target saakashvili --status      # cumulative agreement, no calls
```

`scripts/run_daily_validation.ps1` wraps the batch and exits 0 on quota (a blocked day adds nothing; it is not
a failure). It is **not registered** as a scheduled task — that stays the user's decision, like the
collection task.

### A fourth defect: thinking tokens truncate the reply even at 2048

After raising the cap to 2048, replies were **still** truncated: Gemini's reasoning tokens come out of the same
budget, and a 2,000-character Georgian prompt can spend nearly all of it on thinking. The fix is not a bigger
cap but `thinkingConfig: {thinkingBudget: 0}` — this task needs a label and a verbatim quote, not reasoning.
Measured after the change: **1 compared, 0 unparsable**, where the same call had been unparsable minutes
earlier. Eleven stale truncated replies were purged from the cache again.

### First real accumulation (2026-11-26, task run)

The registered task ran and added ten items in one pass:

```
gtaf validate --target saakashvili --status
Saakashvili cumulative (gemini-3-flash-preview): 8/11 = 72.7 % | kappa 0.535
critical  4/5 (80.0 %)
unclear   4/6 (66.7 %)
```

Two things follow.

**The mechanism works.** One scheduled run took the total from 1 to 11 without repeating anything, and the
cumulative figure came from storage rather than from that run alone.

**Cross-vendor agreement is lower than human agreement.** The reviewer agreed with DeepSeek on **84 %** of
50 rows overall (91 % on `critical`); Gemini agrees with DeepSeek on **72.7 %** of 11, with kappa 0.535 —
"moderate" at best. The gap is concentrated exactly where the reviewer complained: `unclear` (66.7 %).
That is the same boundary he called arbitrary, now showing up as vendor disagreement. Two models agreeing
poorly on `unclear` is evidence that the **label definition** is weak, not that one model is wrong.

Sample size is 11: this is a direction, not a result. The task adds ~10 a day, so the 50-item comparison
against the human check arrives in about four more days.
