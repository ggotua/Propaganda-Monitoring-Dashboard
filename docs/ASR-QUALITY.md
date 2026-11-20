# ASR-QUALITY — what the Georgian auto-captions are like, and what they cost

Status: **first WER measured** (2026-11-20) on one clip, 373 words, against a **published article** as
reference — which makes the figure an **upper bound**, not a benchmark (see §"First measured WER").
The qualitative read below (five raw `json3` files, 2026-11-13) still stands as observation, not
measurement. A corpus-wide rate needs a stratified sample with hand-made audio transcripts.

Why this exists: `FEASIBILITY.md` established that 100 % of sampled videos have captions and that
**none** have manual captions, which makes every downstream claim about *who said what* rest on ASR
output nobody had read. This note is the first look at that text, and now the first number.

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

## First measured WER (2026-11-20)

| Metric | Raw | With number/currency normalisation |
|---|---|---|
| Shared words compared | 373 | 373 |
| **WER** | 13.3 % | **12.3 %** |
| Substitutions / deletions / insertions | 31 / 13 / 6 | 29 / 11 / 6 |
| **CER** | 4.7 % | **4.3 %** |

**What was compared:** one broadcast clip against the article published about the same report. The
article's first 86 words (anchor intro about the court decision and the RAF fights) have no counterpart
in the caption stream, so they were excluded rather than counted as deletions — counting them would have
inflated the result by ~23 percentage points on a 373-word base.

**Normalisation:** timestamps and punctuation removed; hyphenated words split; `50 000` = `50000`;
`1000$ის` = `1 000 დოლარის`; `10` = `ათი` treated as equal.

### The 46 errors are not all recognition errors

| Class | Approx. count | Why it appears |
|---|---|---|
| Wrong word spacing / joined words | ~16 | `საბალაზიშვილი`, `ნურმა გომედოვი`, `ვიდეო მასალის`, `აბუდაბში`/`აბუდაბის` |
| Editorial rewriting, not ASR error | ~13 | `ესაუბრა` vs `ელაპარაკა`; an added `კი`; a dropped `თავდამსხმელთა` |
| Genuine recognition errors | ~17 | `დიჰმის` (დირჰამის), `ეშალოვნები` (ეშელონებიდან), `გაიგენ`, `უცხოელ` |

The spacing class explains the wide **WER–CER gap** (12.3 % vs 4.3 %): a wrongly split word counts as two
word errors while its characters are almost entirely right. For entity matching this matters less than
the headline figure suggests, because a split name is still recoverable by a dictionary and a joiner.

**Adjusted estimates, clearly labelled as estimates and not measurements:** ≈8 % WER if spacing errors are
set aside, and ≈4–5 % if the likely editorial differences are set aside too. Neither is a replacement for
the measured 12.3 %; both exist to keep the discussion honest about what the number contains.

### The reference was the wrong kind of text

An article is **written**, then edited: sentences are compressed, quotes are paraphrased, connectives are
added. Comparing ASR output to it measures *ASR error plus editorial difference* — two different things
summed. The 13 "editorial" errors are the visible part of that; the invisible part is that an article
that happens to agree with a misrecognised word could equally be scored as agreement.

**A fair benchmark needs a word-for-word transcript made from the audio**, not a published article — the
same clip, typed by a human who listens. That is the only method under which 12.3 % becomes a property of
the ASR rather than of the comparison.

### What this establishes, and what it does not

**Establishes:** the WER is in the low teens on clean narration, and a large share of it is spacing and
editorial, not mis-heard words. That is well inside the gate that governs entity work
(`ANALYTICAL-POLICY.md` G-5 requires WER ≤ 30 %), so **NER may proceed** — with a dictionary and fuzzy
matching, not on raw strings.

**Does not establish:** the rate for the corpus. This clip is **clean narration**; the same session's
court-hearing transcript with **overlapping speech** scored far worse. WER is therefore not a constant —
it is a function of audio conditions, and the conditions correlate with content: hearings, street
interviews and protests are both the hardest audio *and* the most interesting material for this analysis.
A single figure would hide exactly the bias that matters.

### Next measurement (stratified, not more of the same)

Two or three more hand-made audio transcripts, chosen by condition rather than convenience:

1. studio narration (baseline — this clip);
2. a court hearing or parliamentary session (overlapping speech, procedural vocabulary);
3. a street interview or protest (noise, accents, crosstalk).

Report WER and **entity-level** WER per condition. If the entity rate in conditions 2–3 exceeds ~30 %,
the actor dictionary becomes mandatory before any named claim, not merely advisable — and the corpus has
to say which conditions its claims cover.


