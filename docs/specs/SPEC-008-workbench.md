# SPEC-008: Streamlit workbench v1 — filters and topic charts

Feature:      Workbench v1 (filters + topic charts)
Priority:     P1 — the first surface where a colleague sees a number
Status:       See `SPEC-008.status`
Dependencies: SPEC-007 (topics), SPEC-004/003, SPEC-001
Related docs: `APP-OVERVIEW.md` §9 · `TOPIC-EVAL.md` §3 (what may not be claimed) · D-014, D-016
Tier:         `[SW]` Structured

---

## 1. Overview

A read-only Streamlit page that lets a colleague pick a channel and a date range and see topic
distribution, with the model's outlier rate displayed next to every figure.

It makes **no analytical decisions**. The queries are already written and tested
(`application/queries.py`); this spec is the presentation layer over them.

### Non-goals

- No method execution from the UI. Method runs dispatch a subprocess and are a later increment
  (D-005); this version reads what exists.
- No report builder, no Quarto export (SPEC-009).
- No editing, no annotation, no human labelling UI (SPEC-016).
- No caching layer: DuckDB on 2.4k segments answers in milliseconds, and a cache is a bug surface.

## 2. The rule this spec exists to enforce

`TOPIC-EVAL.md` §3, Q3: **38.6 % of segments are unclassified.** A topic chart that omits that is
misleading, and a reader cannot be expected to remember a caveat from a document. Therefore:

| Requirement | Implementation |
|---|---|
| Outlier rate visible | Rendered as a metric above the chart **and** as a distinct bar in it (FR-3) |
| Shares never silently normalised | Bar chart shows counts and shares of the whole slice; the outlier bucket is one of the bars (FR-4) |
| Caveats reachable | A methodology expander in the page itself, not a link to a wiki (FR-6) |
| Empty filters do not lie | A slice with no segments shows "no data", never an empty chart that reads as "nothing broadcast" (FR-5) |

## 3. Read-only and lock behaviour

The app opens the database **read-only** (D-005). While collection runs, DuckDB's lock makes that
impossible (D-014), so the app must:

- catch the lock/IO error and show **"Collection in progress — the database is locked; try again when
  it finishes"** (FR-7);
- never retry in a loop, never open read-write, never partially render a chart from stale state.

This is the D-016 requirement that a user must not meet a raw `IO Error`.

## 4. Acceptance criteria (EARS)

- **FR-1** WHEN the page loads, THE SYSTEM SHALL show corpus counts (videos, segments, topics, date span).
- **FR-2** WHEN the user selects a channel and/or date range, THE SYSTEM SHALL restrict every chart and
  the topic table to that slice.
- **FR-3** THE SYSTEM SHALL display the outlier rate for the current slice as a metric above the charts.
- **FR-4** WHEN plotting topic shares, THE SYSTEM SHALL include the outlier bucket as its own labelled
  entry, computed against every segment in the slice.
- **FR-5** WHEN a slice contains no segments, THE SYSTEM SHALL state that, and SHALL NOT render an empty
  chart.
- **FR-6** THE SYSTEM SHALL include an in-page methodology note naming the outlier rate, the fact that
  labels are keywords rather than phrases, and that these are machine-derived figures.
- **FR-7** WHILE the database is locked by a collector, THE SYSTEM SHALL display a "collection in
  progress" message and SHALL NOT retry or write.
- **FR-8** THE SYSTEM SHALL NOT write to the database.

## 5. Layout

```
sidebar          channel select (only channels with videos), date range
main             metrics: videos · segments · topics · outlier rate
                 chart 1  topic distribution (horizontal bars, outliers highlighted)
                 chart 2  clustered vs unclassified per channel (stacked)
                 table    topic, size, share, keywords
expander         methodology + caveats
```

## 6. Boundaries

✅ Always: add a query with a test; improve a caveat's wording.

⚠️ Ask first: adding a chart that implies a claim not supported by `TOPIC-EVAL.md` §4 (trends, cross-
channel comparison); any write path; caching.

