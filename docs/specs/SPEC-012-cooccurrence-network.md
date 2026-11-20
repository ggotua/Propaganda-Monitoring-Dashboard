# SPEC-012: Actor co-occurrence network

Feature:      Who is discussed together
Priority:     P2 — descriptive, and it exposes the analytical size of the corpus
Status:       See `SPEC-012.status`
Dependencies: SPEC-011 (actor mentions), SPEC-006 (drift segments)
Related docs: `G5-VALIDATION.md` (what a mention does and does not mean) · D-030
Tier:         `[SW]` Structured

---

## 1. Overview

An edge means two people were mentioned in the same segment. That is a weak claim and the spec keeps it
weak: co-occurrence in a broadcast segment is not a relationship, an alliance or a conflict — it is
"these names appeared in the same few seconds of television".

Its value is diagnostic. It shows whether the corpus has enough actor structure to support the network
questions (M2) at all, and it shows which pairs are *concentrated* rather than merely frequent.

### Non-goals

- No direction, no sentiment, no "who supports whom". Those need statement attribution, which needs
  speaker identity the captions do not carry.
- No temporal evolution: one channel over eleven days cannot support it (G-4).
- No visual graph export yet; the CLI prints tables a reader can check.

## 2. Two measures, and why both

| Measure | Answers | Fails by |
|---|---|---|
| Co-occurrence count | "who is talked about together most" | rewarding fame: two omnipresent politicians co-occur for trivial reasons |
| **Jaccard** `both / (a + b − both)` | "who is *concentrated* with whom" | thin pairs: a single segment gives 1.0 |

So both are reported, and Jaccard is filtered by a minimum shared segment count. Reporting only the count
would produce a plot of who is famous; reporting only Jaccard would produce pairs of nobodies who shared
one sentence.

## 3. Acceptance criteria (EARS)

- **FR-1** WHEN segments are supplied, THE SYSTEM SHALL count each actor pair once per segment.
- **FR-2** THE SYSTEM SHALL NOT emit self-pairs.
- **FR-3** THE SYSTEM SHALL represent a pair once, with actor ids ordered, so `(a, b)` and `(b, a)` cannot
  both appear.
- **FR-4** WHEN a pair appears in fewer than `min_segments`, THE SYSTEM SHALL omit it.
- **FR-5** THE SYSTEM SHALL report Jaccard together with both actors' individual segment counts, so a
  reader can see the denominator.
- **FR-6** WHEN ranking by Jaccard, THE SYSTEM SHALL ignore pairs below a minimum count.
- **FR-7** THE SYSTEM SHALL report the analysed segment count and how many segments mention two or more
  known actors — the denominator that explains a sparse graph.
- **FR-8** THE SYSTEM SHALL produce identical output for identical input (deterministic ordering).

## 4. Boundaries

✅ Always: state the denominator; state that an edge is co-mention.

⚠️ Ask first: adding a layout or rendering layer; lowering `min_segments`.

🚫 Never: call an edge a relationship; rank by raw count alone; present the graph as a complete picture
when most segments mention nobody.

## 5. Testing

`tests/test_networks.py` covers pair counting, self-pair exclusion, symmetry, the `min_segments` filter,
the Jaccard denominator, the Jaccard floor, deterministic ordering, and the empty corpus.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-20
Approved: 2026-11-20 (standing delegation)

### Files

| Path | Purpose |
|---|---|
| `src/gtaf/domain/networks.py` | `co_occurrence`, `top_by_jaccard`, `PairStat` |
| `src/gtaf/application/networks.py` | `build_network` over drift segments |
| `src/gtaf/cli.py` | `gtaf network --min --top --by` |
| `tests/test_networks.py` | 12 tests |

### Verification with evidence

```
Claim:     Pairs, Jaccard and the denominator are computed on the real corpus
Command:   gtaf network --min 3 --top 10        (unit = video, the default since D-030)
Exit code: 0
Summary:   262 videos analysed | 47 mention two or more known actors (17.94%) | 14 pairs at min 3
           Kobakhidze — Papuashvili 17 (jaccard 0.293)
           Kobakhidze — Saakashvili 17 (0.236)
           Papuashvili — Saakashvili 10 (0.161)
Verdict:   PASS

Claim:     The strict unit is available and is nearly empty, which is why it is not the default
Command:   gtaf network --unit segment --min 2
Exit code: 0
Summary:   4,837 segments analysed | 21 mention two or more actors (0.43%) | 6 pairs
Verdict:   PASS (and the finding that forced D-030)
```

### Deviation from the original spec

The spec's edge definition (§1, "same segment") is now the **strict option**, not the default. Measured:
segment level yields 0.43 % of units with two actors, video level 17.9 %. D-030 records the change and the
reasoning; the weaker claim ("same broadcast") is the one this corpus can support, and it is stated
wherever the result appears.

### Standing caveat

An edge is **co-mention in one segment**, nothing more. With a 15-name dictionary the graph is a view of
the dictionary plus the corpus, not of Georgian politics; a pair that never appears may simply mean one of
the two is not in `config/actors.yaml`.
