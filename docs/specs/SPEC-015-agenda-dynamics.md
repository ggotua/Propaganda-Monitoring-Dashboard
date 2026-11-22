# SPEC-015: Agenda dynamics — daily series

Feature:      Per-day topic and actor series
Priority:     P2 — the first view of change over time
Status:       See `SPEC-015.status`
Dependencies: SPEC-006 (drift segments), SPEC-007 (topics), SPEC-011 (actors)
Related docs: G-4 (trend gate) · D-030 (network unit) · D-031 (title exclusion)
Tier:         `[SW]` Structured

---

## 1. Overview

Two series over the same period: how the topic mix moved day to day, and how often each known actor was
mentioned. Both are **counts**, so neither needs a human judge and neither depends on G-8.

The analytical work is therefore not in the arithmetic but in the refusals:

1. **Shares use that day's own denominator**, so a busier day does not look like a spike.
2. **A day with no occurrence renders as 0.0**, not as a shorter row — otherwise a reader compares lists of
   different lengths and sees a trend where there is only an absence.
3. **Thin days void the series.** Under 50 segments a day, one segment moves a share by percentage points.
4. **No trend is claimed.** A trend needs three complete reporting windows (G-4); this corpus has one
   period on one channel, so the output says "this is what the coverage looked like", never "rising".

### Non-goals

- No smoothing, no moving averages, no significance tests: with eleven days, smoothing would manufacture a
  shape that the data cannot support.
- No cross-channel comparison (one channel).
- No causal reading of a spike.

## 2. Acceptance criteria (EARS)

- **FR-1** WHEN a key is absent on a date, THE SYSTEM SHALL emit a zero cell for that date.
- **FR-2** WHEN the caller knows the full date range, THE SYSTEM SHALL render every date, even one where no
  key occurs.
- **FR-3** THE SYSTEM SHALL divide by that day's total, not by the period total.
- **FR-4** WHEN a day has fewer than `min_per_day` segments, THE SYSTEM SHALL mark the series
  non-reportable and state which days.
- **FR-5** WHEN fewer than three days are covered, THE SYSTEM SHALL mark the series non-reportable.
- **FR-6** THE SYSTEM SHALL print the no-trend statement with every run.
- **FR-7** Actor series SHALL exclude title-conflicted segments (D-031), so it cannot disagree with the
  mention table.

## 3. Boundaries

✅ Always: state the denominator; keep zeros visible.

⚠️ Ask first: smoothing; changing `min_per_day`; drawing a line chart from this output.

🚫 Never: call a series a trend; drop thin days silently; compare days with different segment counts
without stating both.

## 4. Testing

`tests/test_timeline.py` covers zero-filling, the explicit date list, per-day denominators, top-`k` cut,
empty input, and the three reportability rules.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-22
Approved: 2026-11-22 (standing delegation)

### Files

| Path | Purpose |
|---|---|
| `src/gtaf/domain/timeline.py` | `pivot`, `reportability`, `Series`, `DayCell` |
| `src/gtaf/application/timeline.py` | topic and actor series over the active segmentation |
| `src/gtaf/infrastructure/repository.py` | `list_segments_with_date`, `topic_counts_by_day` |
| `src/gtaf/cli.py` | `gtaf timeline --by topics|actors --top --min-per-day` |
| `tests/test_timeline.py` | 10 tests |

### Verification with evidence

```
Claim:     The topic mix by day, with its own denominators
Command:   gtaf timeline --by topics --top 6
Exit code: 0
Summary:   10 days, 4,837 segments, reportable: False (2026-11-13 is thin)
           unclassified 33–42 % every day; topic 0 falls 13.7 % → 6.7 %
Verdict:   PASS

Claim:     Actor mentions by day, title-conflicted segments excluded
Command:   gtaf timeline --by actors --top 5
Exit code: 0
Summary:   10 days incl. 2026-11-13 at 0.0 for every actor
           Kobakhidze 45 % → 0 → 53 %; Saakashvili 3 % → 52 % → 19 %
Verdict:   PASS

Claim:     Lint, types, tests
Command:   ruff check ; mypy ; pytest -q
Summary:   All checks passed ; 47 files ; 297 passed
Verdict:   PASS
```

### A defect found by running it

The first actor run showed **nine days instead of ten**: dates were derived from the count rows, so a day on
which no known actor was mentioned disappeared from the series — precisely the failure `pivot`'s own
docstring warns about. Fixed by passing the full date list from the daily totals; a test pins it.

### Next

The series are rendered in the report as two tables ("Topic share by day", "Actor mentions by day") with the
reportability note and the no-trend statement in the caption. No chart: a line from ten points would imply a
direction the corpus cannot support.

### What the first run suggests, and why it is not a finding

The unclassified share is stable at 33–42 % across all ten days, which is evidence that the 38 % figure is
a property of the model and corpus rather than of a particular day. Topic 0's decline from 13.7 % to 6.7 %
and the actor swings are **descriptions of one channel over ten days**; with G-4 unmet they must not be
called trends, and the CLI says so on every run.
