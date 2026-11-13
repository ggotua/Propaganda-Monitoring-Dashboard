# SPEC-007: Topic modelling (M1) with BERTopic

Feature:      Topic modelling (M1)
Priority:     P1 — the first analytical method and the gate to every chart
Status:       See `SPEC-007.status`
Dependencies: SPEC-004 (segments), SPEC-003, migration `002_topics.sql` (v2)
Related docs: `APP-OVERVIEW.md` §7 (M1), §8, §12 (embedding model is an open item) ·
              `ASR-QUALITY.md` · `decisions.md` D-010, D-019
Tier:         `[ML]` **Formal** SDD-DA — Stage 5 validity review is mandatory, not advisory

---

## 1. Overview

Assigns each segment a topic using BERTopic over multilingual sentence embeddings, and stores the
assignment plus per-topic metadata (size, top keywords, labels) for charts and reports.

Volume at hand: **2,355 segments across 263 videos, 62 hours**, from fixed-window segmentation. That
is enough to build and evaluate the method, and not enough to make an agenda claim — coverage is 9
days of a 43-day window from one channel (STATUS).

### Non-goals

- No cross-channel comparison, no trend analysis (M6, SPEC-015).
- No LLM topic labels yet: the gateway is SPEC-005 and is not built. Labels are **keyword-derived**
  (`c-TF-IDF` top terms) and the Georgian label is the top term, not a human phrase. That is a slice
  limitation, recorded, not hidden.
- No entity extraction, sentiment or frames.
- No tuning per channel.

## 2. Model selection is measured, not assumed

`APP-OVERVIEW` §12 lists the embedding model as an open item. D-019 validated that the *stack* works
on Georgian with `paraphrase-multilingual-MiniLM-L12-v2` — chosen there because it is small, not
because it is best. This spec must choose on evidence:

| Candidate | Rationale |
|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2` (384-d) | fast baseline |
| `paraphrase-multilingual-mpnet-base-v2` (768-d) | the model `APP-OVERVIEW` named first |

Measured on the same 600-segment sample, fixed seed, recording: embedding wall time, number of
topics, **outlier rate** (`topic_id = -1`), and a 10-topic eyeball check of whether top terms are
coherent Georgian phrases. The winner and the numbers go into `docs/TOPIC-EVAL.md` and a decision
entry. **Outlier rate is the primary criterion**: a model that assigns 40 % of segments to "no topic"
would make every downstream chart a lie about coverage.

## 3. Configuration

| Parameter | Value | Rationale |
|---|---|---|
| `min_topic_size` | 15 | with ~2.4k segments, smaller clusters are noise |
| `nr_topics` | auto | merge if outlier reduction justifies it, recorded either way |
| UMAP `n_neighbors` / `n_components` | 15 / 5 | BERTopic defaults, adequate at this scale |
| `random_state` | 42 | determinism (FR-5) |
| `method_version` | `bertopic-<model>-1` | D-009: distinguishable across re-runs |
| Outliers | kept as `topic_id = -1` | dropping them would inflate the coverage of every other topic |

Outliers are **stored**, not discarded. A segment the clustering cannot place is a fact about the
corpus, and hiding it would silently shrink the denominator of every agenda figure — the same failure
mode as an unmeasured caption rate.

## 4. Persistence

`topics` gets one row per topic per run; `res_topics` one row per segment (current assignment).

- **One active assignment per segment** (`res_topics.segment_id` is the primary key). A re-run
  deletes all `res_topics` rows it is about to replace, in two transactions per D-013.
- `topics` rows are scoped by `run_id`, so two runs can be compared without one destroying the other.
- `n_segments` includes outliers only for `topic_id = -1`, which is stored as its own row with
  `label_ka = 'unclassified'`.

## 5. Acceptance criteria (EARS)

- **FR-1** WHEN `gtaf topics` runs, THE SYSTEM SHALL create one `runs` row (stage `topics`) and store
  a `topics` row per discovered topic plus one `res_topics` row per segment.
- **FR-2** WHEN a segment is an outlier, THE SYSTEM SHALL store `topic_id = -1` and SHALL NOT drop the
  segment.
- **FR-3** WHEN `gtaf topics` runs twice with the same parameters, THE SYSTEM SHALL produce an
  identical topic count and identical segment assignments (determinism).
- **FR-4** THE SYSTEM SHALL record `method_version`, embedding model name and every parameter in
  `runs.params_json`.
- **FR-5** THE SYSTEM SHALL NOT exceed the declared cost: this method makes **no LLM call** (labels
  are keyword-derived), so `cost_usd = 0`.
- **FR-6** WHEN the database has fewer than 200 segments, THE SYSTEM SHALL refuse to run and say why —
  clustering 30 segments produces a confident-looking topic model that means nothing.
- **FR-7** THE SYSTEM SHALL report outlier rate, topic count and top terms for the run, so the
  validity review has numbers to judge.

## 6. Validity review (Formal, mandatory before the numbers are used)

Three ways this could mislead, to be answered with measurements and written into `docs/TOPIC-EVAL.md`:

1. **The topics may track bulletin structure, not agenda.** Fixed-window segments from one bulletin
   share guests, music and recurring phrases; a cluster of "introductions" or "weather" would look
   like a topic. Check: do top terms describe subjects or formats?
2. **Georgian ASR noise may become the signal.** Clusters can form around a *mis-transcribed* token
   shared by many segments. Check: are top terms real words or ASR artefacts?
3. **The outlier rate may be doing the work.** If 35 % of segments are outliers, any topic-share
   figure describes a third of the corpus. Check: report the outlier rate next to every share, and
   never present shares normalised to 100 % without saying so.

Plus the standard `[DA]`/`[ML]` gates: Source Traceability (every count traceable to `res_topics`), and
Math Verification for the share computation (a hand-worked percentage on a small fixture).

## 7. Boundaries

✅ Always: add a test for a new parameter; record every metric in `docs/TOPIC-EVAL.md`.

⚠️ Ask first: changing `min_topic_size` after a run is cited anywhere; adding an LLM label step
(that is SPEC-005 territory); dropping the outlier row.

🚫 Never: normalise shares to 100 % without stating the outlier rate; present a keyword label as a
human-readable topic name; tune parameters by looking at the chart you want.

## 8. Scalability

Embedding 2,355 segments on CPU: seconds to a couple of minutes depending on the model. UMAP/HDBSCAN
are the slow part at ~10⁵ segments, not here. The full corpus (~175k segments/year) would need batching
and a smaller `n_neighbors` sweep — recorded as **Revisit if** the corpus exceeds ~50k segments.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-13
Approved: 2026-11-13 (standing delegation)

### Files created

| Path | Purpose |
|---|---|
| `src/gtaf/domain/topics.py` | `TopicAssignment`, `TopicSummary`, outlier rules, share maths, Georgian stopwords |
| `src/gtaf/application/topics.py` | `TopicEngine`/`SegmentReader`/`TopicRepository` protocols, `run_topics`, `InsufficientDataError` |
| `src/gtaf/infrastructure/topics_bertopic.py` | BERTopic adapter with deterministic UMAP/HDBSCAN |
| `src/gtaf/infrastructure/repository.py` | `list_segments`, `replace_topic_results` |
| `src/gtaf/cli.py` | `topics` command |
| `spikes/topic_model_eval.py` | the model comparison behind D-020 |
| `tests/test_topics.py` | 10 tests, engine faked so no model loads |

### Verification with evidence

```
Claim:     Lint, strict types and tests clean
Command:   ruff check src/ tests/ spikes/ ; mypy ; pytest -q
Exit code: 0 / 0 / 0
Summary:   All checks passed ; 27 files clean ; 135 passed
Verdict:   PASS

