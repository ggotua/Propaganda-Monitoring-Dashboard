# FEASIBILITY — caption availability for the six Georgian TV channels

**Status: MEASURED** (2026-11-12). Previous version of this file recorded a blocked attempt; that
history is kept in §7 because it explains two design rules.

Method: [`spikes/caption_feasibility.py`](../spikes/caption_feasibility.py), metadata only — no
video, audio or subtitle file was downloaded. Titles are classified against the **committed**
`config/programmes.yaml` through the real application loader, so the probe and the future collector
cannot drift apart.

Sample: per channel, up to 20 videos per configured programme type within the archive window
(≥ 2026-10-01) **plus 5 deliberately sampled unclassified videos**. The unclassified sample exists
because measuring captions only on videos that matched a programme would be a selection bias —
and those unclassified videos are 69 % of the corpus.

Output: [`data/feasibility/captions.csv`](../data/feasibility/captions.csv) — 99 rows.

## 1. Headline

**Every video sampled has Georgian automatic captions. None has manual captions.** 99 of 99 videos:
`caption_kind = auto`, `caption_lang = ka`. That is the whole story on availability, and it is
better news than expected for collection — and worse news than it looks for analysis (§5).

## 2. Caption availability by channel × programme type

| channel | type | n | manual | auto | none | % captioned |
|---|---|---|---|---|---|---|
| Imedi | news | 20 | 0 | 20 | 0 | 100 % |
| Imedi | unclassified | 5 | 0 | 5 | 0 | 100 % |
| Rustavi 2 | news | 20 | 0 | 20 | 0 | 100 % |
| Rustavi 2 | talk | 20 | 0 | 20 | 0 | 100 % |
| Rustavi 2 | unclassified | 5 | 0 | 5 | 0 | 100 % |
| POSTV | talk | 11 | 0 | 11 | 0 | 100 % |
| POSTV | unclassified | 5 | 0 | 5 | 0 | 100 % |
| GPB (First Channel) | news | 2 | 0 | 2 | 0 | 100 % |
| GPB (First Channel) | unclassified | 5 | 0 | 5 | 0 | 100 % |
| TV Pirveli | talk | 1 | 0 | 1 | 0 | 100 % |
| TV Pirveli | unclassified | 5 | 0 | 5 | 0 | 100 % |
| Formula | — | 0 | — | — | — | **no in-window classified video found** |

**No cell contains a single uncaptioned video.** Georgian (`ka`) is the only caption language
observed — no English track was offered on any sampled video.

## 3. Volume and duration — bulletins and clips coexist

| channel | type | n | median (min) | min (min) | max (min) |
|---|---|---|---|---|---|
| GPB (First Channel) | news | 2 | 37.5 | 36.7 | 38.3 |
| Imedi | news | 20 | 28.4 | 3.6 | 61.8 |
| Rustavi 2 | news | 20 | 17.8 | 4.0 | 55.0 |
| POSTV | talk | 11 | 10.6 | 1.4 | 18.5 |
| Rustavi 2 | talk | 20 | 8.3 | 1.5 | 23.1 |
| TV Pirveli | talk | 1 | 6.8 | 6.8 | 6.8 |
| Imedi | unclassified | 5 | 7.3 | 2.2 | 24.1 |
| POSTV | unclassified | 5 | 10.7 | 2.4 | 18.6 |
| GPB (First Channel) | unclassified | 5 | 4.0 | 2.1 | 18.9 |
| TV Pirveli | unclassified | 5 | 5.2 | 2.9 | 14.9 |
| Rustavi 2 | unclassified | 5 | 3.5 | 2.3 | 130.1 |

Totals: **104,258 seconds = 29.0 hours** of captioned material across 99 videos, spanning **13
distinct publish dates** (2026-10-01 … 2026-11-12; 90 of 99 in November).

Two facts that change design decisions:

- **Full bulletins exist** (17–38 min medians) and are long enough to contain many topics — the
  segmentation stage is genuinely needed.
- **Short clips also exist** (1.4 min minimum), including a 130-minute live stream. A fixed-window
  segmenter will behave very differently on these; SPEC-003/004 must handle sub-5-minute items
  explicitly rather than assuming every video is a bulletin.

## 4. Programme identification is unreliable — the main finding

**464 titles examined matched no configured programme.** With 211 videos extracted and further
titles skipped once a quota was met, the examined denominator is at least 675, so **≈69 % of titles
cannot be attributed to a programme from the title alone**.

