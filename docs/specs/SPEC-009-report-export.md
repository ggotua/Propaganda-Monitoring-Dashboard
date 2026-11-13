# SPEC-009: Report export v1 — one self-contained bilingual-ready HTML file (EN only)

Feature:      Report export v1
Priority:     P1 — the artefact the audience actually receives
Status:       See `SPEC-009.status`
Dependencies: SPEC-008 queries, SPEC-007 topics, SPEC-004 segments
Related docs: `APP-OVERVIEW.md` §9 · `TOPIC-EVAL.md` §3/§4 · D-021 · D-019
Tier:         `[SW]` Structured

---

## 1. Overview

Builds one HTML file — no server, no assets folder, no CDN — from the same queries the workbench uses,
containing headline counts, two interactive charts, the topic table, and a methodology block generated
from the same numbers that produced the page. English only in v1 (the roadmap's SPEC-009 scope).

### Non-goals

- No Georgian report yet. The structure must be i18n-ready (every user-visible string goes through a
  single lookup), but v1 ships `en`.
- No builder UI: the report takes CLI filters, not a chart-block composition (SPEC-017).
- No Quarto (see D-021), no PDF, no server-side rendering.
- No LLM-written narrative. Every sentence in the report is either a template or a measured number.

## 2. Deviation from APP-OVERVIEW §9: no Quarto (D-021)

§9 specifies Quarto (`format: dashboard`, `embed-resources: true`). **Quarto is not installed on this
machine and `pandoc` is a broken shim** pointing at a missing binary. Rather than add two external
binaries to a pipeline that must be reproducible, v1 renders HTML directly:

| Need from §9 | How v1 meets it |
|---|---|
| one self-contained file | Plotly `include_plotlyjs="inline"` once, then `False` for later figures |
| interactive charts | Plotly HTML embed |
| embedded Georgian font | not needed in v1 (EN only); noted for v2 |
| methodology page | generated section with the run's own numbers |

Cost accepted: hand-written layout and CSS instead of a theme. Revisit if: the report needs multi-page
structure, PDF output, or a design system — that is when Quarto earns its install.

## 3. Contract

`gtaf report --out reports/report.html [--channel ID] [--since DATE] [--until DATE]`

The file must:

- contain **no external references** — no `http://`, no `https://`, no `<script src>`, no `<link href>`
  to a remote host — so it survives being emailed and opened offline (FR-1);
- state the **outlier rate in the headline block** and again in the methodology section (FR-3);
- carry a **machine-derived notice** and the corpus scope (channels, date span) (FR-4);
- render correctly when the slice is empty: a "no data" statement instead of empty charts (FR-5).

HTML from the corpus is **escaped** — topic labels are ASR keywords, and a keyword containing `<` must
not become markup (FR-6).

## 4. Acceptance criteria (EARS)

- **FR-1** WHEN a report is generated, THE SYSTEM SHALL produce a single file with no external network
  references, verified by scanning the output for `http://`, `https://`, `<script src`, `<link href`.
- **FR-2** WHEN `--channel`, `--since` or `--until` are given, THE SYSTEM SHALL restrict every number and
  chart to that slice.
- **FR-3** THE SYSTEM SHALL display the outlier rate as a headline figure and restate it in the
  methodology section.
- **FR-4** THE SYSTEM SHALL include: generation timestamp, corpus videos/segments/topics, date span,
  channel scope, and a notice that figures are machine-derived.
- **FR-5** WHEN the slice has no segments, THE SYSTEM SHALL state that and omit charts rather than
  drawing empty ones.
- **FR-6** WHEN a label or keyword contains HTML metacharacters, THE SYSTEM SHALL escape them.
- **FR-7** THE SYSTEM SHALL NOT write to the database.
- **FR-8** THE SYSTEM SHALL be deterministic apart from the generation timestamp: two runs on the same
  slice produce identical bodies.

## 5. Structure

```
header        title · period · generated-at · machine-derived notice
kpi row       videos · segments · topics · unclassified %
scope         channels included, date span, segment method
chart 1       topic distribution (outliers distinct)
chart 2       clustered vs unclassified by channel
table         topic · segments · share · keywords
methodology   what it is, what it is not, outlier rate, sample caveats
```

## 6. Boundaries

✅ Always: improve a caveat's wording; add a KPI that the queries already compute.

⚠️ Ask first: any chart implying a claim `TOPIC-EVAL.md` §4 forbids (trend, cross-channel comparison);
adding a template engine or a CDN; adding a second output format.

🚫 Never: fetch anything at render time; normalise shares without stating the outlier rate; embed a
keyword as a topic name without saying labels are keywords.

## 7. Testing

`tests/test_report.py` covers: self-containment (no remote refs), outlier rate in both places, HTML
escaping, empty-slice behaviour, filter restriction, and determinism of the body. Rendering is pure
(`ReportContext` → `str`), so it needs no browser.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-13
Approved: 2026-11-13 (standing delegation)

### Files created

| Path | Purpose |
|---|---|
| `src/gtaf/application/report.py` | `ReportContext` + `build_report`, reusing the workbench queries |
| `src/gtaf/presentation/report_html.py` | pure HTML renderer, Plotly inlined once |
| `src/gtaf/cli.py` | `report` command with `--out`, `--channel`, `--since`, `--until` |
| `tests/test_report.py` | 9 tests: self-containment, escaping, outlier rate, empty slice, determinism |

### Verification with evidence

```
Claim:     Lint, strict types and tests clean
Command:   ruff check src/ tests/ spikes/ ; mypy ; pytest -q
Exit code: 0 / 0 / 0
Summary:   All checks passed ; 31 files clean ; 148 passed
Verdict:   PASS

Claim:     A real report is generated from the corpus
Command:   gtaf report --out reports/report_imedi_2026-11.html --channel imedi
Exit code: 0
Summary:   wrote 4,843,200 bytes — 31 topic(s), unclassified 38.6%
Verdict:   PASS

Claim:     The file is genuinely self-contained (FR-1)
Command:   strip <script> bodies, then scan for remote resource attributes
Exit code: 0
Summary:   remote attr: False | script src: False | link tag: False
           Plotly.newPlot present (library embedded, not linked)
Verdict:   PASS

Claim:     The outlier rate is stated more than once (FR-3)
Command:   count "38.6%" in the output
Exit code: 0
Summary:   3 occurrences (KPI block, methodology bullet, coverage context)
Verdict:   PASS

Claim:     The period reflects the data, not a placeholder
Command:   inspect the subtitle
Exit code: 0
Summary:   "Imedi · 2026-11-03 to 2026-11-13 · generated 2026-11-13 14:02 UTC"
Verdict:   PASS
```

### Deviations from the original spec

1. **No Quarto** (D-021): Quarto is absent and pandoc is a broken shim, so the report is hand-rendered
   HTML with Plotly inlined. §2 of the spec records how each §9 requirement is still met.
2. **Plotly generates a random div id per render**, which made two renders of identical data differ.
   Fixed by passing explicit `div_id` values (FR-8).
3. **A label was not escaped in the chart data.** The first escaping test failed because the topic
   label went into Plotly's JSON unescaped; labels are now HTML-escaped before embedding, and the table
   gained a Label column.
4. **The empty slice omits Plotly entirely**, so a "no data" report is a few kilobytes, not 4.8 MB.
5. **`reports/` is gitignored.** Each file is ~4.8 MB of embedded library; it is a build artefact and is
   reproducible from one command, which the repo records instead of the blob.

### Lessons learned

- "Self-contained" is not decidable by searching for `http`. Plotly's own bundle contains namespace
  URIs and a CDN URL in its banner, none of which are fetched. The test now strips script bodies and
  looks for resource-bearing attributes — the distinction between a *string* and a *load*.
- Determinism needed explicit work: a random div id per figure is invisible until you compare two
  renders of the same data.

### Next

SPEC-017 (builder) would let a user choose blocks; until then the report has one fixed structure, which
is the right trade for a v1 that must not drift from the workbench.
