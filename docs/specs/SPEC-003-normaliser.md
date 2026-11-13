# SPEC-003: Normaliser — cues to sentences, with turns and flags

Feature:      Normaliser
Priority:     P1 (segmentation and every text method depend on it)
Status:       See `SPEC-003.status` — this line is for human reference only
Dependencies: SPEC-002 (captions in `captions`), SPEC-001 (schema, CLI)
Related docs: `APP-OVERVIEW.md` §5, §7 · [`ASR-QUALITY.md`](ASR-QUALITY.md) ·
              [`FEASIBILITY.md`](FEASIBILITY.md) · `decisions.md` D-012, D-017
Tier:         `[SW]` Structured (SDD-V2 Stage 2)

---

## 1. Overview

Turns YouTube's caption cues (thousands of fragments per video) into **timestamped sentences with
speaker-turn boundaries and quality flags** — the unit that segmentation and every text method will
operate on.

This spec is written directly from [`ASR-QUALITY.md`](ASR-QUALITY.md), which read five real
transcripts and found four things that make a naive "join the cues" implementation wrong:

1. Cue boundaries are **not** speech boundaries; dialogue is run-on within a cue.
2. Speaker changes are marked with `>>` — no identities, but real turn structure.
3. Non-speech appears as bracket tokens: `[მუსიკა]`, `[ტაში]`.
4. Foreign-script contamination occurs inside Georgian text (`इकोनॉमिक`).

### Non-goals

- No segmentation into topics (SPEC-004/006), no translation, no LLM call, no NER.
- **No database writes.** See §3.3 — sentences are transient by decision, not by omission.
- No "correction" of ASR text: no spell-fixing, no rewriting. The normaliser preserves what was said
  and flags what is suspect.

---

## 2. Architecture placement

| Layer | Module | Responsibility |
|---|---|---|
| `domain` | `domain/normalise.py` | `Sentence`, `normalise_cues`, bracket/turn/script rules — pure, no I/O |
| `application` | `application/text.py` | use case: load a video's cues through the repository, return sentences |
| `infrastructure` | `repository.py` | new `fetch_cues(video_id)` read method |
| `presentation` | `cli.py` | new `text` command to print sentences for one video (spot-check tool) |

No new dependency: punctuation and script detection use `unicodedata` and plain string tests.

---

## 3. Behaviour

### 3.1 Cue disposition

For each cue, in `idx` order:

- **Bracket events are removed.** Any `[...]` run is stripped and counted as `n_events`. A cue that is
  *only* a bracket event produces no sentence. Music and applause are not speech, and counting them as
  tokens corrupts every downstream figure.
- **`>>` is a turn marker.** A cue containing `>>` starts a new turn (and `>>` itself is removed from
  the text). Multiple markers in one cue advance the turn index accordingly. Turn indices are
  non-decreasing and start at 0.
- **Whitespace is collapsed.** Cue text is stripped and internal runs of whitespace become one space.
- **Foreign script is flagged, not fixed.** If the text contains characters outside Georgian
  (`U+10A0–U+10FF`, `U+2D00–U+2D2F`), Latin, Cyrillic or common punctuation/digits, the sentence gets
  the `foreign_script` flag and the offending characters are preserved verbatim.
- **Empty-after-cleaning cues are dropped.**

### 3.2 Sentence assembly

Consecutive cue text is merged into one sentence until a boundary is hit. A boundary is any of:

| Boundary | Reason |
|---|---|
| Text ends with `.` `?` `!` `…` or `:` | natural sentence end |
| A turn marker appears | different speaker; merging across it would attribute one person's words to another |
| Gap between cues > **2.5 s** | an ASR silence usually means a cut, a shot change, or a speaker change |
| Accumulated length > **400 characters** | a guard against a 493-cue bulletin becoming one 17,000-character "sentence" |

The resulting `Sentence` carries `start_s` = first cue start, `end_s` = last cue end, the merged
`text`, its `turn_index`, and flags.

### 3.3 Sentences are transient — no table, no schema change