Consequences, stated as facts rather than preferences:

- Programme-level comparison is only defensible for **Imedi** (ქრონიკა), **Rustavi 2** (კურიერი,
  შუადღე) and partially **GPB** (მოამბე) — the channels whose titles carry a programme marker.
- **TV Pirveli** publishes bare story headlines (`ევროპელი ლიდერების სამიტი დუბლინში | …`), and
  **Formula** produced no in-window classified video at all. For these, `programme_id = NULL` is the
  honest value.
- The agenda analysis can still proceed at **channel × date** level without any programme dimension.
  That is a scope decision for SPEC-002, not something to force with looser patterns — a loose
  pattern would mislabel videos, which is worse than NULL.
- Formula's empty row means "nothing in-window could be classified and dated", **not** "Formula has
  no captions". Its unclassified sample was not reached because the extraction ceiling was hit on
  matched-but-too-old items.

## 5. Three ways these numbers could mislead

1. **100 % is a rate for recent uploads, not for the archive.** The sample covers 13 dates, 90 of 99
   in November, because the probe takes the latest uploads. An older bulletin from October could be
   uncaptioned and never enter this sample. The claim "captions are universal" is supported only for
   the recent past; SPEC-002's full backfill to 2026-10-01 must measure it again — which it does for
   free, since it records `caption_kind` for every video (D-008).
2. **"Captioned" is not "usable".** Zero manual captions means every transcript is ASR output:
   Georgian auto captions mangle proper nouns, numerals and names, and carry no speaker labels. A
   100 % availability rate says nothing about whether segmentation, NER or attributed statements
   work. Availability was the question here; quality is a separate measurement for SPEC-003/004
   (risk R2 in the Analysis Brief is now concrete rather than hypothetical).
3. **Small cells make the per-channel table look more informative than it is.** GPB news rests on
   *two* videos and TV Pirveli talk on *one*. Those percentages are noise. The only robust statements
   in §2 are "no uncaptioned video was found in any cell" and "no manual captions exist anywhere".

A fourth, subtler risk: **the unclassified sample (n=5 per channel) is small by design**, chosen to
test the selection bias cheaply rather than to estimate the unclassified population precisely. It
succeeded at the first job — all 25 unclassified samples were captioned — and is too small for the
second.

## 6. What this means for the next specs

| Finding | Consequence |
|---|---|
| 100 % auto `ka` captions | Collection is viable; no channel needs to be dropped for lack of captions |
| Zero manual captions | Actor-dictionary mitigation (APP-OVERVIEW §7 M2) is mandatory, not optional |
| ≈69 % titles unclassifiable | Agenda analysis at **channel × date**; programme filter only where a marker exists; NULL elsewhere |
| 1.4 min – 130 min durations | Segmentation must not assume bulletin length; short items need their own path |
| 1 age-gated video (Imedi) | Per-video skip is required; cookies optional. A single age gate must never abort a run (this probe learned it by aborting one) |
| Formula: 0 in-window classified | SPEC-002 must report per-channel coverage, so an empty channel is visible rather than silent |

## 7. How this was obtained — and the two bugs that shaped it

The first attempt was blocked by YouTube's bot check (*"Sign in to confirm you're not a bot"*),
plausibly self-inflicted: an earlier version of the probe had no `playlistend`, so yt-dlp paginated
one channel's entire upload history and reached page 293 before being stopped.

Two further defects were found by running it, and both changed the tool:

1. **An age-restricted video aborted the whole run.** `"Sign in to confirm your age"` matched the
   block-detection list, so the probe treated one unreadable video as an IP-level block and stopped
   after 21 videos. It now separates per-video skips (`SKIP_HINTS`) from client-level blocks
   (`BLOCK_HINTS`). This is the difference between losing one video and losing the corpus.
2. **A `live_chat` track was counted as captions.** One video advertised only a viewer live chat,
   which is not a transcript of the audio; counting it inflated coverage by one video and produced a
   nonsense `caption_lang` value. Non-transcript keys are now excluded.

Both are recorded because the CSV is a deliverable and its method has to be auditable.

## 8. Reproduction

```
.venv\Scripts\python.exe spikes\caption_feasibility.py \
    --per-category 20 --listing-limit 120 --unclassified-sample 5 --throttle 2.0
```

Writes `data/feasibility/captions.csv` (safe to commit: metadata only) and
`data/feasibility/probe_errors.jsonl`. Runtime ≈ 20 minutes; the 2-second throttle is deliberate.
