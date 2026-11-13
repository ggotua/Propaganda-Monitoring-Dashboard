# ASR-QUALITY — a qualitative read of the Georgian auto-captions

Status: **preliminary**. Five raw `json3` files read by eye on 2026-11-13, from 245 available
(Imedi). This is a qualitative read, **not a measured error rate**: n=5 supports observations, not
percentages. SPEC-003 must measure the rate properly on ~30 videos before any quality claim enters a
report.

Why this exists: `FEASIBILITY.md` established that 100 % of sampled videos have captions and that
**none** have manual captions, which makes every downstream claim about *who said what* rest on ASR
output nobody had read. This note is the first look at that text.

## What the text is actually like

Sampled: `imedi/2026-11-04/5Ulgg1ZEflc`, `imedi/2026-11-04/5n_RmZTA3o0`,
`imedi/2026-11-07/wuv0LuMXmi4`, `imedi/2026-11-12/rsIMGqFdbI4`, `imedi/2026-11-05/lpx9XoaO_IA`.
Sizes range 35–493 cues and 1,148–17,830 characters per video.

**Better than feared on coherence.** Sentences are largely grammatical Georgian with punctuation,
and a 17-minute bulletin yields ~490 cues of continuous text. This is usable material, not word salad.

**Speaker changes are marked `>>`.** Example:

```
სტუდიაში კი მივესალმებით ლევან მახაშვილს … >> საღამო მშვიდობის, მოგესალმებით …
```

This is a significant finding: `APP-OVERVIEW` §11 and the brief's risk **R1** assume captions carry no
speaker information at all. They carry no *identities*, but they do carry **turn boundaries** — which
is exactly what attributed-statement extraction (M4) needs to separate one speaker's claim from the
next. R1 should be restated as "no speaker identities" rather than "no speaker structure".

**Non-speech events appear as bracketed tokens**: `[მუსიკა]` (music), `[ტაში]` (applause). These are
not speech and must be stripped before sentence merging and before any token or topic count.

**Foreign-script contamination occurs.** One sample contains Devanagari inside Georgian text:

```
… მშვიდობიანი თანაცხოვრებისა და इकोनॉमिक პარტნიორობის გასამტკიცებლად
```

(`इकोनॉमिक` = "economic" in Hindi script.) Rare in this sample, but it corrupts token-level counts,
entity matching and any Georgian-language model input. It must be detected and flagged, not silently
passed downstream.

**Dialogue is run-on.** Rapid exchanges lose sentence boundaries and speaker attribution inside a cue:

```
გამარჯობა. >> გაზიდან თქვენთან ვართ ხო? >> კი ბატონო მობრძანდით. სამზარეულო აქეთ ხო >> აქ გაზის ონკანი საით უნდა ხართ საიდან შემოდი
```

Cue boundaries therefore **cannot** be treated as speech boundaries. The `>>` marker is the only
reliable turn signal.

## Consequences for SPEC-003 (normaliser)

| Observation | Rule it implies |
|---|---|
| `>>` marks a turn change | Preserve it as a **turn boundary**, do not strip it. Add a nullable `turn_index` to the sentence row so M4 can separate speakers without inventing identities |
| `[...]` marks non-speech | Strip bracketed events before merging; count them (they are also a cheap proxy for music/clip padding) |
| Foreign-script tokens | Detect non-Georgian script runs and flag the sentence; never silently "correct" them |
| Run-on dialogue | Merge cues into sentences using `>>` and punctuation as boundaries, not cue ends |
| ASR has no casing guarantee | Do not rely on capitalisation for entity detection; the actor dictionary must be the primary matcher |
| Cue count varies 35–493 per video | Sentence merging must be O(n) and bounded per video; a 493-cue bulletin is normal |

## What must be measured, and was not

- **Word error rate** on a hand-transcribed sample of ~15 minutes. Without it, "quality" is an
  impression.
- **Named-entity accuracy**: how often a politician's name is mangled. This is the number that decides
  whether M2 needs the actor dictionary to be large or merely present.
- **Rate of foreign-script and bracket tokens** across the corpus, once the backfill exists.
- **Whether numerals survive** (dates, sums, casualty counts) — ASR frequently spells numbers out or
  drops them, and an agenda analysis of "how much" depends on them.

These four measurements belong at the start of SPEC-003, on real files, before the normaliser is
written — the same discipline that caught the pagination and age-gate bugs in the collector.
