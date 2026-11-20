# SPEC-013: Stance toward a named person

Feature:      Stance labelling of segments
Priority:     P2 — the first LLM-derived analytical layer
Status:       See `SPEC-013.status`
Dependencies: SPEC-005 (gateway), SPEC-011 (actor mentions), G-5 (a mention may be named)
Related docs: `ANALYTICAL-POLICY.md` G-8 · D-028 (WER) · D-029
Tier:         `[SW]` Structured

---

## 1. Overview

For each segment that mentions a known actor, ask a model how that text frames them: `supportive`,
`critical`, `neutral`, or `unclear`. Store the label, the confidence and a one-line rationale.

This is the first feature whose output is a **judgement** rather than a count, which changes the risk
profile. A dozen false positives in actor matching produce a wrong number; a systematic labelling bias
produces a wrong *story* — "the channel is hostile to X" — that looks like evidence.

Three design choices follow from that:

1. **`unclear` is a first-class label**, offered first in the prompt. If the text does not evaluate the
   person, the model must say so rather than pick a side; measurable opinion is better than forced opinion.
2. **An unreadable reply is never coerced.** "The model replied with prose" and "the model found
   neutrality" are different facts; merging them would inflate the most comfortable label.
3. **Nothing is publishable until a human checks a sample** (G-8, below). The CLI prints the warning on
   every run, not in a document somewhere else.

### Non-goals

- No speaker attribution: the label describes the **segment's framing**, not what a named person said.
- No intensity beyond the confidence the model reports.
- No aggregation across channels or over time — the corpus cannot support either (G-3, G-4).

## 2. Labels

| Label | Meaning |
|---|---|
| `supportive` | The text presents the person positively |
| `critical` | The text presents them negatively |
| `neutral` | The text mentions them without evaluation |
| `unclear` | The text does not evaluate them, or cannot be read — **a real answer, not a failure** |

## 3. Acceptance criteria (EARS)

- **FR-1** WHEN a segment does not mention the target, THE SYSTEM SHALL NOT send it.
- **FR-2** WHEN a reply cannot be parsed, THE SYSTEM SHALL count it as unparsable and store nothing.
- **FR-3** WHEN a reply carries a label outside the set, THE SYSTEM SHALL treat it as unparsable.
- **FR-4** THE SYSTEM SHALL store segment, target, label, confidence, model, prompt version, rationale and
  timestamp.
- **FR-5** THE SYSTEM SHALL replace a previous label for the same (segment, target, model, prompt version).
- **FR-6** THE SYSTEM SHALL report the labelled count as the denominator and show every label, including
  zeros.
- **FR-7** THE SYSTEM SHALL print a non-publishable warning naming the gate that blocks publication.
- **FR-8** Re-running with the same prompt version SHALL cost nothing (gateway cache).

## 4. Boundaries

✅ Always: keep `unclear`; store rationales; state the denominator.

⚠️ Ask first: changing the label set; publishing any distribution; raising `limit` above a few hundred.

🚫 Never: coerce a parse failure to `neutral`; call a segment's framing a speaker's position; report a
stance share without the labelled denominator.

## 5. Gate G-8 (new)

Stance shares may be published only when a human has checked ≥ 50 labelled segments and agreement is
≥ 0.80, on a sample that includes the model's `critical` and `unclear` verdicts. Until then the numbers are
candidates. **G-8 is currently OPEN.**

---

## Implementation Status

STATUS: COMPLETE (feature), gate OPEN
Implemented: 2026-11-20
Approved: 2026-11-20 (standing delegation)

### Files

| Path | Purpose |
|---|---|
| `src/gtaf/infrastructure/migrations/004_stance.sql` | `stance` table, schema v4 |
| `src/gtaf/domain/stance.py` | labels, prompt, strict parser, zero-inclusive summary |
| `src/gtaf/application/stance.py` | selection, gateway calls, storage |
| `src/gtaf/infrastructure/repository.py` | `store_stance`, `stance_counts` |
| `src/gtaf/cli.py` | `gtaf stance --target --limit --provider` |
| `tests/test_stance.py` | 13 tests |

### Verification with evidence

```
Claim:     A live pass labels segments and reports its own limits
Command:   gtaf stance --target saakashvili --limit 30 --provider deepseek
Exit code: 0
Summary:   segments mentioning them: 30 | labelled: 30 | unparsable: 0 | cost $0.011016
             supportive   0   0.0%
             critical    18  60.0%
             neutral      4  13.3%
             unclear      8  26.7%
Verdict:   PASS (feature), NOT PUBLISHABLE (gate)

Claim:     Lint, types, tests
Command:   ruff check ; mypy ; pytest -q
Summary:   All checks passed ; 45 files ; 272 passed
Verdict:   PASS
```

### What the first run suggests, and why it is not a finding

60 % `critical` for Saakashvili on Imedi is a plausible number for a government-aligned channel, and that
plausibility is the danger: it is exactly the result a reader will accept without checking. It remains a
model's reading of ASR text with 26.7 % `unclear`, on 30 of 108 mentioning segments, with no human
agreement measured. The next step is a 50-segment human check (G-8), not a chart.

### Next

`gtaf stance --export-sample` (G-8 review file), then the validator pass; only after that may the report
gain a stance section, and it must state the labelled denominator and the `unclear` share beside it.
