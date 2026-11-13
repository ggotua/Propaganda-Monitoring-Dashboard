# SPEC-004: Fixed-window segmenter (vertical slice)

Feature:      Segmentation (temporary, for the slice)
Priority:     P1 — the slice needs any segmentation to test topics end to end
Status:       See `SPEC-004.status`
Dependencies: SPEC-003 (sentences), SPEC-001 (`segments` table already exists)
Related docs: `APP-OVERVIEW.md` §5, §10 (SPEC-004 is explicitly temporary; SPEC-006 replaces it)
Tier:         `[SW]` Structured

---

## 1. Overview

Splits a video's sentences into contiguous, non-overlapping **segments** of roughly equal duration,
never splitting a sentence, and writes them to `segments` with `seg_method = 'fixed'`.

Why a fixed window at all: the vertical slice needs *some* segmentation to prove topics → charts →
report end to end. Correct segmentation (LLM for news, TextTiling for talk) is SPEC-006 and is
`[ML]` work with a benchmark. This spec exists to be thrown away, and its `seg_method` value exists
so nobody confuses its output with the real thing later.

### Non-goals

- No semantic segmentation, no LLM, no embeddings, no topic awareness.
- No tuning per programme type.
- No deletion of sentences from storage (they are transient, D-017).
- No `res_*` tables.

---

## 2. Rules

| Rule | Value | Rationale |
|---|---|---|
| Target window | **90 s** | ~2–3 coherent news items per segment at newsread pace; adjustable by parameter |
| Hard maximum | **240 s** | a segment must stay small enough for an LLM prompt and a topic label |
| Minimum remainder | **20 s** | a 5-second trailing segment is noise, not a topic; it merges backwards |
| Split unit | **sentence** | never split inside a sentence — a half sentence has no proposition |
| Ordering | time order, non-overlapping | spans must tile the video without gaps or overlap |
| `seg_method` | `'fixed'` | distinguishes this from SPEC-006 output |
| `seg_version` | `'1'` | D-009: a re-run under changed rules is distinguishable |
| `segment_id` | `f"{video_id}:{start_ms:08d}"` | deterministic, stable across re-runs, sortable |

Behaviour at the edges:

- A single sentence longer than the hard maximum becomes **its own segment** (it cannot be split).
- A video with no sentences produces **no segments**.
- A trailing remainder below the minimum merges into the previous segment, **unless** that would push
  it past the hard maximum — then the remainder is kept as its own segment (better a small segment
  than an oversized one).
- A segment's text is its sentences joined by a single space; its span is first sentence start to last
  sentence end.

## 3. Persistence

`gtaf segment` writes to `segments` for one video or all videos:

1. delete existing rows for that `video_id` **with the same `seg_method`** (committed first, per D-013);
2. insert the new rows in one transaction.

Re-running is therefore idempotent, and a future SPEC-006 run (different `seg_method`) coexists with
the fixed-window output rather than destroying it — which is exactly what a temporary segmenter should
do.

## 4. Acceptance criteria (EARS)

- **FR-1** WHEN segmenting a video, THE SYSTEM SHALL produce segments whose spans tile the sentence
  range in time order with no overlap.
- **FR-2** THE SYSTEM SHALL NOT split a sentence across two segments.
- **FR-3** WHEN a segment would exceed 240 s, THE SYSTEM SHALL close it and start a new one.
- **FR-4** WHEN the trailing remainder is under 20 s, THE SYSTEM SHALL merge it into the previous
  segment unless that would exceed 240 s.
- **FR-5** WHEN a single sentence exceeds 240 s, THE SYSTEM SHALL emit it as its own segment.
- **FR-6** WHEN a video has no sentences, THE SYSTEM SHALL write no segments and report zero.
- **FR-7** WHEN `gtaf segment` runs twice for a video, THE SYSTEM SHALL leave the segment count
  unchanged.
- **FR-8** THE SYSTEM SHALL record `seg_method = 'fixed'` and `seg_version = '1'` on every row.
- **FR-9** THE SYSTEM SHALL NOT call any network service or LLM.

