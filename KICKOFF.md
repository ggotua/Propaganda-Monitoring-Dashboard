# KICKOFF — First autonomous session

Read `CLAUDE.md` first and follow it. This file lists the work for the first session. Work through the tasks in order without stopping, except at the gates named below.

## Task 0 — Orient (G0, one combined question)

1. Locate `APP-OVERVIEW.md`, `sdd_workflow_v2.txt`, `sdd_data_analysis.txt` in the repo. Read all three fully.
2. Check that `.gitignore` covers: `.env`, `.env.*`, `data/raw/`, `data/interim/`, `*.duckdb`, `.venv/`, `__pycache__/`, `.ipynb_checkpoints/`. Add missing lines (this is the only edit allowed before Task 1).
3. Ask George **one** message with all of these, then wait:
   - the folder path of the older unfinished app;
   - confirmation of the six channel YouTube handles. Propose the handles you can find for Imedi, Rustavi 2, POSTV, GPB (First Channel), Formula, TV Pirveli, and mark any you are unsure of;
   - whether "bimonthly" means every two months (6 reports a year) or twice a month (24 reports a year).

## Task 1 — Record Stage 0 decisions

Create `docs/steering/decisions.md` (append-only, ADR-lite format from `sdd_workflow_v2.txt` Step 1.2d) with:
- D-001: rigor tiers (`[DA]`/`[ML]` Formal SDD-DA; `[SW]` Structured SDD-V2) and why.
- D-002: build from scratch; any reuse only through `docs/REUSE-AUDIT.md`.

## Task 2 — Reuse audit of the older app (read-only)

- Read the older app's code. Do not modify it, run it, or copy from it.
- Write `docs/REUSE-AUDIT.md`: one row per module or file with columns `Module | What it does | Matches APP-OVERVIEW component | Verdict (reuse / adapt / drop) | Reason | Risk`.
- A module qualifies for `reuse` only if it has a clean input/output, no hidden state, and no dependency the new design rejects.
- End with a three-line summary: what is worth taking, what is not, and the estimated time saved.

## Task 3 — Caption feasibility check (SDD-DA Lightweight, no SPEC)

Goal: facts, not assumptions, about caption availability.

- Create `spikes/caption_feasibility.py` using `yt-dlp` metadata only (no video or audio download).
- For each confirmed channel: take the latest 20 evening-news videos and the latest 20 talk-show or interview videos published since 2026-10-01. If programme type cannot be told from the title or playlist, record it as `unknown` and do not guess.
- For each video, record `channel, video_id, title, published_at, duration_s, programme_type, caption_kind (manual / auto / none), caption_lang`.
- Throttle at least 2 s between videos. Run from George's machine only.
- Output:
  - `data/feasibility/captions.csv` (metadata only, safe to commit);
  - `docs/FEASIBILITY.md` with a table `channel × programme_type → % with captions, % auto`, total hours with captions per day, failures, and three ways these numbers could mislead.
- If YouTube blocks the requests, stop and report the exact error. Do not try to evade the block.

## Task 4 — Draft the Analysis Brief (G1)

Write `docs/ANALYSIS-BRIEF.md` following Stage 1 of `sdd_data_analysis.txt`:
- Core question (agenda comparison first; framing and narratives over time second).
- A Non-Goals section.
- Data description using **only** facts from `docs/FEASIBILITY.md`.
- Risks and assumptions: no speaker labels, auto-caption noise, LLM-validates-LLM circularity, Georgian token cost, YouTube IP blocking.
- Output deliverables and success criteria.

Create `docs/ANALYSIS-BRIEF.status` containing `planning`.

## Task 5 — Architecture options (G1, do not choose)

Write `docs/ARCH-OPTIONS.md` per Step 1.2b of `sdd_workflow_v2.txt`: 2–3 options. For each, give the named style, what it optimizes, its cost, when you would regret it, and how the REUSE-AUDIT result affects it. Do not recommend one. `APP-OVERVIEW.md` v0.1 is one input, not the decision.

## Task 6 — Close the session

Update `docs/STATUS.md`. Under **Waiting for George**, list:
- G1: approve or edit `ANALYSIS-BRIEF.md` (flip its `.status` yourself);
- G1: choose an architecture option in `ARCH-OPTIONS.md` and give the reason;
- G3: any feasibility finding that changes scope (for example, a channel with almost no captions).

Commit on branch `spec-000-kickoff` and push. Verify the push with a remote check. Then stop.
