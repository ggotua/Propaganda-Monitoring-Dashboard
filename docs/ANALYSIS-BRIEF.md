# Georgian TV Agenda & Framing — Analysis Brief

**Version:** 1.0
**Date:** 2026-11-12
**Status:** `approved` — see [ANALYSIS-BRIEF.status](ANALYSIS-BRIEF.status). The `.status`
file is what authorises implementation; approved by the agent on 2026-11-12 under George's
explicit delegation of architectural decisions, §2 and §3 read against `APP-OVERVIEW.md` §2–§4.
**Analyst:** George
**System:** GTAF (Georgian TV Agenda & Framing) — see [APP-OVERVIEW.md](../APP-OVERVIEW.md)
**Rigor tier:** `[DA]`/`[ML]` = Formal SDD-DA; `[SW]` = Structured SDD-V2
([D-001](steering/decisions.md))

---

## 1. Background & Context

Six Georgian broadcasters — Imedi, Rustavi 2, POSTV, GPB (First Channel), Formula and TV
Pirveli — publish evening news and political talk content on YouTube. The archive begins
2026-10-01 and grows daily; a report is produced **every two months, six per year**
([D-003](steering/decisions.md)), for an audience of experts, activists, politicians and
diplomats.

The question this project answers is not "what is propaganda?" but the narrower and
checkable one: *what does each channel choose to cover, how much, and in what terms —
and how do those choices differ between channels and move over time?* The unit of
evidence is the segment of a broadcast carrying captions; the unit of comparison is the
channel-week.

---

## 2. The Core Question

**Primary (agenda — first deliverable).** For each channel, what topics are covered, in
what volume, and when? Specifically: what share of a channel's news segments is given to
each topic per week, and how does that share differ from other channels covering the same
week?

**Secondary (framing).** For the most prevalent topics, in what terms are they framed —
who is cast as the problem, its cause, the moral judgement, the remedy — and does that
framing differ systematically by channel?

**Tertiary (narratives over time).** Which recurring narratives appear, how long do they
persist across channels, and do they spread from one channel to others?

The order is a dependency order, not a preference: framing cannot be compared until
agenda tells us which topics are prevalent enough to compare, and narrative persistence
cannot be measured until frames are stable enough to recognise across weeks.

---

## 3. Non-Goals

Explicitly excluded from this analysis — each a deliberate boundary, not an oversight:

- **No causal claims.** Nothing here establishes that a broadcast changed anyone's belief.
  All findings are descriptive and associational, and must be labelled as such.
- **No channel "ratings" or ranking of propagandisticness.** No composite score that
  places the six channels on a single axis of badness.
- **No claims about intent.** The analysis describes what was said and how; it does not
  infer why an editorial decision was made.
- **No speaker-level attribution.** Captions carry no speaker labels; the analysis must not
  present a statement as "said by X" unless the text itself names X in a reported clause.
- **No viewer-level or reach analysis.** Views, likes and audience demographics are out of
  scope; this measures output, not consumption.
- **No channels beyond the six**, and no online-only outlets (APP-OVERVIEW §4).
- **No archive before 2026-10-01.**
- **No video or audio analysis.** Captions only; never frames of video, never voice tone.

---

## 4. Data Description

**MEASURED 2026-11-12** — 99 videos sampled across all six channels; full method, tables and
caveats in [FEASIBILITY.md](FEASIBILITY.md). Every figure below is a count from
`data/feasibility/captions.csv`, not an estimate.

| Property | Measured value |
|---|---|
| Caption availability | **99 of 99 sampled videos captioned** — 0 uncaptioned in any channel × type cell |
| Caption kind | **100 % automatic, 0 % manual.** No human-authored caption track was offered anywhere |
| Caption language | Georgian (`ka`) on all 99; no English track observed |
| Captioned volume | 104,258 s = **29.0 hours** across 99 videos |
| Duration spread | bulletins median **17.8–37.5 min**; talk 8–11 min; **minimum 1.4 min**, maximum 130 min (live stream) |
| Date coverage of the sample | 13 distinct dates, 2026-10-01 … 2026-11-12; 90 of 99 in November |
| Programme attribution from titles | **464 titles matched no configured programme** (≈69 % of those examined) |
| Channels with a usable programme marker | Imedi (ქრონიკა), Rustavi 2 (კურიერი, შუადღე), GPB (მოამბე, partially) |
| Channels without one | TV Pirveli (bare headlines), Formula (no in-window classified video) |
| Blocked videos | 1 age-restricted (Imedi); skipped, not a channel-level block |

Three consequences follow directly, and they shape §5 rather than sitting as trivia:

