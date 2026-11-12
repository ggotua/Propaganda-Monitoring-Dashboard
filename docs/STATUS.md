# STATUS — GTAF

Last updated: 2026-11-12. Branch: `spec-000-kickoff`, tracking `origin`
(`github.com/ggotua/Propaganda-Monitoring-Dashboard`).
Sessions: (1) kickoff Tasks 0–6, (2) architecture decisions D-004…D-010, (3) SPEC-001 written.

## Where the project stands

Documents are settled, the architecture is decided, and the first feature spec exists
(`SPEC-001`, status `planning`). **There is still no pipeline code and no data.** Two physical
prerequisites remain: a successful collection run, and a decision on the interpreter chain
(D-007), which is currently *unproven* rather than failed — see below.

## Decisions taken (2026-11-12)

Recorded with rejected alternatives and revisit triggers in
[`docs/steering/decisions.md`](steering/decisions.md). Made by the agent under George's
explicit delegation ("make decisions as senior software engineer"), noted in each entry.

| ID | Decision | Why it mattered now |
|---|---|---|
| D-001 | `[DA]`/`[ML]` → Formal SDD-DA; `[SW]` → Structured SDD-V2 | Two failure modes, two gate sets |
| D-002 | Build from scratch; reuse only via `REUSE-AUDIT.md` | Older app is a shell; silent copying would import a rejected model |
| D-003 | Report cadence: every two months, 6/year | Was undefined in APP-OVERVIEW entirely |
| **D-004** | **Architecture: Option B — layered modular monolith, domain core + adapters.** Adopts immutable-raw + `runs` watermark from Option C; defers its machinery | §7/§8/§11 are interchange requirements; layering is free on greenfield |
| **D-005** | **One writer.** DuckDB's own file lock; Streamlit `read_only=True`; method runs dispatch a subprocess; collector treats lock errors as logged "busy" | Collection and workbench share one file by design, so collision is normal |
| **D-006** | **Method contract → `run(segments, ctx)`** — injected context, no ambient state | Old `run(segments, params)` claimed purity while §8 required cost/`llm_calls` writes; the contract was false |
| **D-007** | **Python: two-hour box on 3.13.1, pre-approved fallback to 3.12** | Turns an open risk into a decision rule with a committed trigger |
| **D-008** | **Feasibility moves from spike-gate to collector output.** Low-coverage channel is caveated, never dropped | The spike duplicated what SPEC-002 must record anyway; G3 re-scoped |
| **D-009** | Schema: `videos.caption_lang`, `videos.broadcast_date_local`, `schema_meta.schema_version`, `method_version` on results; all instants UTC | Locks these before SPEC-001 DDL |
| D-010 | Benchmark picks the primary LLM; **validator is always a different vendor**; gateway refuses over-budget runs | R3 circularity and budget are not benchmark questions |

`APP-OVERVIEW.md` is now v0.2 and reflects D-003/004/005/006/007/009 inline.

## Gate state

| Gate | Status |
|---|---|
| G0 — orient, handles, cadence, older-app path | **Closed** (2026-11-11) |
| G1 — Analysis Brief | **Approved** — [`ANALYSIS-BRIEF.status`](ANALYSIS-BRIEF.status) says `approved` |
| G1 — Architecture | **Decided** — Option B (D-004) |
| G3 — Feasibility | **Re-scoped** (D-008): SPEC-002's first run must emit the caption table before SPEC-007 or any report |
| Remote | **Closed** — pushed to `origin`, verified against the remote |
| D-007 interpreter chain | **Open, unproven** — `spikes/bertopic_chain_check.py` exits 3 (inconclusive): all eight modules are simply absent, which proves nothing about compatibility |

## Waiting on the physical world (not on judgement)

1. **A git remote.** Give me a URL and I will add `origin`, push `spec-000-kickoff`, and verify
   with a remote check.
2. **A successful collection run**, from a normal terminal, once YouTube's bot check clears:
   `.venv\Scripts\python.exe spikes\caption_feasibility.py` (optional now — the collector does
   this permanently), or straight to SPEC-002's collector.
3. **George's spot-check of §2–§3 of the brief** — approved by delegation, but if the core
   question or the non-goals are not what you meant, that is the cheapest thing to change and
   it invalidates everything downstream.

## Environment findings worth keeping

These cost real hours and will cost them again if forgotten:

- **Python 3.13.1**, no app stack installed (`pandas`, `duckdb`, `streamlit`, `plotly` all
  absent); `ruff` and `mypy` present.
- **`python -m venv` fails here** — `ensurepip` dies in temp-directory cleanup
  (`PermissionError: [WinError 5]`). Use `--without-pip`, then
  `python -m pip --python .venv\Scripts\python.exe install …`.
- **pip's networking hangs** (spins at ~100 % CPU, emits nothing). Working substitute: fetch the
  wheel with `Invoke-WebRequest`, install with `--no-index --no-deps`. A wheel saved under a
  non-canonical filename is rejected ("not a valid wheel filename").
- **The agent's sandboxed shell cannot complete HTTPS** — TCP connects, TLS dies for every host,
  while the harness's own fetcher works. Network steps need the unconfined path, one approval each.
- **yt-dlp needs `playlistend`** when listing a channel or it paginates the entire upload history
  (it reached page 293 here, which is very likely what triggered YouTube's bot check).
- **The embedding chain is uninstalled, and its installability is untested** (D-011). The check
  script deliberately exits 3 rather than 1 in that state: "not installed" must never be read as
  "incompatible", which is exactly the conclusion a first version of it wrongly printed.
- Workspace folder permissions were repaired once (missing `WRITE_OWNER`); undo script and
  report are in `D:\Data analysis\acl-repair-20261111\`.

## Next session, in order

1. Review **`docs/specs/SPEC-001-foundation.md`** and flip `SPEC-001.status` to `approved` (or
   edit it first). It is written but deliberately **not** set to `approved`, so no code exists
   against an unreviewed schema.
2. Implement SPEC-001: `src/gtaf/` per §2, `config/*.yaml`, `001_init.sql`, JSON logging, the
   four CLI commands, and the tests in §9 — `ruff` + `mypy --strict` clean.
3. Run the D-011 chain check **after** installing the CPU stack; only then does D-007's rule
   apply. Until then the interpreter stays 3.13.1.
4. Then SPEC-002 (collector), whose first run produces the feasibility table (D-008).
5. Keep `docs/steering/tech-stack.md`, `conventions.md`, `principles.md` unwritten until
   SPEC-001 forces their content — inventing them first would be fiction.
