# G-8 validation record — stance labelling

Status: **CONDITIONAL PASS** (v2, 2026-11-21) — 42/50 = **0.84** overall, above the 0.80 bar, but two label
classes are too small to judge and one is contaminated by the corpus defect fixed afterwards.

- **v1:** 33/50 = 0.66 → **FAILED** (five failure classes, §v1 below)
- **v2:** 42/50 = 0.84 → **CONDITIONAL PASS** (§v2 below)
- **Targeted check of `neutral` and `supportive`:** **not yet run** — files produced, see §"Still open"

Reviewer: George. He applied the same standard to both versions, and reports that five calls were
borderline: if every one had gone against the model, v2 would be 41/50 = 0.82 — the overall verdict holds
either way.

## Result

| Outcome | Count |
|---|---|
| Rejected | **≥ 19** |
| Agreement | **≤ 0.62** |
| Gate threshold | 0.80 → **FAILED** |

The exact count is uncertain because the rejections overlap; the upper bound is 31/50, which is already
below the bar. No arithmetic could rescue it, and the classes matter more than the percentage.

## v2 result — 42/50 (0.84), conditional

| Class | Agree | Rate | v1 rate |
|---|---|---|---|
| `critical` | 21 / 23 | **91 %** | 66 % |
| `unclear` | 20 / 23 | **87 %** | — |
| `neutral` | 1 / 3 | 33 % | — |
| `supportive` | 0 / 1 | **0 %** | — |
| **Overall** | **42 / 50** | **84 %** | 66 % |

**What improved.** The explicit-target rule worked. The rows v1 wrongly called `critical` are now `unclear`,
correctly: the Alasania and Zodelava rows, the UNM-as-a-party rows, the ambassadors' démarche, and the list
of court cases. That list also receives one consistent label now.
Key finding: **the model can be steered away from a systematic error by a stated rule**, which is the most
encouraging result so far in this project.

**Why it is only conditional.**

1. **Two classes are too small to judge.** `neutral` has 3 rows, `supportive` 1. "No class clearly broken"
   cannot be claimed for either, and the bar is by class as well as overall.
2. **The only `supportive` label is wrong.** #12 is the UNM defending itself in the Constitutional Court,
   saying his role as party chairman was "minimal" — the party disowning him, which the reporter frames as
   such. The same content is `neutral` in #31. So `supportive` is **untested and currently 0 correct**.
3. **The model now over-corrects toward `unclear`.** #2, #23 and #27 carry mild criticism — rejecting his
   November 7 justification, "if it can even be called an idea", the "227 Strasbourg violations" framing.
4. **Rationales still invent.** #11 claims the text calls him a "psychopath"; #25 and #48 quote words absent
   from their segments. The labels on those rows are fine, but their stated evidence cannot be used.

## Targeted check of `neutral` and `supportive` — Kobakhidze (2026-11-22)

Reviewer: George. 30 rows, `neutral` 21 + `supportive` 9, under `stance-v2`.

| Class | Agree | Rate |
|---|---|---|
| `neutral` | 20 / 21 | **95 %** (20/20 excluding one empty row — see note) |
| `supportive` | 8 / 9 | **89 %** |
| **Overall** | **28 / 29** | **97 %** |

Rejected: **#1**, labelled `supportive` but a plain report of his Dublin speech — the same text as #10,
which is correctly `neutral`; its rationale again cited content the segment does not contain ("criticism
called unfair", "readiness for dialogue"). Borderline **#15** accepted: the outlet repeats his line as fact
and says "our government", which endorses his position without praising him — accepted to stay consistent
with how mild criticism was treated for Saakashvili.

**Note on #30:** reported as having no segment text. The stored row is intact (8 cells, text present); the
likely cause is a viewer truncating a very long last cell. Cells are now capped at 300 characters so a row
cannot be clipped, and the near-duplicate check below was added in the same pass.

### The critical class is untested for an incumbent, and this sample proves it

The model gave **none** of these 30 rows `critical`. Across the whole corpus, under v2:

| target | critical | neutral | unclear | supportive |
|---|---|---|---|---|
| Kobakhidze (PM, incumbent) | **1 / 94 (1.1 %)** | 64 | 5 | 24 |
| Saakashvili (ex-president, opposition) | **46 / 90 (51 %)** | 0 | 44 | 0 |

Two explanations fit, and **this corpus cannot separate them**:

1. **The channel.** The only channel collected is **Imedi**, a government-aligned broadcaster. Its coverage
   of the prime minister may genuinely contain almost no criticism.
2. **The model.** It may read criticism of an incumbent as `unclear` or `neutral` — exactly the failure
   direction that would bias a government-versus-opposition comparison. The Saakashvili results show it
   handles `critical` well when the target is in opposition.

That is why this is **not** a clean pass for Kobakhidze: the "no class clearly broken" condition cannot be
met when the class is absent from the sample.

**The decisive test is blocked by data, not by code.** Opposition channels (Formula, TV Pirveli) are
configured in `config/channels.yaml`, but collection is still backing off from the caption-endpoint block
(D-024): `gtaf next` reports *next attempt after 2026-11-25 02:47 UTC*. Until those channels exist, no
review can distinguish channel bias from model bias.

## Contamination found by the reviewer, and what it revealed

#7, #29 and #38 are **Kavelashvili at COP31**, not Saakashvili. After applying the D-031 title/role guard
and re-running, the class distribution changed materially:

| | before guard | after guard and purge |
|---|---|---|
| `critical` | 46 | 46 |
| `unclear` | 44 | 44 |
| `neutral` | 7 | **0** |
| `supportive` | 1 | **0** |

**The `neutral` class was almost entirely contamination** — the COP31 segments were the neutral ones. Two
consequences: the v2 `neutral` rate of 1/3 measured contaminated data, and Saakashvili currently has **no
neutral and no supportive labels at all**, so those classes cannot be assessed on this target.

## Targeted check, ready to run

Because the rare classes cannot be judged on Saakashvili's own coverage, candidates were pulled from a
second target. Kobakhidze (prime minister) under v2:

```
94 segments: supportive 24 (25.5%) | neutral 64 (68.1%) | critical 1 | unclear 5
```

Files for review:

- `reports/g8-targeted-kobakhidze.md` — 30 rows, `neutral` 21 + `supportive` 9;
- `reports/g8-targeted-saakashvili.md` — **0 rows**, which is itself the finding: after the purge this
  target has no neutral or supportive labels to check.

The 25.5 % supportive share for the prime minister is **suspicious in the opposite direction**: a
government-aligned channel reporting the prime minister's own statements may read as "supportive" when it
is simply attribution. That is what the targeted review is for.

## Rules written down before the next round

`docs/STANCE-RULES.md` records the decisions the reviewer asked for — reported speech (#41, #44), blame
aimed at his government (#18, #19), a party disowning him (#12), and how to treat a quote that cannot be
found. They apply to the next labelling round; the v2 measurement above stands under v2's prompt.

## Still open (v1 section, kept for the record)

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
