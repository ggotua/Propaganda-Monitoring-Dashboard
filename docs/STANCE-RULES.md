# STANCE-RULES — how to label when the text is ambiguous

Status: in force from 2026-11-21, extended 2026-11-26 (stance-v3) after a publication review.

## 0. What stance-v3 added

Three rules were added to the prompt, not just to this document, because the labels the model produces are what
these rules govern.

**Target pinning.** Evaluate stance toward the named person only. An attack on Ivanishvili, on Georgian Dream or
on "the regime" is `unclear` unless the text names the target or clearly implicates them. A review found four
`critical` labels on pieces that attacked Ivanishvili and never mentioned Kobakhidze.

**Reported self-praise is neutral.** When the outlet relays the target's own words about their own record, that
is `neutral` — it is the politician's self-assessment, not the outlet's stance. Only the outlet's own
contribution (a headline, an aside, a tone) is evaluated. A review found one self-praise headline labelled
`supportive` and two of the same kind labelled `neutral`.

**Someone else is not the target.** An attack on a relative, the party, a minister acting in the target's name,
ambassadors or another person is `unclear` — not `critical`, and not `neutral`.

Measured effect of v3: `supportive` on the Kobakhidze sample 1 → 0, and Ivanishvili `critical` 7 → 6 as
regime-attacks moved to `unclear`. Under-detection did **not** improve: TV Pirveli's Kobakhidze coverage still
gets zero `critical` labels where a human found four in thirty (D-037).

## 0a. What stance-v4 changed, and why

The v3 rule was worded **negatively** — "label only if the target is named or clearly implicated" — and the
model read it as *"only if the article is mainly about him"*. The result was the opposite failure: `unclear`
inflation and collapsed recall (4 of 11 critical, 0 of 2 supportive caught).

v4 states the rule **positively** and adds five examples taken from the reviewed batch:

> If the text names the target and attributes an action, motive or quality to him, label the stance of **that
> attribution** — the article does not need to be mainly about him.

Also added: the **headline is part of the text** ("if the headline says he 'joked' or 'lied', that is a stance").

Measured on the same 52 publications: Kobakhidze `critical` 0 → **3**, `unclear` 9 → **1**; Ivanishvili
`critical` 6 → **14**, `unclear` 15 → **6**, `supportive` 0 → **1**. All three Kobakhidze pieces and all four
Ivanishvili pieces named in the review are recovered.

**Not yet validated.** These labels have not been re-reviewed by a human, so the publication G-8 remains failed
until `reports/g8-web-review-v4.csv` is scored (D-038).


The labels describe **how the segment frames the named person**, not what anyone believes, and not what is
true. Every rule below exists to make two reviewers independently reach the same label.

## 1. Reported speech — #41, #44

If the segment reports that **someone else said something about the target**, the label describes the
*framing of the report*, not the quoted speaker's opinion.

| Case | Label |
|---|---|
| "X accused him of corruption", reported without endorsement | **`critical`** — the segment presents an accusation as news |
| "X accused him of corruption, which is absurd" | **`supportive`** — the text carries the accusation *and* defends him |
| "He said he would return" — his own statement reported neutrally | **`neutral`** — reporting his words is not an evaluation of him |
| Quotation marks around praise by a third party | **`supportive`** only if the reporter does not undercut it; if undercut, `unclear` |

The test: **who is doing the evaluating in this text?** If nobody evaluates the target and the text merely
carries a claim, it is `critical`/`supportive` only when the *report itself* frames him that way (headline
framing, verb choice, "allegedly").

## 2. Blame aimed at his government — #18, #19

Criticism of a government, ministry or era **he led** is `critical` **only when the text ties the criticism
to him personally** — his decision, his order, his responsibility, his name in the same clause.

- "The 2008 war was his decision" → **`critical`**
- "The government then mishandled the case" → **`unclear`** (no personal evaluation), unless the text
  attributes responsibility to him by name
- "Ministers of his era failed" → **`unclear`**; a minister is not the person

This is the same principle as the explicit-target rule in the prompt, applied to institutions rather than
relatives.

## 3. A party disowning him — #12

"The party says his role as chairman was minimal" is **`critical`** (the party distances itself) and in no
case `supportive`. A text that reports the distancing approvingly is `critical`; one that reports it as a
fact without evaluation is `neutral`.

## 4. Quotes and rationales

- The `quote` field must be **verbatim from the segment**. If it cannot be found, the label is
  **unverified** and cannot be used as evidence — `quote_verified` records this.
- A rationale that describes content absent from the segment (#11 claiming the word "psychopath") is a
  reason to distrust the label, even when the label happens to be right.

## 5. Neutral vs unclear

| | Test |
|---|---|
| `neutral` | The text mentions the person and takes **no** position: factual attribution, event listing, neutral description |
| `unclear` | The text does not evaluate the person at all (names him inside someone else's story), or is unreadable |

Mild evaluation is **not** neutral: "if it can even be called an idea" is `critical`.

## 6. What is never done

- Never infer a label from the channel's known editorial line.
- Never label a segment `supportive` because the subject is the one speaking.
- Never coerce a parse failure or an unverifiable quote into a label.
