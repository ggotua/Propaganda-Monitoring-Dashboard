# tech-stack.md — what we run, and why each choice was made

Written 2026-11-12, after SPEC-001 was implemented. Every line here is a decision already made and
paid for, not a wish list. "Because it is popular" appears nowhere.

## Language and interpreter

**Python, targeting 3.12+; the installed interpreter is 3.13.1.**

Why: the analytical ecosystem (BERTopic, sentence-transformers, DuckDB, pandas) is Python-native,
and the LLM/tooling wrappers are best supported there. Why not a notebook-first or R-first stack:
the deliverable is a scheduled pipeline plus a Streamlit app, i.e. software, not a one-off analysis.

The version policy was a rule, not a preference: try 3.13.1 within a two-hour box, fall back to 3.12 if
the CPU embedding chain failed to install (D-007, D-011). **It passed** (D-019): numpy 2.5.4, numba
0.68.1, llvmlite 0.50.0, umap-learn 0.6.0, hdbscan 0.8.44, scikit-learn 1.9.1, sentence-transformers
6.3.0 and bertopic 0.17.4 all import on 3.13.1, and a real Georgian embedding run produces
discriminative vectors (similar 0.63 vs unrelated 0.25 on a 384-dim model). One interpreter, one
environment, one lockfile.

Two machine-specific details that cost time and are not obvious:

- `umap-learn` imports as **`umap`**, not `umap_learn`. A diagnostic that used the distribution name
  reported a false "missing" and nearly triggered a needless downgrade.
- HuggingFace models default to `%USERPROFILE%\.cache\huggingface`, which this machine refuses to
  create (WinError 5). Set `HF_HOME` inside the workspace — `spikes/embedding_smoke.py` does this.

## Storage

**DuckDB 2.0.0, one file at `data/gtaf.duckdb`.**

Why: the workload is analytical SQL over a corpus of tens of thousands of videos and millions of
caption cues — columnar scans and aggregations, not point lookups. DuckDB reads/writes Parquet and
interoperates with pandas/arrow with no server to operate.

Why not SQLite: row-oriented, weaker on wide aggregate scans, and no native arrow interop.
Why not PostgreSQL: it would be a service to run and back up for a single-user local tool (YAGNI).

Accepted cost, recorded rather than hidden: **DuckDB allows exactly one writer.** The workbench is
read-only, method runs dispatch a subprocess, and a lock collision is a logged "busy" exit rather
than a retry loop (D-005).

## Configuration

**Pydantic 2 for shape, PyYAML for parsing, plus hand-written cross-file rules.**

Why pydantic: it reports *every* field error in one pass, which is what FR-4 requires ("fix
configuration in one edit, not ten"). Why not hand-rolled validation everywhere: it would
re-implement error paths for no gain. Why not TOML: YAML tolerates the comment-heavy,
Georgian-string-bearing corpus files this project actually has.

## Collection

**yt-dlp**, invoked with `skip_download` and metadata only. Why: it is the only maintained,
actively-updated tool that reliably extracts YouTube captions, and it degrades legibly when YouTube
changes. Its one non-obvious requirement, learned the hard way: **always pass `playlistend`**, or
channel listing paginates the entire upload history.

## Quality gate

**ruff** (lint, with `BLE` enabled so blind `except` blocks must be justified), **mypy `strict`**,
**pytest**. Why these: deterministic, external, and re-runnable by anyone — the point of a quality
gate is that it is not an AI's opinion (see the SDD workflows' Automated Quality Score Gate).

**uv** manages the environment. Why: pip's networking hangs on this machine (spins at 100 % CPU,
emits nothing); uv installs the same set in seconds. Not a preference — a workaround that became the
convention.

## Installed and validated

- **BERTopic 0.17.4 + UMAP 0.6.0 + HDBSCAN 0.8.44 + sentence-transformers 6.3.0** (CPU, torch 2.15.0)
  for topics and embeddings (SPEC-006/007). Validated on Georgian: 384-dim vectors where two sentences
  about the same summit score 0.63 while an unrelated sentence scores 0.25. The **production model is
  still an open choice** (SPEC-006/007); the smoke test used `paraphrase-multilingual-MiniLM-L12-v2`
  because it is small, not because it is chosen.
- **DeepSeek and Gemini** behind one gateway (SPEC-005). Two *vendors* is a hard requirement, not a
  redundancy: a validator from the same vendor shares the primary's blind spots (D-010).

## Planned, not yet installed

- **Streamlit + Plotly** for the workbench (SPEC-008): interactive filters and charts without
  building a JS front end.
- **Quarto** for the bilingual self-contained HTML report (SPEC-009): `format: dashboard` with
  embedded resources, because the deliverable must survive being emailed.

## Explicitly not used

No ORM (the SQL *is* the analysis), no Docker locally (no local Docker; CI-only if ever), no
Kubernetes/microservices (a solo local tool), no vector database (embeddings live in DuckDB or as
arrays), no GitHub Actions for collection (runner IPs are datacenter IPs, which YouTube blocks —
APP-OVERVIEW §11).
