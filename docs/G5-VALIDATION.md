# G-5 validation record — actor matching

Status: **PASSED with a narrower meaning than recorded**, 2026-11-21. The 0.96 agreement stands, but the
G-8 review of the next day showed what it does not cover: the matcher finds the name **in the text**, and
the text itself can be wrong. Three reviewed segments about President Kavelashvili address COP31 contain
the literal string `მიხეილ სააკაშვილი` — the ASR substituted a famous surname. Mention counts are
therefore "the name appears in the text", not "the person appeared on air". See `G8-VALIDATION.md` §2.

## What was checked

A deterministic, method-stratified sample of **50 mentions** produced by `gtaf actors --spot-check 50`
(`reports/g5-spot-check.md`): every fuzzy match in the corpus (4) plus a seeded random draw of 46 from the
328 exact and ending matches. Each row was read by **George** — the person who owns the corpus and the
language — who marked it correct or not.

## Result

| Outcome | Count |
|---|---|
| Correct (the segment really mentions that person) | **48** |
| Wrong | **2** |
| **Agreement** | **0.96** (48/50; Wilson 95 % CI ≈ 0.87 – 0.99) |
| Gate threshold | 0.80 → **PASSED** |

The lower bound of the interval is still above the threshold, so the pass does not depend on the point
estimate: even the pessimistic reading clears 0.80.

## The two errors, and what they were

Both were the **same** false positive, and it is the most instructive failure this feature can have:

| Row | Matched | Reality |
|---|---|---|
| 10 | `პაპაშვილი` → Papuashvili (parliament speaker) | `თამარ პაპაშვილი`, a **weather presenter** |
| 41 | `პაპაშვილი` → Papuashvili (parliament speaker) | same person, different segment |

Two **different real people**, one deleted `უ` apart: `პაპაშვილი` versus `პაპუაშვილი`. The matcher treated
the deletion as ASR noise and merged a broadcaster's weather slot into the speaker's count.

A third issue was **not** a matching error: row 17 rendered `მახაშვილი` as "Makashvili"; the correct
transliteration is **Makhashvili**. That is a label defect in `config/actors.yaml`, fixed there.

## Fixes applied after the check

1. **`FUZZY_PREFIX = 4`** — a fuzzy match now requires the first four characters to be identical. The
   deleted `უ` sits inside that prefix, so the pair is no longer merged. A test pins this
   (`test_papashvili_is_not_papuashvili`).
2. **Transliteration corrected**: `მახაშვილი` → `Makhashvili`.

Effect on the corpus: Papuashvili 53 → **51** segments (the two false positives removed); total actor
mentions 332 → **330**; fuzzy matches needing review 4 → **2**, both correct on inspection.

## What this authorises

Per `ANALYTICAL-POLICY.md` G-5 and G-6, the following may now be published, provided each figure carries
its denominator, method version and date span:

- that a named person is **mentioned** in a number of segments of the analysed slice;
- comparisons of mention counts **within** one channel and one period.

## What it does not authorise

- **Speaking.** A mention is not a statement. "X said" requires speaker attribution, which this corpus
  does not have beyond `>>` turn markers.
- **Airtime, sentiment, framing.** None of those are measured yet.
- **Cross-channel or trend claims** — G-3 and G-4 still fail (one channel, 11 days).
- **Completeness.** 330 is a **lower bound**: a person outside the 15-entry dictionary is invisible.

## Method note — this check is not reusable as a certificate

The fixes were made **after** seeing the 50 rows. That is the correct engineering response, but it means
the 0.96 belongs to the *version that produced the sample*, not to the current build. The current build has
not been measured; its false-positive rate is lower by construction (two defects removed, nothing loosened),
but "lower by construction" is a claim, not a measurement.

**Re-run a fresh 50-mention sample** (new seed) before the next report that cites names, and again whenever
the dictionary grows by more than a few entries — every added name introduces new collision surface.
