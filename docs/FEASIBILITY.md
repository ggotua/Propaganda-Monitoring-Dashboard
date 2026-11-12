# FEASIBILITY — caption availability for the six Georgian TV channels

**Status: BLOCKED — no measurements were obtained.** This document contains no
percentage, no hours-per-day figure and no channel comparison, because none was
measured. Anything numeric here would be invented, so there is nothing numeric here.

Date of attempt: 2026-11-12 (session started 2026-11-11).
Script: [`spikes/caption_feasibility.py`](../spikes/caption_feasibility.py)
Planned output: `data/feasibility/captions.csv` (metadata only) — **not produced**.

## What was attempted

A metadata-only probe of the six confirmed channels (`@tvimedi`,
`@rustavi2official`, `@postv`, `@georgianbroadcaster`, `@tvformula`, `@tvpirveli1`):
list recent uploads per channel, classify each title as `news` / `talk` / `unknown`,
then read each candidate video's caption availability. No video, audio or subtitle file
was ever downloaded; the probe reads the info dictionary and records whether captions are
advertised and in which languages.

Three defects in the probe were found and fixed during the attempt, each by observation
rather than assumption:

1. **Channel pagination was unbounded.** Without `playlistend`, yt-dlp walks a channel's
   *entire* upload history a page at a time. On the first run it reached page 293 of one
   channel's API JSON before being stopped. Fixed by capping pagination in
   `build_ydl(flat=True, limit=...)`.
2. **Listing mode was wrong.** A non-flat extraction of a channel URL makes yt-dlp resolve
   every video in the catalogue. Fixed by using `extract_flat="in_playlist"`.
3. A date-window filter compared ISO strings while a parsed `date` sat unused; and the
   wheel for `yt-dlp` had to be installed from a locally downloaded file because pip's own
   HTTP stack hangs in this environment. Both fixed.

After these fixes the channel listing worked — it resolved a handle to real video IDs and
selected a candidate for extraction — and then YouTube refused the per-video metadata call.

## The block, verbatim

```
ERROR: [youtube] uhSDjpdKpI4: Sign in to confirm you’re not a bot. Use --cookies-from-browser
or --cookies for the authentication. See
https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp for how to manually
pass cookies. Also see
https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies for tips on
effectively exporting YouTube cookies
```

The probe classified this as blocking and stopped (`exit 1`), as instructed. No workaround
was attempted: no proxy, no cookie injection, no retry through another client.

**Likely partial cause, stated plainly:** defect 1 above means this session sent several
hundred rapid requests to one channel in a few minutes. That is enough, on its own, to
trigger YouTube's bot check for an IP. The block is therefore plausibly *self-inflicted and
temporary* rather than a statement about these channels' captions. It is also possible that
YouTube requires authentication for this kind of enumeration from a residential IP
regardless. The two cannot be distinguished without retrying later.

## What is measured, and what is still unknown

| Question | Answer |
|---|---|
| Do the six handles resolve to real channels? | **Partly tested:** `@postv` and `@tvimedi` listed video IDs successfully. The other four were not reached. |
| Do the channels' titles allow `news` / `talk` classification? | **Unknown.** Titles were fetched but classification was never exercised against real captions. |
| Percentage of videos with manual vs auto vs no captions | **Not measured** — this is the question the task exists to answer |
| Total hours with captions per day | **Not measured** (needs duration × caption availability) |
| Whether captions exist in Georgian (`ka`) vs another language | **Not measured** |

The per-`channel × programme_type` table requested by the task is therefore empty by
necessity, not by omission:

| channel | programme_type | % with captions | % auto | n | status |
|---|---|---|---|---|---|
| — | — | — | — | 0 | not measured |

## Three ways these numbers would mislead, once they exist

Recorded now so they are not invented later by whoever reads the first successful run:

1. **Small-n instability.** 20 videos per cell is a very small sample. If 10 of 20 carry
   captions, the 95 % confidence interval is roughly ±22 percentage points, so a channel
   at 50 % and a channel at 72 % are not distinguishable. A first table will tempt
   comparisons the sample cannot support.
2. **Availability is not usability.** A video "having" auto captions says nothing about
   whether the Georgian text is good enough to segment and analyse. Auto captions fail
   hardest on exactly what this project needs — proper nouns, numerals and speaker
   attribution — so a high caption rate can coexist with a low usable rate. The probe
   cannot tell these apart by design.
3. **The sample window is not representative.** Six weeks of uploads (from 2026-10-01)
   covering one political moment will not generalise to a year, and talk-show volume in
   particular is seasonal and event-driven (elections, crises). A rate measured now is a
   rate for this window.

## How to complete this task

The probe is ready and lint-clean; it needs a network path YouTube will talk to. Two
environment facts matter:

- **It cannot run from the agent's shell.** This session's sandboxed shell cannot complete
  HTTPS requests at all (every host fails during TLS while `web_fetch` succeeds), so a
  successful run requires the unconfined path, which each call must request separately.
- A browser-exported cookie file (`--cookies`) or `--cookies-from-browser` is the standard
  documented remedy for the bot check. That is authentication, not evasion — but it is
  George's decision, because it means using his logged-in identity for the probe.

Recommended: let the IP cool off for a few hours, then from a normal terminal:

```
.venv\Scripts\python.exe spikes\caption_feasibility.py
```

which writes `data/feasibility/captions.csv` and
`data/feasibility/probe_errors.jsonl`, then regenerate this document's tables from that
CSV. **No figure in a report may be produced before that run exists.**

## Consequence for the Analysis Brief

`docs/ANALYSIS-BRIEF.md` §4 (Data Description) is therefore marked **UNVERIFIED**, not
populated. The brief is otherwise complete; it is the one section that must wait for this
document to have numbers.