## 5. Examples (tests)

| # | Input | Expected |
|---|---|---|
| 1 | 10 sentences × 10 s | segments ~90 s, all spans within [0, 100] |
| 2 | one sentence of 300 s | one segment of 300 s (FR-5) |
| 3 | sentences totalling 100 s | one segment (remainder merges) |
| 4 | sentences totalling 200 s | 2 segments, second ≥ 20 s |
| 5 | no sentences | zero segments, no error |
| 6 | same input twice | identical `segment_id` list (determinism) |
| 7 | any input | spans tile without overlap (property check) |

## 6. Requirements mapping

| Requirement | Where |
|---|---|
| FR-1, FR-3, FR-4, FR-5 | `domain/segment.py` window assembly |
| FR-2 | sentence boundary as split unit |
| FR-6 | empty input path |
| FR-7 | repository delete-then-insert |
| FR-8 | constants passed to the repository |
| FR-9 | §1 non-goals |

## 7. Boundaries

✅ Always: add a test for a new edge case; adjust window constants via parameters.

⚠️ Ask first: changing `seg_method` semantics; deleting segments of another method.

🚫 Never: split a sentence; emit overlapping spans; reuse the `'fixed'` method name for real
segmentation (SPEC-006 gets its own).

## 8. Dependency and DRY check

No dependency. Sentence merging stays in `domain/normalise.py`; this module consumes `Sentence` and
must not re-implement normalisation.

## 9. Scalability

262 videos × ~200 sentences → a few seconds. Linear in sentences. No I/O in the domain function.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-13
Approved: 2026-11-13 (standing delegation)

### Files created

| Path | Purpose |
|---|---|
| `src/gtaf/domain/segment.py` | `SegmentDraft`, window assembly, deterministic ids |
| `src/gtaf/application/segment.py` | `SegmentWriter` protocol, `segment_video` use case |
| `src/gtaf/infrastructure/repository.py` | `replace_segments` (per-method delete-then-insert), `list_video_ids` |
| `src/gtaf/cli.py` | `segment --video-id | --all` with tunable window parameters |
| `tests/test_segment.py` | 9 tests including tiling and no-lost-sentence properties |

### Verification with evidence

```
Claim:     Lint, types and tests clean
Command:   ruff check src/ tests/ spikes/ ; mypy ; pytest -q
Exit code: 0 / 0 / 0
Summary:   All checks passed ; 24 files clean ; 122 passed
Verdict:   PASS

Claim:     Segmentation runs over the whole collected corpus
Command:   gtaf segment --all
Exit code: 0
Summary:   segmented 263 video(s): 2355 segments, 1 with none
Verdict:   PASS

Claim:     Windows respect the spec's bounds on real data
Command:   SQL over `segments`
Exit code: 0
Summary:   2355 rows, all seg_method='fixed' seg_version='1'
           duration min 22.2 s / median 95.6 s / max 179.1 s
           0 segments over 240 s, 0 under 20 s
           segments per video: min 1, median 5, max 51
           coverage: 62.4 hours of broadcast
Verdict:   PASS
```

### Deviations from the original spec

1. **A segment closes as soon as its span reaches the target** (90 s), so windows land at ~90–95 s
   rather than overshooting by a sentence. This is the literal reading of "closes once it reaches
   this", and the measured median confirms it.
2. **One video produced no segments.** 263 were attempted and 262 have rows. That is correct
   behaviour for a video whose cues normalise to nothing (all blank or non-speech), and it is
   reported rather than hidden.
3. **`--target`, `--max` and `--min` are exposed as CLI flags.** The spec fixed the constants; making
   them parameters costs nothing and is the first thing anyone tuning segmentation will want. The
   `Revisit if` trigger in §9 is therefore already satisfied structurally.

### Note for SPEC-006

`replace_segments` deletes only rows with the same `seg_method`, so when the real segmenter lands it
will add `'llm'`/`'texttiling'` rows **alongside** these, not replace them. Deleting the temporary
output must be a deliberate act, and a comparison between the two on the same videos is the natural
evaluation for SPEC-006.
