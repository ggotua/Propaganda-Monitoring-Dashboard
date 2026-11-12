# APP-OVERVIEW — Georgian TV Agenda & Framing Analyzer

> Working name: **GTAF** (Georgian TV Agenda & Framing). Rename freely.
> Workflow: **SDD-V2** for the system `[SW]`, **SDD-DA** for analytical modules `[DA]` / `[ML]`.
> Status: draft v0.1 — 2026-11-03. Decisions below are agreed; open items are in §12.

---

## 1. Purpose (gestalt)

A pipeline that **collects** YouTube captions from six Georgian TV channels, **cuts** them into thematic segments, **analyses** them (topics → entities → networks → aspect sentiment → frames/narratives over time), and **presents** results in two ways:

1. **Workbench** — a Streamlit app where colleagues pick channels, period, methods and charts.
2. **Report** — a self-contained bilingual (EN/KA) HTML dashboard built from the workbench selection, sendable by email or publishable on GitHub Pages.

Analogy: a newsroom monitoring desk. The collector is the intern recording every bulletin, the segmenter is the editor writing the rundown, the methods are the analysts, the report is the weekly brief to the embassy.

## 2. Research questions (priority order)

1. **Agenda** — what does each channel cover, how much, and when? (first deliverable)
2. **Framing** — how are the prevalent topics framed, by which channel, and how do frames shift over time?
3. **Narratives** — which recurring narratives appear, how do they spread across channels and persist?

## 3. Audience and quality bar

- Experts, activists, politicians, diplomats — dashboards and reports.
- Reproducibility: **minimal but honest** — pinned model versions, logged prompts, raw captions kept, methodology page in every report.
- Every LLM-derived number carries a validation figure (§8) and an "AI-generated, verify against source" notice with a link to the video timestamp.

## 4. Scope

| In scope | Out of scope (v1) |
|---|---|
| 6 channels: Imedi, Rustavi 2, POSTV, GPB, Formula, TV Pirveli | Other channels, online-only media |
| Evening news, talk shows, interviews | Entertainment, ads, sports |
| Videos with YouTube captions (auto or manual) | Videos without captions — **skipped**, logged |
| Archive from **2026-10-01**, then daily forward | Older archive |
| Scheduled automatic collection, local PC | Server deployment (designed for, not built) |
| Streamlit UI in English | Georgian UI |
| Reports in English and Georgian | Other languages |

## 5. Architecture

```
            ┌──────────── scheduled (Windows Task Scheduler) ────────────┐
            ▼                                                            │
 [1] Collector ──► raw captions (json3) ──► [2] Normaliser ──► [3] Segmenter
   yt-dlp            data/raw/                 sentences +         news  → LLM
   channel lists                               timestamps          talk  → embeddings (TextTiling)
                                                                         │
                                                                         ▼
                                          ┌───────────── DuckDB (single file) ─────────────┐
                                          │ videos · captions · segments · method results   │
                                          └───────────────────────┬─────────────────────────┘
                                                                  │
         [4] Method modules (pluggable, one interface)            │
         topics · entities · concept network · ABSA · frames ◄────┘
                    │                    │
                    │         [5] LLM gateway (DeepSeek / Gemini, cache, cost log)
                    ▼
         [6] Validator (cross-model + human spot-check)
                    │
                    ▼
 [7] Streamlit workbench + builder ──► [8] Quarto export ──► report.html (EN / KA)
```

### Design principles

- **Functional style**: pure functions, data in → data out; side effects (network, DB, files) at the edges only.
- **Idempotent stages**: every stage can be re-run for a date/channel without duplicating rows; keyed by `video_id` / `segment_id`.
- **Pluggable methods**: each method is a module exposing the same contract (§7). Adding a method = adding a module + registry entry, no changes elsewhere.
- **Collector is separable**: it must be able to run on a home PC while analysis later runs on a server (YouTube blocks datacenter IPs — see §11).
- **Wave-agnostic**: every method runs on any slice (channel × period × programme type).

## 6. Data model (DuckDB)

| Table | Key | Main fields |
|---|---|---|
| `channels` | `channel_id` | name_en, name_ka, youtube_handle |
| `programmes` | `programme_id` | channel_id, name, type (`news` / `talk` / `interview`), title patterns or playlist ids |
| `videos` | `video_id` | channel_id, programme_id, published_at, title, duration, caption_kind (`auto` / `manual` / `none`), status |
| `captions` | `video_id, idx` | start_s, end_s, text |
| `segments` | `segment_id` | video_id, start_s, end_s, text, title_ka, title_en, seg_method (`llm` / `texttiling`), seg_version |
| `runs` | `run_id` | stage, method, params_json, model, started_at, finished_at, n_items, cost_usd, status |
| `llm_calls` | `call_hash` | provider, model, prompt_version, input_tokens, output_tokens, cost_usd, response_json (cache) |
| `res_<method>` | per method | `segment_id`, `run_id`, method-specific columns |
| `validation` | `run_id, segment_id` | validator_model, agreement, human_label (nullable) |

Raw caption files are also kept on disk under `data/raw/<channel>/<date>/<video_id>.json3`.

## 7. Method contract

Every method module exposes:

```python
def run(segments: pd.DataFrame, params: dict) -> pd.DataFrame: ...   # pure
METHOD = {"name": ..., "version": ..., "needs_llm": bool, "outputs": "res_<name>", "charts": [...]}
```

The registry lists methods; the Streamlit builder reads `charts` to offer chart blocks per method.

### Methods v1