Claim:     Model choice measured, not assumed
Command:   python spikes/topic_model_eval.py
Exit code: 0
Summary:   MiniLM 11 topics / 30.0% outliers / 28.1 s
           mpnet   8 topics / 22.8% outliers / 53.6 s  -> chosen
Verdict:   PASS

Claim:     Full corpus clustered and persisted
Command:   python -m gtaf topics --top 12
Exit code: 0
Summary:   segments 2355 | topics 30 | outliers 910 (38.6%)
           method bertopic-paraphrase-multilingual-mpnet-base-v2-1
           top topics: China visit (168), patients/cardiac (100), EU dialogue (98) …
Verdict:   PASS
```

### Deviations from the original spec

1. **BERTopic 0.17 takes no `random_state`.** §3 named one; determinism is actually controlled by the
   UMAP and HDBSCAN models, which the adapter now supplies explicitly with seed 42. The first
   evaluation run failed on this, so the deviation is measured rather than theoretical.
2. **Georgian stopwords and `max_df = 0.4` were added to the vectoriser** — not in §3. Without them
   every cluster's top terms were `და, რომ, ეს, არის` (grammar, not subjects). Recorded as D-020.
3. **`probability` is NULL.** Probabilities are not computed (`calculate_probabilities=False`) because
   they roughly triple runtime for a value no current consumer uses. The column exists for the method
   that needs it.
4. **`label_en` is always NULL** in this slice, as §1 said it would be: English labels need SPEC-005's
   gateway. `label_ka` is the top keyword, not a phrase.
5. **The 600-segment evaluation sample was biased** (`ORDER BY segment_id`), which made the measured
   22.8 % outlier rate 16 points better than the full corpus's 38.6 %. Disclosed in `TOPIC-EVAL.md`;
   the *model comparison* remains valid because both models saw the same sample.

### Lessons learned

- A topic model without stopwords is not a weak model; it is a model of grammar. The failure was
  invisible in every metric — topic count and size looked healthy — and only the *keywords* exposed it.
  Reading the labels is not optional.
- The predicted validity risk (clusters tracking format rather than subject) materialised: t10 is
  greetings and thanks. The review question earned its place.
- Convenience sampling inflated the headline metric by 16 points. Any future evaluation must sample
  across videos, not take the first N rows.

### Next

`docs/TOPIC-EVAL.md` §3 constrains what may be claimed; SPEC-008 (workbench) can now chart topics **with
the outlier rate displayed**, and SPEC-006 (real segmentation) should be evaluated by comparing its
topics against these fixed-window ones.
