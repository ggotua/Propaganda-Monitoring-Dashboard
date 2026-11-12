# STATUS — GTAF

Last updated: 2026-11-12. Branch: `spec-000-kickoff`. Session: first autonomous kickoff.

## Where the project stands

The project has documents and a probe script; it has **no working pipeline and no data**.
That is the intended state after Kickoff Task 0–6, with one deviation: Task 3's caption
probe is blocked by YouTube, so feasibility is unmeasured and the Analysis Brief's data
section is deliberately empty of numbers.

## Done in this session

| # | Task | Result |
|---|---|---|
| 0 | Orient; `.gitignore` | Done. `.gitignore` created at repo root covering secrets, `data/raw`, `data/interim`, `*.duckdb`, `.venv`, `__pycache__`, notebook checkpoints, `.tmp` |
| 1 | Record Stage 0 decisions | Done — [`docs/steering/decisions.md`](steering/decisions.md): **D-001** rigor tiers, **D-002** build from scratch, **D-003** report cadence |
| 2 | Reuse audit | Done — [`docs/REUSE-AUDIT.md`](REUSE-AUDIT.md). Older app contains **no working code**: of 27 files, 13 are empty, 9 are stubs of 27–46 bytes, and the 5 real files are config/README, not code |
| 3 | Caption feasibility probe | **BLOCKED.** Script written, lint-clean, and proven to reach the listing endpoint; YouTube then demanded auth. See [`docs/FEASIBILITY.md`](FEASIBILITY.md) for the verbatim error |
| 4 | Analysis Brief | Done — [`docs/ANALYSIS-BRIEF.md`](ANALYSIS-BRIEF.md), `.status` = `planning`. §4 is marked UNVERIFIED on purpose |
| 5 | Architecture options | Done — [`docs/ARCH-OPTIONS.md`](ARCH-OPTIONS.md): three options, **no recommendation** |
| 6 | Close the session | This file; committed on `spec-000-kickoff`. **Not pushed** — no git remote exists yet |

## Waiting for George

- **G1 — approve or edit [`docs/ANALYSIS-BRIEF.md`](ANALYSIS-BRIEF.md).** Read §2 (core
  question) and §3 (non-goals) first; if they match what you meant, flip
  [`docs/ANALYSIS-BRIEF.status`](ANALYSIS-BRIEF.status) from `planning` to `approved`
  yourself. Nothing downstream is authorised until that file says `approved`.
- **G1 — choose an architecture option in [`docs/ARCH-OPTIONS.md`](ARCH-OPTIONS.md)** and
  give the reason (not just the letter). The reason becomes D-004 in `decisions.md`.
  Decisions there that would be expensive to reverse: DuckDB single-writer exposure,
  whether a domain core is worth its cost, and whether incremental watermarks are needed.
- **G3 — feasibility.** The probe never produced a number. Options: (a) wait a few hours and
  re-run from a normal terminal, (b) supply a cookie file, or (c) accept a scope change. If
  a channel turns out to have almost no captions, §4 of the brief and the scope in
  APP-OVERVIEW change before SPEC-002 is written.
- **Remote.** There is no git remote. Give me a URL and I will add `origin` and push
  `spec-000-kickoff` with verification.

## Environment findings worth keeping

These cost real time this session and will cost it again if forgotten:

- **Python 3.13.1** is installed and has **none** of the app stack (`pandas`, `duckdb`,
  `streamlit`, `plotly` absent). `ruff` and `mypy` are present.
- **`python -m venv` fails normally here**: `ensurepip` dies in temp-directory cleanup
  (`PermissionError: [WinError 5]` on a sandbox temp path). Workaround used:
  `python -m venv .venv --without-pip`, then `python -m pip --python .venv\Scripts\python.exe install ...`.
- **pip's own networking hangs** in this shell (spins at ~100 % CPU, emits nothing). The
  working substitute was to download the wheel with `Invoke-WebRequest` and install it with
  `--no-index --no-deps`.
- **The agent's sandboxed shell cannot complete HTTPS at all** (TCP connects, TLS dies for
  every host, while the harness's own fetcher succeeds). Any network step — the probe, pip,
  a future collector run — must use the unconfined path, one approval per call.
- **yt-dlp must be told `playlistend`** when listing a channel, or it paginates the whole
  upload history (it reached page 293 in this session, which is very likely what triggered
  YouTube's bot check).
- Workspace folder permissions were repaired once (it lacked `WRITE_OWNER` for your
  account); a recovery script and report are in `D:\Data analysis\acl-repair-20261111\` if
  that ever needs undoing.

## Next session, in order

1. Resolve G1 and G3 above; record D-004.
2. Re-run the feasibility probe; then populate `FEASIBILITY.md` tables and brief §4, and
   delete this document's "blocked" framing for Task 3.
3. Only then write **SPEC-001** (repo skeleton, `channels.yaml`/`programmes.yaml`, DuckDB
   schema, logging) — and verify the BERTopic dependency chain installs on 3.13.1 before
   committing to it.