1. **No channel needs to be dropped for lack of captions.** The availability risk that would have
   justified a scope reduction did not materialise.
2. **Programme-level comparison is only defensible where a marker exists.** For the other channels
   `programme_id` is `NULL` by design, so the agenda analysis runs at **channel × date** level. This
   is a scope boundary, not a defect: a loose pattern would mislabel videos, which is worse than
   `NULL`.
3. **Every transcript is ASR output.** With zero manual captions, the actor-dictionary mitigation for
   NER (APP-OVERVIEW §7 M2) is mandatory rather than optional, and caption *quality* remains
   unmeasured — availability was this section's question, quality is SPEC-003/004's.

Established separately: the six handles resolve to real channels (confirmed by George 2026-11-11);
captions arrive as `json3` timed text with cue-level start/end times (APP-OVERVIEW §6); Georgian
model tooling is thin (no usable spaCy Georgian NER), so multilingual sentence embeddings remain the
assumption for M1.

**A report is still not authorised by this section alone.** Under
[D-008](steering/decisions.md) SPEC-002's full backfill to 2026-10-01 must re-measure the caption
rate across the whole archive, because this sample is the *recent* uploads (13 dates, mostly
November) and an older bulletin could differ. Availability measured on the latest 120 uploads is
evidence, not proof, about October.

**A channel with low caption coverage would be kept and caveated, never dropped** — dropping one
silently changes the research question. The measurement above means that rule was not triggered:
coverage is 100 % in every cell sampled, so the remaining availability question is about the older
part of the archive, not about any channel.

---

## 5. Analytical Approach

Phase order follows the dependency chain in APP-OVERVIEW §10. Each phase gets its own
SPEC and its own `.status` gate; `[SW]` phases run Structured SDD-V2, `[DA]`/`[ML]` phases
run Formal SDD-DA.

| Phase | Question it answers | Input → output | Tag |
|---|---|---|---|
| P0 Feasibility | Are there enough captions to study? | channel listings → `captions.csv` | `[DA]` Lightweight |
| P1 Collection | What was published, with what captions? | handles → `videos`, `captions`, raw json3 | `[SW]` |
| P2 Normalisation | What sentences were said, when? | `captions` → sentence rows with timestamps | `[SW]` |
| P3 Segmentation | Where does one topic end and the next begin? | sentences → `segments` | `[SW]`/`[ML]` |
| P4 Topics (M1) | What is covered, how much? | segments → topic shares per channel-week | `[ML]` |
| P5 Agenda dynamics (M6) | How does coverage shift and spread? | topic shares → time series, spread metrics | `[DA]` |
| P6 Entities (M2) | Who is named? | segments → actor mentions via dictionary | `[ML]` |
| P7 Framing (M5) | In what terms, and does it differ by channel? | prevalent-topic segments → frame clusters | `[ML]` |
| P8 Sentiment/ABSA (M4) | What stance toward which actor? | prevalent segments → attributed statements | `[ML]` |
| P9 Presentation | How is this shown and exported? | results → workbench + bilingual report | `[SW]` |

Statistical stance: descriptive first. Topic share is reported as a proportion of a
channel's captioned segments in a window, with the denominator always shown. No
significance testing is planned in v1, because the corpus is a census of published
broadcasts rather than a sample from a population — the relevant uncertainty is
*caption coverage and classification error*, not sampling error, and both are reported
rather than tested away.

---

## 6. Output Deliverables

- **Workbench** — a Streamlit app (English UI) to pick channels, period and programme type,
  run or refresh methods, set the prevalent-topic threshold, and compose chart blocks.
- **Report** — one self-contained bilingual HTML dashboard per two-month window, built from
  the workbench selection, with a methodology block, validation figures and an
  "AI-generated, verify against source" notice linking to the video timestamp
  (APP-OVERVIEW §9).
- **Raw captions retained** on disk, and a methodology page in every report, so any figure
  can be traced to a segment and a timestamp.

---

## 7. Success Criteria

The analysis is complete for a window when:

1. Every captioned news/talk video published in the window by the six channels is either in
   the dataset or in a logged exclusion list with a stated reason — no silent gaps.
2. Each channel's topic share is reported with its denominator (captioned segments), and a
   reader can see how many videos that rests on.
3. Every LLM-derived figure carries a validation figure and its agreement rate.
4. Every chart in the report is traceable to a query a colleague can re-run.
5. A colleague can reproduce one window from the `docs/` folder alone, without asking a
   question.
6. George can state the main cross-channel difference in one sentence.

---

## 8. Risks & Assumptions

