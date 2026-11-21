# STANCE-RULES — how to label when the text is ambiguous

Status: in force from 2026-11-21. Written because the G-8 review found the same content receiving
different labels (#11 `neutral`, #13 `critical`, #36 `unclear` for the same list of court cases), and
because two boundary questions recurred: **reported speech** and **blame aimed at a person's government**.

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