`APP-OVERVIEW` §6 has no `sentences` table, and this spec does not add one. Reason: a sentence is a
**deterministic function of `captions` plus a `normaliser_version`**. Persisting it would:

- require a migration and a schema-version bump for data that can be recomputed in milliseconds;
- create a second copy that can drift from `captions` when the rules change;
- add ~2M rows/year for no analytical benefit, since `segments` already carries the timestamps that
  traceability needs.

The `normaliser_version` string is therefore part of the function's contract, and any method whose
output depends on normalisation must record it (D-017). If a future requirement needs sentence-level
annotations keyed by a stable id, that is a migration then — and the id can be derived
`(video_id, start_s)` deterministically.

### 3.4 Determinism

`normalise_cues(cues, normaliser_version)` is a pure function: same cues, same output, no clock, no
randomness, no environment. This is what makes a transient sentence defensible rather than sloppy.

---

## 4. Acceptance criteria (EARS)

- **FR-1** WHEN a cue contains a `[...]` bracket event, THE SYSTEM SHALL remove it from the text and
  count it, and SHALL NOT emit a sentence for a cue that contained nothing else.
- **FR-2** WHEN a cue contains `>>`, THE SYSTEM SHALL start a new turn, increment `turn_index`, and
  remove the marker from the text.
- **FR-3** WHEN merging cues, THE SYSTEM SHALL break the sentence at a terminator, a turn change, a
  gap greater than 2.5 s, or 400 characters, whichever comes first.
- **FR-4** WHEN text contains characters outside Georgian/Latin/Cyrillic/digits/punctuation, THE
  SYSTEM SHALL set `foreign_script` on that sentence and SHALL NOT alter the characters.
- **FR-5** THE SYSTEM SHALL produce sentences whose `start_s`/`end_s` are non-decreasing and lie
  within the input cue range.
- **FR-6** THE SYSTEM SHALL be deterministic: identical cues produce identical sentences.
- **FR-7** WHEN a video has no cues, THE SYSTEM SHALL return an empty tuple, not raise.
- **FR-8** WHEN `gtaf text --video-id` runs, THE SYSTEM SHALL print each sentence with its span, turn
  index and flags, and SHALL NOT write to the database.
- **FR-9** THE SYSTEM SHALL NOT call any LLM or network service.

Completion means: every FR has a passing test with a real fixture, `ruff` and `mypy --strict` clean,
and a spot-check output attached from one collected video.

---

## 5. Examples (these become tests)

| # | Input cues | Expected |
|---|---|---|
| 1 | `["[მუსიკა]"]` | no sentences, `n_events == 1` |
| 2 | `["გამარჯობა.", "[ტაში]"]` | one sentence `გამარჯობა.`, events 1 |
| 3 | `["სიტყვა A", ">> სიტყვა B"]` | two sentences, turns 0 and 1 |
| 4 | `["სიტყვა A. სიტყვა B."]` | two sentences, split on terminators |
| 5 | cues 2.4 s apart, no terminator | one sentence (below the gap threshold) |
| 6 | cues 2.6 s apart, no terminator | two sentences (above it) |
| 7 | `["ა" * 250, "ბ" * 250]` | two sentences (400-char cap) |
| 8 | `["ტექსტი ინგლისურად ინგლისურად इकोनॉमिक"]` | `foreign_script` flag set, text unchanged |
| 9 | `["  ზედმეტი   სივრცე  "]` | `ზედმეტი სივრცე` |
| 10 | `[]` | empty tuple, no exception |
| 11 | same input twice | byte-identical output (FR-6) |

---

## 6. Requirements mapping

| Requirement | Design decision / section |
|---|---|
| FR-1 | §3.1 bracket removal |
| FR-2 | §3.1 turn marker |
| FR-3 | §3.2 boundary table |
| FR-4 | §3.1 foreign-script flag |
| FR-5 | §3.2 span assembly, monotonicity asserted in tests |
| FR-6 | §3.4 determinism |
| FR-7 | §3.1 empty input |
| FR-8 | `cli.py text`, `repository.fetch_cues` |
| FR-9 | §1 non-goals |

