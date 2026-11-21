# G-8 validation record — stance labelling

Status: **FAILED** (2026-11-21). The gate required agreement ≥ 0.80 over 50 reviews; the review found
**at least 19 rejected rows (≤ 0.62)** and, more importantly, **five distinct failure classes**, three of
which no threshold could have fixed.

Reviewer: George. Sample: 50 rows from `gtaf stance --target saakashvili --export-sample 50`
(prompt `stance-v1`, DeepSeek).

## Result

| Outcome | Count |
|---|---|
| Rejected | **≥ 19** |
| Agreement | **≤ 0.62** |
| Gate threshold | 0.80 → **FAILED** |

The exact count is uncertain because the rejections overlap; the upper bound is 31/50, which is already
below the bar. No arithmetic could rescue it, and the classes matter more than the percentage.

## The five failure classes

### 1. Hostile context read as a verdict on the target (the largest class)

Twelve `critical` labels were rejected; **nine do not criticise Saakashvili himself**. They criticise
someone connected to him and name him only for identification:

- his uncle, Temur Alasania (#5);
- "a leading figure of Saakashvili's team" (#47);
- Zodelava (#48);
- the UNM as a party (#28, #39);
- a defence minister of his era (#29);
- the EU ambassadors' démarche (#27).

**The model reads a hostile setting as a judgement on the person named inside it.** This is the failure
that matters most, because it inflates exactly the figure the analysis wants.

### 2. Wrong person in the corpus — an upstream defect, not a model error

Rows **#3, #30, #37** are about **Mikheil Kavelashvili**, the president addressing COP31 in Antalya in
November 2026 — not Saakashvili. Inspected directly: the segment text contains the literal string
`მიხეილ სააკაშვილი`:

> პრეზიდენტი დღეს ანტალიაში გაემგზავრება … **მიხეილ სააკაშვილი** კონფერენციის მონაწილეებსა და
> მსოფლიო ლიდერებს სიტყვით ხვალ, 11 ნოემბერს მიმართავს.

The president in 2026 is Kavelashvili; the caption says Saakashvili. **The ASR substituted a famous
surname for a similar one.** That is a corpus defect, and it has a consequence beyond this feature:

> **G-5 validated that the matcher finds the name in the text. It did not validate that the name was
> said on air.** A familiar surname can be substituted for an unfamiliar one precisely because it is
> familiar, so mention counts of famous figures are the most exposed to this inflation.

This cannot be fixed by thresholds. It requires either a second signal (title/office agreement) or human
checking of the high-stakes names.

### 3. The same text receives different labels

Papuashvili's list of cases is `neutral` in #11, `critical` in #13 and `unclear` in #36; the "simulating"
passage is `critical` in #19 and `unclear` in #22 with a meaningless rationale.

Cause: prompt v1 truncated the segment at 800 characters, so the same passage arrived with different
surrounding context and the model answered the context, not the passage.

### 4. Invented rationales

#6, #27 and #34 quote words that are not in the segment. #25 and #50 claim the person is not mentioned
when he is.

A stated reason that the source does not contain makes the label **unreviewable**, and spot-checking a
rationale cannot establish whether a label is right.

### 5. `neutral` and `unclear` have no boundary

Mentions with no evaluation get either label. #42 is labelled `neutral` but is mildly dismissive.

## What was changed in response

Prompt v2 (`stance-v2`) and a stricter contract, all measured:

| Change | Reason | Verifiable effect |
|---|---|---|
| Explicit-target rule: hostility toward an associate is **not** the target's evaluation | failure class 1 | not yet measurable — needs a new review |
| `neutral` and `unclear` defined by what the text does | failure class 5 | — |
| Verbatim `quote` required, then **checked against the segment** | failure class 4 | **30/30 quotes verified** in the first v2 run |
| Prompt text raised from 800 to 2,000 characters | failure class 3 | — |

First v2 run on the same 30 segments:

```
labelled 30 | unparsable 0 | quote verified 30/30 | cost $0.016
supportive  0   0.0%    critical  9  30.0%    neutral  3  10.0%    unclear 18  60.0%
```

Against v1's `critical 71.3 % / unclear 13.9 %` on the same corpus. **The direction is right** — v1
over-called critical exactly as the review found — but **60 % unclear may now be an over-correction**, and
only a human reading of the same 50 segments can tell. v2 is therefore **not** an improvement by
measurement yet; it is a fix with a plausible mechanism and a different bias.

## Standing consequences

1. **G-8 remains OPEN.** Stance may not appear in a report.
2. **G-5's meaning is narrower than recorded.** Mention counts are "the name appears in the text", not
   "the person appeared on air". `G5-VALIDATION.md` and `ANALYTICAL-POLICY.md` now say so.
3. **Any stance claim must state the labelled denominator and the `unclear` share**, and no stance number
   may be presented without a review of the current prompt version.
4. **A new review is required for `stance-v2`**, over a fresh sample, before the next attempt at the gate.
