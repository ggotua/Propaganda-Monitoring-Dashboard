# ANALYTICAL-POLICY — what this data may and may not be used to claim

Status: **in force** from 2026-11-13 (D-023). This document is deliberately numeric: every gate is a
threshold that either passes or fails, because "be careful with small samples" is not a rule anyone can
apply at 6pm before a deadline.

It exists because the pipeline now produces plausible-looking figures on a corpus that cannot support
most claims: **263 videos, 1 channel, 11 days, 38.6 % unclassified.** Without gates, the first chart
someone likes becomes the finding.

---

## 1. Gates

| # | Gate | Threshold | Why this number |
|---|---|---|---|
| G-1 | Publish a topic **share** | ≥ **30 segments** in the cell | Below 30, one segment moves the share by ≥3.3 points; report the count, not a percentage |
| G-2 | Publish a topic **ranking** | outlier rate ≤ **50 %** in that slice | Above half unclassified, a ranking describes a minority of the corpus; publish coverage only |
| G-3 | **Compare two channels** | each channel ≥ **14 days** and ≥ **100 videos** | A week of one channel is a news cycle, not an agenda |
| G-4 | Claim a **trend** | ≥ **3 complete reporting windows** (6 months at the bimonthly cadence, D-003) and one method version | Two periods is a line between two points; three is the minimum shape |
| G-5 | Name an **actor** or attribute a statement | NER agreement ≥ **0.80** on a 50-mention spot-check **and** caption WER ≤ **30 %** | ASR mangles exactly the proper nouns an entity claim depends on (`ASR-QUALITY.md`) |
| G-6 | Publish **any** number | denominator + outlier rate + date span + channel count + method version travel with it | A number without its scope is not reproducible and invites the wrong comparison |
| G-7 | Publish **proportions** | never renormalised to 100 % unless the excluded share is stated in the same sentence | 61 % of segments are placed; a "61 %-normalised" chart silently hides the rest |
| G-8 | Publish any **model-judged label** (stance, framing) | human agreement ≥ **0.80** on ≥ 50 labelled items, including the model's `critical` and `unclear` verdicts | a judgement can be systematically biased in a way a count cannot; plausibility is not agreement |

## 1a. Gate status as measured (2026-11-20)

| Gate | Status | Evidence |
|---|---|---|
| G-5, WER half | **PASSES** | 12.3 % WER / 4.3 % CER, 373 words, and that is an *upper bound* because the reference was an edited article (D-028) |
| G-5, entity half | **PASSES** (0.96, n=50) | 48/50 correct; Wilson 95 % CI ≈ 0.87–0.99, above the 0.80 bar. Two false positives (same pair of distinct people) fixed afterwards — see `G5-VALIDATION.md` |
| G-8, stance/framing labels | **OPEN** | first pass exists (30 segments, 26.7 % `unclear`) but no human agreement measured; nothing may be published until it is |
| G-1, G-2 | fail on current data | 38.2 % unclassified; largest topic 5.5 % of 4,837 segments |
| G-3, G-4 | fail on current data | one channel, 11 days; no trend possible |

WER is measured on **clean narration**. The stratified re-measurement (hearing, street) is pending and
matters because bad audio correlates with the confrontational content this project studies (D-028).

## 2. What may be claimed today (2026-11-20)

**May be claimed:**

- the pipeline works end to end and is reproducible;
- on Imedi, 3–13 November 2026, the topic model found **62 clusters over 4,837 drift segments**, with
  **38.2 %** unclassified and the largest cluster at **5.5 %** of segments;
- Georgian YouTube auto-captions were available for 99 of 99 sampled videos and **manual captions for
  none**, with a measured **WER of 12.3 %** on one clean-narration clip (an upper bound);
- ~69 % of titles cannot be attributed to a programme from the title alone.

**May not be claimed:**

- that any channel gives more airtime to any topic than another (G-3 fails: one channel);
- that any topic is rising or falling (G-4 fails: 11 days);
- that any named person is portrayed a given way (G-5 fails: no NER, WER unmeasured);
- that "X % of coverage" is a property of Georgian television (one channel, 11 days, 38.6 % unplaced).

## 3. Banned phrasings

These sentences are wrong even when the underlying number is right:

| Never write | Because | Write instead |
|---|---|---|
| "X causes Y" | associational data only | "X co-occurs with Y" |
| "the channel supports the government" | intent is not observable | "the segment frames the government's position as…" |
| "proves" / "demonstrates" | a single cluster is not proof | "is consistent with" |
| "X % of viewers" | we measure output, not reach | "X % of analysed segments" |
| "the main topic" without a denominator | share of what? | "the largest topic, at X % of Y segments" |

## 4. Multiple comparisons

The current design is **descriptive**: proportions with denominators, no significance tests. If a test is
ever run — subgroup differences, correlation between channels — it must be:

1. **pre-specified** in a SPEC before running;
2. reported with the number of tests performed and a correction;
3. labelled exploratory if it was not pre-specified.

## 5. Escalation

If a decision needs a claim that fails a gate, the answer is not to lower the gate. It is one of:

- collect more data (the schedule grows the corpus daily);
- narrow the claim to what the data supports;
- state the limitation in the same sentence as the number.

Changing a threshold requires a new entry in `docs/steering/decisions.md` — never a quiet edit here.
