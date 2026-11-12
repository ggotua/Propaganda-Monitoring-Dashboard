# REUSE-AUDIT — older app `tv-narrative-analysis`

Read-only audit performed 2026-11-11 against
`D:\Data analysis\Propaganda Dashboard\tv-narrative-analysis` and its sibling design
document `tv_narrative_analysis_technical_spec.md`. Nothing was modified, executed or
copied from either. This audit is the only gate through which reuse is permitted
(steering decision [D-002](steering/decisions.md)).

**Headline: there is no working code in the older app.** Of the 27 files in the project
(excluding its bundled `venv/`), **13 are 0 bytes**, **9 are stubs of 27–46 bytes**, and
**5 contain real content** — `requirements.txt`, `setup.py`, `.env.example`, `README.md`
and `.gitignore`. Not one of those five is program code. The `.py` "modules" contain a
docstring and nothing else. The only other substantial artifact is a 1,934-line technical
spec, kept outside the project folder, describing a *rejected* architecture. A bundled
`venv/` inflates the file count into the thousands.

A module qualified for `reuse` only if it had a clean input/output, no hidden state, and
no dependency the new design rejects. No module met even the first of those, because
no module has a body.

## Audit

| Module | What it does | Matches APP-OVERVIEW component | Verdict | Reason | Risk |
|---|---|---|---|---|---|
| `src/pipeline.py` (29 B) | Nothing — module docstring only | §5 orchestrator [1]–[8] | drop | No code to reuse. The name invites a false sense that the orchestration exists | None today; risk is treating this file as a reference implementation |
| `src/scraper.py` (28 B) | Nothing — docstring only | §5 [1] Collector, SPEC-002 | drop | No code. Design intent (yt-dlp) matches the new design, so the *idea* is already in APP-OVERVIEW | None |
| `src/translator.py` (31 B) | Nothing — docstring only | none — deliberately absent | drop | New design analyses Georgian directly with multilingual embeddings (§7 M1). A translate-then-analyse step would double token cost and lose Georgian-specific framing | Reintroducing it would break the §8 LLM budget of ~USD 20/month |
| `src/qualitative_analyzer.py` (41 B) | Nothing — docstring only | §7 M4/M5 | drop | No code. Design depended on local Mistral 7B, replaced by the provider-agnostic gateway (§8) | None |
| `src/quantitative_analyzer.py` (42 B) | Nothing — docstring only | §7 M1/M2 | drop | No code. Intended stack (spaCy + VADER + TextBlob) has no usable Georgian NER/sentiment model; VADER and TextBlob are English-only | If its assumptions leak into a spec, M2 gets planned around tools that cannot do the job |
| `src/sheets_manager.py` (35 B) | Nothing — docstring only | §6 DuckDB store | drop | No code, and Google Sheets is rejected as the store (no keys, no types, one writer, poor volume) | None |
| `src/data_schema.py` (46 B) | Nothing — `import pydantic` plus a comment | §6 data model | drop | No schema defined. New schema is DuckDB DDL with different keys (`video_id`/`segment_id`) | Its intended Pydantic approach would add a dependency the new design does not need |
| `src/config.py` (27 B) | `class Config: pass` | SPEC-001 `channels.yaml`, `programmes.yaml` | drop | Empty class; a config module is a handful of lines written fresh | None |
| `src/__init__.py` (40 B) | Package docstring | — | drop | Trivial | None |
| `tests/test_pipeline.py` (0 B) | Nothing | — | drop | Empty file. No test existed, so the old app cannot demonstrate that any part of it ever worked | Strong reason not to trust the spec's claims as verified behaviour |
| `tests/__init__.py` (0 B) | Nothing | — | drop | Empty | None |
| `dashboard/index.html` (0 B) | Nothing | §9 Streamlit workbench | drop | Empty. The static-HTML dashboard is a different interface style from the chosen Streamlit workbench | None |
| `dashboard/js/charts.js`, `data_loader.js`, `filters.js`, `narrative_display.js` (all 0 B) | Nothing | §9 workbench + export | drop | All empty. Chart/filter logic would in any case be rewritten for Plotly inside Streamlit | None |
| `dashboard/css/style.css` (0 B) | Nothing | §9 theme | drop | Empty | None |
| `prompts/daily_analysis.txt`, `comparative_analysis.txt`, `weekly_synthesis.txt` (all 0 B) | Nothing | §8 LLM prompt versions, M5 | drop | All empty. See the spec row below for the one prompt that does exist in text | None |
| `.github/workflows/daily_collection.yml` (0 B) | Nothing | SPEC-010 scheduler | drop | Empty, and GitHub Actions is the wrong place to collect from: runner IPs are datacenter IPs, which §11 says YouTube blocks | Adopting it would reproduce the blocking problem the new design already knows about |
| `requirements.txt` (269 B, real) | Pins 14 packages, Dec-2023 era | SPEC-001 dependency set | drop | `numpy==1.26.2` and `spaCy==3.7.2` have no wheels for the installed Python 3.13.1, so the file cannot be installed here as written; the set also targets a rejected architecture | Would waste a session on resolver failure; also drags in `google-api-python-client` for storage we are not using |
| `setup.py` (464 B, real) | `setuptools` metadata + duplicate dependency list | packaging | drop | Duplicates `requirements.txt` — a second source of truth for the same pins (a DRY violation); packaging is not needed before v1 | Two dependency lists drifting apart |
| `.env.example` (123 B, real) | `GOOGLE_SHEETS_ID`, `GOOGLE_SHEETS_CREDENTIALS`, `PROMPT_DIR` | SPEC-001 config + secrets handling | drop | Names are specific to the rejected Sheets store. The *convention* it demonstrates (secrets in env, never in code) is already adopted and is in `.gitignore` | None; reusing the file would encode a wrong dependency |
| `.gitignore` (92 B, real) | Ignores `venv/`, `__pycache__/`, `*.pyc`, `.env`, `data/*.json`, `.pytest_cache/`, `*.log`, `.DS_Store` | repo hygiene | drop | Strictly narrower than the new root `.gitignore`, which already covers every one of these plus `data/raw/`, `*.duckdb` and notebook checkpoints | None — superseded, not reused |
| `README.md` (781 B, real) | Describes a 3-channel system with Google Sheets and Mistral | docs | drop | Documents an architecture that was rejected. Copying it would mislead a future session | High if reused: it is the most quotable file in the folder and the most wrong |
| `tv_narrative_analysis_technical_spec.md` (60,685 B, 1,934 lines, Jan 2026) | Full design for the rejected system: GitHub Actions cron, Google Sheets store, local Mistral 7B, static dashboard, 3 channels | whole §5 | drop as a design source; **adapt** three ideas, below | Its architecture contradicts APP-OVERVIEW on storage, scheduler, LLM provider, channel count and UI. Reusing it would silently re-import every rejected decision | Highest source of anchoring bias in this audit — it reads far more authoritative than an unimplemented spec deserves |
| `venv/` (bundled environment, thousands of files) | A virtualenv the old project shipped | — | drop | Package tree, not project code; must never be committed or audited as source. Its presence is why an unqualified `*.py` sweep returns urllib3 instead of the project | Bloats the repo and hides the actual (empty) source in file listings |
| `data/` (`.gitkeep` only) | Nothing | `data/raw/` | drop | No data, no samples. Confirms nothing was ever collected | None |