---

## 7. Boundaries

✅ **Always**: add a test for a new ASR artefact found in real text; improve a flag name.

⚠️ **Ask first**: changing the 2.5 s or 400-character thresholds once a method depends on them;
persisting sentences to a table; adding a dependency for language detection.

🚫 **Never**: "correct" ASR text; drop a sentence because it looks garbled (flag it); merge across a
`>>` boundary; write to the database from the normaliser.

---

## 8. Dependency and DRY check

No new dependency. `unicodedata` (stdlib) covers script classification. The turn/gap/length rules
live once, in `domain/normalise.py`; segmentation (SPEC-004/006) consumes `Sentence` and must not
re-implement merging.

---

## 9. Scalability check

Per video: 35–493 cues → 10–120 sentences, linear pass, no nested scans. For ~7,000 videos/year this
is a few seconds total. No I/O in the domain function.

**Revisit if**: the 400-character cap produces sentences that segmentation cannot handle — then the
cap becomes a parameter rather than a constant, which is a one-line change with a test.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-13
Approved: 2026-11-13 (George, standing delegation per D-017)

### Files created

| Path | Purpose |
|---|---|
| `src/gtaf/domain/normalise.py` | `Sentence`, `NormalisationResult`, bracket/turn/script rules, sentence assembly, span monotonicity |
| `src/gtaf/application/text.py` | `CueReader` protocol + `sentences_for_video` use case |
| `src/gtaf/infrastructure/repository.py` | `fetch_cues` read method |
| `src/gtaf/cli.py` | `text` command; stdout forced to UTF-8 |
| `tests/test_normalise.py` | 16 tests covering every case in §5 |

### Verification with evidence

```
Claim:     Lint and types clean
Command:   ruff check src/ tests/ spikes/ ; mypy
Exit code: 0 / 0
Summary:   All checks passed! ; no issues found in 22 source files
Verdict:   PASS

Claim:     Normaliser satisfies its acceptance criteria
Command:   pytest -q
Exit code: 0
Summary:   111 passed (16 new in test_normalise.py)
Verdict:   PASS

Claim:     Real bulletin normalises with monotonic spans (FR-5, FR-8)
Command:   gtaf text --video-id dtg77VWcfbQ --limit 6
Exit code: 0
Summary:   211 sentences, 0 non-speech events, 0 flagged (normaliser v1)
           63.9-75.4 -> 75.4-77.9 -> 77.9-82.6 (no overlap)
Verdict:   PASS
```

### Deviations from the original spec

1. **A span-allocation defect was found by the spot-check and fixed.** The first implementation gave
   every fragment of a cue the *whole* cue's span, so two sentences from one cue overlapped in time —
   violating FR-5. Fragments now receive a proportional sub-span by character count.
2. **A monotonicity post-pass was added.** Even with (1) fixed, YouTube's cues overlap *each other*,
   so sentences still overlapped across cue boundaries. `_make_monotonic` trims the earlier sentence
   to the later one's start. This is a deliberate, documented distortion of at most a few seconds;
   the raw payloads keep the original timing.
3. **The CLI forces UTF-8 on stdout/stderr.** The first `gtaf text` run crashed with
   `UnicodeEncodeError` printing Georgian to a legacy console code page — a command that worked but
   appeared broken. Unprintable characters now degrade rather than abort.
4. **Sentences are transient** (D-017): no table, no migration, no schema-version bump.

### Known limitation, measured

A bulletin's opening headline block has no sentence punctuation in the ASR output, so several
headlines merge into one long sentence (the first sentence above runs 19.5–42.3 s and contains five
stories). That is a property of the transcript, not of the normaliser: the 400-character cap is the
only thing splitting it, and no rule can recover boundaries the ASR never emitted. SPEC-004/006
segmentation is where topic boundaries get assigned, and it works on embeddings rather than
punctuation for exactly this reason.

### Next

SPEC-004 (fixed-window segmenter for the vertical slice), after the backfill has enough material —
or SPEC-004 on the 262 videos already collected, which is enough to build and test segmentation on.