| # | Method | Engine | LLM? |
|---|---|---|---|
| M1 | Topic modelling | BERTopic, multilingual sentence embeddings (CPU) | labels only (KA + EN) |
| M2 | Named entities | multilingual transformer NER + **actor dictionary** (aliases → canonical actor) | optional, hard cases |
| M3 | Concept network | keyword/concept co-occurrence within segments, `networkx`, interactive `pyvis` | no |
| M4 | Aspect-based sentiment | aspects = actors **and** topics; extracted as **attributed statements**: *speaker → target → stance* | yes |
| M5 | Framing / narratives | inductive: Entman functions per segment (problem, cause, moral judgement, remedy) → embed → cluster → label | yes |
| M6 | Agenda dynamics | time series of topic share, cross-channel spread, persistence | no (uses M1/M5) |

Firehose-of-Falsehood dynamics (volume, repetition, cross-channel spread) are read off M6 as an analytical lens, not a separate classifier.

## 8. LLM strategy

- **Gateway**: one module wraps providers (DeepSeek, Gemini) behind one function; handles retries on per-minute limits, response caching by prompt hash, token and cost logging in `llm_calls`.
- **Budget**: ~USD 20/month. LLM calls run only where needed:
  - news segmentation (all news videos);
  - M4/M5 only on segments belonging to **prevalent topics** selected from M1 (threshold set in the workbench);
  - validation on samples, not 100 %.
- **Provider choice**: decided by the benchmark spec (§10, SPEC-005) on the same 10 segments — Georgian quality plus measured cost.
- **Validation**:
  - a **different model** re-judges a sample of outputs;
  - George spot-checks 30–50 segments once per method;
  - the agreement figures are shown in reports.

## 9. Interfaces

- **Workbench (Streamlit, EN)**:
  - pick channels, period, programme type;
  - run or refresh methods;
  - set the prevalent-topic threshold;
  - **builder**: choose chart blocks per method, order them, preview.
- **Export**: the builder selection plus a methodology block render through Quarto (`format: dashboard`, `embed-resources: true`) to one `report_<slug>_<lang>.html`.
  - Plotly charts and pyvis networks stay interactive.
  - Noto Sans Georgian is embedded.
  - Data is aggregated before embedding.
- **Bilingual**: UI strings and chart labels come from `i18n/en.yaml` and `i18n/ka.yaml`; topic and frame labels are stored in both languages.

## 10. Spec roadmap

Vertical slice first (one channel, end to end, crude), then deepen.

| Spec | Title | Tag | Slice? |
|---|---|---|---|
| SPEC-001 | Repo skeleton, config (`channels.yaml`, `programmes.yaml`), DuckDB schema, logging | [SW] | ✅ |
| SPEC-002 | Collector: list videos per channel/programme, classify programme type, fetch json3 captions, skip no-caption, backfill from 2026-10-01 | [SW] | ✅ |
| SPEC-003 | Normaliser: clean caption text, merge cues into sentences with timestamps | [SW] | ✅ |
| SPEC-004 | Fixed-window segmenter (temporary, for the slice) | [SW] | ✅ |
| SPEC-005 | LLM gateway + **provider benchmark** (DeepSeek vs Gemini, 10 segments, quality + cost) | [SW] [DA] | |
| SPEC-006 | Real segmentation: LLM for news, embedding TextTiling for talk shows | [ML] | |
| SPEC-007 | M1 Topics (BERTopic) + bilingual labels | [ML] | ✅ (no labels) |
| SPEC-008 | Streamlit workbench v1: filters + topic charts | [SW] | ✅ |
| SPEC-009 | Quarto export v1: one report, EN only | [SW] | ✅ |
| SPEC-010 | Scheduler + run log (Windows Task Scheduler, idempotent daily run) | [SW] | |
| SPEC-011 | M2 NER + actor dictionary (validated against corpus frequencies) | [ML] | |
| SPEC-012 | M3 Concept network | [DA] | |
| SPEC-013 | M4 ABSA via attributed statements | [ML] | |
| SPEC-014 | M5 Framing (Entman, inductive clustering) | [ML] | |
| SPEC-015 | M6 Agenda dynamics over time | [DA] | |
| SPEC-016 | Validator: cross-model agreement + human spot-check UI | [DA] | |
| SPEC-017 | Builder: chart blocks per method, ordering, bilingual export | [SW] | |

Each spec ends with a Stage 6 validity review ("three ways this could mislead or break"). Replans are committed as `replan: After SPEC-N — …`.

## 11. Known constraints and risks

- **YouTube IP blocking.** Works from a residential IP; a server move requires a residential proxy or keeping the collector at home.
- **Auto-caption quality.** Georgian auto captions are noisy (names, numbers). This affects NER most; the actor dictionary mitigates it.
- **No speaker labels.** Captions don't say who speaks. Attributed-statement extraction (M4) partly compensates; the limitation is stated in every report.
- **CPU only.** Embeddings for BERTopic are feasible on CPU at this volume but slow for the backfill; run the backfill overnight.
- **Georgian tokens are expensive.** Georgian uses several times more LLM tokens per word than English; the budget depends on the prevalent-topic filter.
- **Python version.** BERTopic dependencies (UMAP, HDBSCAN) may lag behind Python 3.13; SPEC-001 verifies this and pins the version.
- **No local Docker.** Docker runs only in CI (GitHub Actions); local setup is a native venv.

## 12. Open items (to decide in the named spec)

- Exact programme list and title patterns per channel → SPEC-002.
- LLM provider → SPEC-005 benchmark.
- Prevalent-topic threshold default → SPEC-007/015.
- Embedding model choice (`paraphrase-multilingual-mpnet-base-v2` vs `LaBSE` vs alternatives) → SPEC-006/007.
- Narrative codebook (deductive layer) — after the first inductive M5 run, not in v1.

`DATA-DECISIONS.md` starts empty and fills as specs are implemented.