## The three ideas worth adapting (not code — design)

These are the only items in the older app with transferable value. Each is a *shape*,
not an implementation; writing them into a SPEC means writing new code against a
better-informed requirement.

1. **Qualitative output schema** (`qualitative` JSON in §3.2). It names
   `narrative_elements` as protagonist / antagonist / conflict / resolution and
   `dominant_frames` as a list. That is a usable first draft of M5's output contract and
   worth considering in SPEC-014 — it is closer to a structured frame definition than
   "cluster and label", and a fixed field set is far easier to validate across models.
2. **`discourse_markers`** (`quotation_count`, and counts split by
   government / opposition / expert). Cheap, non-LLM, deterministic, and it is exactly
   the kind of source-and-voice evidence a framing report is thin on given that captions
   carry no speaker labels (§11). Worth evaluating for M3/M4 in SPEC-012/013.
3. **The `comparative_analysis` prompt's output discipline** (Appendix B): JSON-only
   return, explicit `shared_narratives` / `divergent_frames` / `propaganda_techniques`
   keys, and a numeric `narrative_alignment` per channel. Prompt-versioned, this is a
   reasonable template for the cross-channel comparison in SPEC-014/015.

A fourth item, `firehose_patterns` (`repetition_detected`, `contradictions`,
`volume_intensity`, `source_diversity`), maps onto APP-OVERVIEW §7's M6 lens. APP-OVERVIEW
deliberately made this a read-off of M6 rather than a classifier; the old field list is a
useful reminder of *which* quantities to read off, and no more than that.

---

**What is worth taking:** three design shapes only — the frame/narrative output schema,
the non-LLM quotation-based discourse markers, and the JSON-only cross-channel comparison
prompt; zero lines of code.

**What is not:** everything executable — all 13 empty files, all 9 stubs, the Dec-2023
dependency pins that cannot install on Python 3.13.1, and the entire rejected
architecture (Sheets, GitHub Actions, Mistral 7B, 3 channels, static dashboard), whose
60 KB spec reads authoritative despite never having run.

**Estimated time saved: ~0 engineer-hours of code, ~2–4 hours of design thinking** — the
reuse value is entirely in not re-deriving M5's output fields and the comparison prompt's
shape from scratch; every hour this audit might otherwise have promised as "we can copy
the collector" would have been spent discovering the collector is empty.
