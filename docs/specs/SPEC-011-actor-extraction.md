# SPEC-011: Actor extraction — dictionary first, measurement always

Feature:      Actor mentions over segments
Priority:     P1 — M2 needs to know who is mentioned, and the ASR cannot be trusted with names
Status:       See `SPEC-011.status`
Dependencies: SPEC-003 (sentences), SPEC-006 (drift segments), D-028 (measured WER)
Related docs: `docs/ACTORS.md` · `ANALYTICAL-POLICY.md` G-5
Tier:         `[SW]` Structured

---

## 1. Overview

Every caption in this corpus is automatic, and D-028 measured **12.3 % WER** with the failures
concentrated exactly where this feature works: `დიჰმის` for `დირჰამის`, `ეშალოვნები` for
`ეშელონებიდან`, and surnames split across tokens. A general NER model would produce confident output
nobody can audit; a **dictionary plus explicit matching rules** produces output whose failures are
visible, countable and fixable.

The dictionary is small (15 public figures) and that is a feature, not an oversight: every entry is a
claim that this person is worth tracking, and the list grows only when a report needs a name.

### Non-goals

- No general NER: no attempt to find unknown persons. An unknown person is invisible rather than
  invented, which is the correct failure for an analytical claim.
- No coreference, no titles ("the president"), no organisations — persons only, for now.
- No speaker attribution. Matching a name in a segment says the segment mentioned them; it does not say
  they spoke, and the report must never imply otherwise.

## 2. Matching rules (and why each exists)

| Rule | Reason |
|---|---|
| One case ending stripped from the dictionary form | Georgian nouns inflect: `სააკაშვილი` / `სააკაშვილს` / `სააკაშვილმა` are one person |
| 21 endings tried, longest first | The ergative `-მა/-ემ/-ამ` is the most common form in speech |
| Fuzzy matching only from 7 characters | Below that, `მელია` matched `მედია` ("media"), `მერია` ("city hall") and `მეტია` ("more") |
| At most 2 edits from 9 characters, 1 from 7–8 | `გააცრია` ("sifted") is 2 edits from `გახარია`; a real slip `სააკაშველი` is also 2 edits but on a 9-character stem |
| Similarity ≥ 0.80 as a second condition | An edit cap alone admits unrelated words that happen to pass the length test |
| One mention per actor per segment | The unit is "did this segment mention X", not frequency: segment length inflates counts without information |

## 3. Acceptance criteria (EARS)

- **FR-1** WHEN a token equals the dictionary form, the stem, or stem plus a known ending, THE SYSTEM
  SHALL record a mention with method `exact` or `ending`.
- **FR-2** WHEN a token differs by at most the allowed edits and clears the similarity floor, THE SYSTEM
  SHALL record a mention with method `fuzzy`.
- **FR-3** WHEN a surname is shorter than 7 characters, THE SYSTEM SHALL NOT use fuzzy matching.
- **FR-4** WHEN a token is institutional vocabulary (a stopword), THE SYSTEM SHALL NOT match it.
- **FR-5** WHEN an actor is mentioned several times in one segment, THE SYSTEM SHALL count one mention.
- **FR-6** WHEN the scan runs, THE SYSTEM SHALL report the denominator, the fuzzy count, and a
  non-publishable warning — no count reaches a report without the G-5 check.
- **FR-7** WHEN `--audit N` is passed, THE SYSTEM SHALL print up to N fuzzy mentions with their matched
  token, ratio and segment text, because fuzzy matches are the only ones a human needs to review.
- **FR-8** WHEN the dictionary is missing or empty, THE SYSTEM SHALL fail rather than return an empty scan.

## 4. Boundaries

✅ Always: audit fuzzy matches before citing a count; add an ending rather than loosening the ratio.

⚠️ Ask first: enabling fuzzy matching below 7 characters; adding a name that no report mentions.

🚫 Never: present these counts as findings (G-5 is open); infer that an actor spoke; treat a directory
count as airtime.

## 5. Calibration record

The thresholds were set by audit, not by taste. Each iteration was run on the real corpus and the false
positives are named:

| Iteration | Rule | Fuzzy matches | What was wrong |
|---|---|---|---|
| 1 | ratio ≥ 0.84, no length floor | 62 | `გააცრია` → `გახარია`; `მდინარე` → `მდინარაძე` |
| 2 | ratio ≥ 0.92 | 0 | recall collapsed: real slips and dropped endings rejected |
| 3 | ratio ≥ 0.90, edits by length | 6 | `გიხარია` ("I'm glad") → `გახარია` |
| 4 | + locative endings, `-ა`, floor at 7 chars | **4** | all four reviewed and correct |

The lesson is in iteration 2: a single similarity threshold cannot separate typo from different word,
because a dropped ending and a common noun can score the same. Length plus edit distance can.

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-20
Approved: 2026-11-20 (standing delegation)

### Files

| Path | Purpose |
|---|---|
| `config/actors.yaml` | 15 seeded public figures, format documented in `docs/ACTORS.md` |
| `src/gtaf/domain/actors.py` | stemming, 21 endings, edit-distance + ratio matching |
| `src/gtaf/application/actors.py` | scan, per-actor stats, fuzzy audit sample |
| `src/gtaf/cli.py` | `gtaf actors --top --audit` |
| `tests/test_actors.py` | 25 tests |

### Verification with evidence

```
Claim:     Mention counts over the corpus, with the review workload named
Command:   gtaf actors --top 10 --audit 8
Exit code: 0
Summary:   drift | 4,837 segments analysed | 332 mention a known actor (6.9%)
           Saakashvili 108 (2.2%), Kobakhidze 94 (1.9%), Papuashvili 53 (1.1%)
           fuzzy matches needing review: 4 — all four correct on inspection
Verdict:   PASS

Claim:     Lint, types, tests
Command:   ruff check ; mypy ; pytest -q
Summary:   All checks passed ; 41 files clean ; 235 passed
Verdict:   PASS
```

### What this does not do

It does not make the counts publishable. G-5 still requires a 50-mention spot check at agreement ≥ 0.80,
and the fuzzy workload is only 4 of 332 — so the check will be about the **ending** and **exact** matches,
which are the vast majority. A person who is not in the dictionary is invisible, so these are lower bounds.