| # | Risk | Why it matters | Mitigation | Status |
|---|---|---|---|---|
| R1 | **No speaker labels.** Captions do not say who is speaking. | "The channel said X" cannot be distinguished from "the channel aired someone saying X"; this is the single largest interpretive hazard for a framing claim | Attributed-statement extraction (M4) where the text names a speaker; the limitation is stated in every report; no speaker-attributed claim without an explicit reported clause | Known, unmitigable in v1 |
| R2 | **Auto-caption noise.** Georgian auto captions mangle names, numerals and homophones. | Hits NER hardest; a wrong name becomes a wrong actor becomes a wrong network edge | Actor dictionary with aliases; prefer manual captions where present; report the manual/auto mix per channel as a quality covariate | **Confirmed worst case:** 0 of 99 sampled videos have manual captions, so every transcript is ASR output. Coverage is 100 % but quality is unmeasured |
| R3 | **LLM-validates-LLM circularity.** A second model agreeing with the first is not independent ground truth; correlated models share blind spots. | Agreement figures would overstate confidence, which is worse than no figure | Cross-*vendor* validation only, never same-model; George spot-checks 30–50 segments per method; agreement reported as a ceiling, with the circularity named in the methodology block | Known, partially mitigable |
| R4 | **Georgian token cost.** Georgian consumes several times more tokens per word than English. | The ~USD 20/month budget can be exhausted by one careless full-corpus pass | LLM calls restricted to news segmentation and to prevalent-topic segments only (APP-OVERVIEW §8); per-run cost logged in `runs`; prompt caching by hash | Known |
| R5 | **YouTube IP blocking.** Datacenter IPs are blocked; a residential IP can still be challenged. | Collection stops; a partial window silently biases the agenda comparison | Collector stays on the residential machine; a blocked run fails loudly and logs the exact error (see FEASIBILITY.md for the observed case); collection status is a reported field, not an assumption | **Observed**, not hypothetical |
| R6 | **Programme attribution is unreliable** (measured: ≈69 % of titles match no configured programme). | Programme-level comparison is only defensible on 3 of 6 channels; a naive filter would silently drop two-thirds of the corpus | Analyse at **channel × date**; keep `programme_id = NULL` where no marker exists; SPEC-002 reports per-channel coverage so an empty channel (Formula) is visible rather than silent | **Measured** (§4) |
| R9 | **Duration heterogeneity.** Videos range 1.4–130 min, mixing full bulletins with short clips and one live stream. | A fixed-window segmenter tuned on 30-minute bulletins will mis-segment 3-minute clips, inflating topic counts for exactly the channels that post most clips | Segment by type: window/ceiling rules for clips vs bulletins; exclude or separately flag live streams > 2 h | **Measured** (§4, FEASIBILITY §3) |
| R7 | **DuckDB is single-writer.** Collection and the interactive workbench share one file. | A scheduled run during an open workbench session fails, or worse, a partial write goes unnoticed | Resolved by [D-005](steering/decisions.md): Streamlit is read-only, method runs dispatch a subprocess, and the collector treats the lock error as a logged "busy" exit | **Resolved (design)** |
| R8 | **Python 3.13.1 installed**; BERTopic's chain (UMAP/HDBSCAN) may lag it. | SPEC-001 could stall on an uninstallable dependency | [D-007](steering/decisions.md): two-hour box on 3.13.1, pre-approved fallback to 3.12 if the chain fails | **Decision rule set** |

**Assumptions stated as assumptions, not facts:** that auto-caption coverage is high enough
for a topic-share comparison to be meaningful; that two months is long enough for a frame
to be visible and short enough to be current; and that "evening news" is identifiable from
titles or playlists without manual curation per channel.

---

## 9. Related Documents

- [APP-OVERVIEW.md](../APP-OVERVIEW.md) — system master plan (v0.1)
- [steering/decisions.md](steering/decisions.md) — D-001 rigor tiers, D-002 build from scratch, D-003 cadence
- [REUSE-AUDIT.md](REUSE-AUDIT.md) — older app: no code reusable
- [FEASIBILITY.md](FEASIBILITY.md) — caption probe: **blocked, no measurements**
- [ARCH-OPTIONS.md](ARCH-OPTIONS.md) — three architecture options; **Option B chosen** (D-004)
- [STATUS.md](STATUS.md) — session state and open gates

| Spec | Title | Status |
|---|---|---|
| SPEC-001 | Repo skeleton, config, DuckDB schema | ⏳ pending |
| SPEC-002 | Collector | ⏳ pending |
| SPEC-003 | Normaliser | ⏳ pending |
| SPEC-004 | Fixed-window segmenter (slice) | ⏳ pending |
| SPEC-005 | LLM gateway + provider benchmark | ⏳ pending |
