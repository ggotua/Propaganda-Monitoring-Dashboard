# SPEC-006: Segmentation at semantic boundaries

Feature:      Drift segmentation
Priority:     P1 — every topic figure depends on what a "segment" is
Status:       See `SPEC-006.status`
Dependencies: SPEC-003 (sentences), SPEC-004 (fixed windows as control), SPEC-007 (topics)
Related docs: **D-027** (measured decision) · `spikes/segment_compare.py`
Tier:         `[SW]` Structured

---

## 1. Overview

SPEC-004 shipped 90-second windows as a deliberately disposable unit, and said so. Every topic figure
since then has described *windows*, not stories. This spec replaces the unit with one cut where meaning
changes, and measures whether it actually is better.

The measurement is the spec's centre of gravity, because "better segmentation" is easy to assert and
hard to demonstrate. The metric is the **gap** between mean similarity of adjacent sentences inside a
segment and mean similarity across a boundary:

- a segmenter that cuts mid-thought leaves dissimilar neighbours *inside* → low intra;
- a good one puts the change *on* the boundary → low inter;
- **gap = intra − inter** is therefore the only number that measures what a boundary is for.

Segment count, duration and short-segment share are reported as context, not as evidence.

## 2. Three rules compared

| Rule | Idea | Where it fails |
|---|---|---|
| `fixed` | cut every 90 s | ignores content entirely — kept as the control |
| `pause` | cut on ≥1.8 s silence | pauses in news reading are breath, not structure |
| `drift` | cut where similarity to the next sentence drops below the video's own 25th percentile | needs local embeddings; threshold is per video |

## 3. Acceptance criteria (EARS)

- **FR-1** WHEN sentences and a similarity series are supplied, THE SYSTEM SHALL cut at drops below the
  threshold, respecting minimum, target and maximum durations.
- **FR-2** THE SYSTEM SHALL reject a similarity series not aligned with the sentence pairs.
- **FR-3** THE SYSTEM SHALL produce ids that cannot collide with another method's ids for the same video.
- **FR-4** THE SYSTEM SHALL keep the previous segmentation intact when adding a new one.
- **FR-5** SQLITE queries used for analysis SHALL filter `segments` by the active method.
- **FR-6** THE SYSTEM SHALL compute the threshold per video, not globally.
- **FR-7** THE SYSTEM SHALL record `seg_method` and `seg_version` on every segment.
- **FR-8** The schema SHALL permit the new method name without manual database surgery.

## 4. Boundaries

✅ Always: report the gap alongside segment counts; keep the control segmentation.

⚠️ Ask first: changing the quantile; deleting control segments; changing `min_s` after a rebuild.

🚫 Never: overwrite the control segmentation; let a query count two methods at once; tune a threshold on
the same videos used to report the improvement.

## 5. Testing

`tests/test_segment_drift.py` (9 tests) and `tests/test_segment_pause.py` (10 tests) pin the cutting
rules with synthetic similarity series, so no model is needed. `spikes/segment_compare.py` measures the
three rules on real videos and prints the table that D-027 cites.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-14
Approved: 2026-11-14 (standing delegation)

### Files

| Path | Purpose |
|---|---|
| `src/gtaf/domain/segment.py` | `segment_by_pause`, `segment_by_drift`, method-scoped ids |
| `src/gtaf/application/segment_drift.py` | per-video threshold from neighbour similarities |
| `src/gtaf/application/methods.py` | `ACTIVE_SEG_METHOD` — the single place the choice is made |
| `src/gtaf/infrastructure/embeddings.py` | local SentenceTransformer embedder, cosine |
| `src/gtaf/infrastructure/migrations/003_seg_method_drift.sql` | table rebuild to widen the CHECK |
| `spikes/segment_compare.py` | three-way measurement |
| `tests/test_segment_drift.py`, `tests/test_segment_pause.py` | 19 tests |

### Verification with evidence

```
Claim:     Drift boundaries separate topics; time-based ones do not
Command:   python spikes/segment_compare.py --videos 20
Exit code: 0
Summary:   method  segments  median_s   intra   inter     gap
           fixed        190      96.3  0.4626  0.4776  -0.0150
           pause        281      64.7  0.4619  0.4767  -0.0148
           drift        282      52.1  0.4961  0.2792  +0.2169
Verdict:   PASS

Claim:     The corpus rebuilds and clusters
Command:   gtaf segment --all --method drift ; gtaf topics ; gtaf label-topics --provider deepseek
Exit code: 0
Summary:   4,837 drift segments (from 2,355 fixed); 62 topics + outlier bucket;
           1,849 unclassified = 38.2 %; 62 topics named in ka+en for ~$0.01
Verdict:   PASS

Claim:     Lint, types and tests clean
Command:   ruff check src/ tests/ spikes/ ; mypy ; pytest -q
Summary:   All checks passed ; 39 files clean ; 209 passed
Verdict:   PASS
```

### Three defects found during the rebuild

1. **Duplicate segment ids.** The fixed and drift runs can start a segment at the same millisecond, and
   the insert failed on `ZZGoZutVr7o:00000199`. Ids are now method-scoped (`video:drift:00000199`); the
   fixed method keeps its old format so existing rows stay valid.
2. **DuckDB cannot drop a CHECK constraint** ("No support for that ALTER TABLE option yet"). Migration
   003 rebuilds the table: drop the child tables, *drop the index* (a table index blocks the rename —
   measured), rename, recreate, copy, recreate children.
3. **A plain file copy of the database is stale.** The first migration probe copied `gtaf.duckdb` without
   its WAL and showed 245 videos at schema v1 while the live file held 263 at v2. `CHECKPOINT` first, then
   copy.

### Deviation from the plan

The `pause` method stayed in the code but was **not adopted**: it measured identical to fixed windows, and
a method with no measured benefit is a liability. Keeping it as a documented control costs one function.

### The result that matters

Outlier rate barely moved: **38.6 % → 38.2 %**. Better boundaries did not reduce what the model cannot
place; they doubled the number of topics (30 → 62) and cut the largest cluster from 7.1 % to 5.5 %. So
the unclassified share is a property of the corpus and the model, **not an artefact of segmentation** —
which is a more useful finding than a cosmetic improvement, because it says where the next effort should
not go.