🚫 Never: normalise shares to 100 % without stating the outlier rate; present a keyword as a topic name;
open the database read-write; hide the methodology note behind a link.

## 7. Testing

Queries are tested against a real DuckDB fixture (`tests/test_queries.py`): share denominators include
outliers, an empty slice returns nothing, channels without videos are excluded, per-channel coverage
sums to the total. The Streamlit page itself is verified by launching it headless and confirming it
serves without error (evidence recorded in the Implementation Status), because a UI that only "imports
cleanly" is not a UI that runs.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-13
Approved: 2026-11-13 (standing delegation)

### Files created

| Path | Purpose |
|---|---|
| `src/gtaf/application/queries.py` | read-only analytical queries returning plain rows, no Streamlit/Plotly import |
| `src/gtaf/presentation/app.py` | the Streamlit page: filters, two charts, table, methodology expander |
| `tests/test_queries.py` | 6 query tests, including the denominator rule |
| `tests/test_app.py` | 4 render tests using `streamlit.testing.v1.AppTest` |

### Verification with evidence

```
Claim:     Lint, strict types and tests clean
Command:   ruff check src/ tests/ spikes/ ; mypy ; pytest -q
Exit code: 0 / 0 / 0
Summary:   All checks passed ; 29 files clean ; 141 passed
Verdict:   PASS

Claim:     The page renders against the real corpus with no exception
Command:   AppTest run of src/gtaf/presentation/app.py with GTAF_DB=data/gtaf.duckdb
Exit code: 0
Summary:   exceptions: 0
           metrics: Videos 263 | Segments 2355 | Topics 30 | Unclassified 38.6%
           charts: 2 | tables: 1 | sidebar selectbox: ['Channel']
Verdict:   PASS

Claim:     The app serves over HTTP, not just in a test harness
Command:   streamlit run … --server.port 8599 ; GET / ; GET /_stcore/health
Exit code: 200 / 200
Summary:   page 7,863 bytes with the Streamlit bootstrap; health "ok"
Verdict:   PASS

Claim:     A missing database produces a message, not a traceback
Command:   AppTest with GTAF_DB pointing at a non-existent file
Exit code: 0
Summary:   no exception; an error block is rendered
Verdict:   PASS
```

### Deviations from the original spec

1. **Queries return plain tuples, not DataFrames.** §7 assumed tests would run against DuckDB; keeping
   pandas out of the application layer means `test_queries.py` needs neither Streamlit nor Plotly, and
   the presentation layer owns all formatting.
2. **`width="stretch"` replaces `use_container_width`.** Streamlit 1.67 deprecates the latter (removal
   after 2025-12-31); the render run surfaced the warning, so it was fixed rather than shipped.
3. **The topic column is cast to `str`.** Mixing `"UNCLASSIFIED"` with integers in one column broke
   Arrow serialisation — visible in the first real render as a `pyarrow.lib.ArrowTypeError`.
4. **No time-series chart yet.** The spec listed three views; the third (topic share over time) is
   deferred because nine days of one channel does not support a trend, and a trend chart on this data
   would invite exactly the claim `TOPIC-EVAL.md` §4 forbids.
5. **`E501` is ignored for `app.py`** (pyproject per-file rule): the file is mostly prose, and wrapping
   a methodology paragraph to 100 columns makes it harder to read, not easier.

### Lessons learned

- "It imports cleanly" and "it serves" and "it renders with data" are three different claims. The
  headless `AppTest` run caught two defects (deprecated argument, Arrow type clash) that a successful
  HTTP probe could not see, because Streamlit returns the page shell regardless of script failure.
- The outlier rate is now on the page twice — as a metric and as a red bar in the topic chart — because
  a caveat that requires opening a document is a caveat that will be missed.

### Next

SPEC-009 (Quarto export) can reuse these queries unchanged; the methodology block should be generated
from the same numbers (`outlier_rate`, date span, corpus size) so a report cannot drift from the page.
