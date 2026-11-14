# LLM-BENCHMARK — Gemini (free) vs DeepSeek (paid) on Georgian topic labelling

Status: **first pass**, 2026-11-14. Three segments, one prompt, two vendors. The objective numbers are
below; the quality judgement is George's, which is the point of the exercise (D-010).

Raw generated table (including `cached` flags): `reports/llm-benchmark.md`, produced by
`gtaf llm-benchmark --limit 3`.

## Objective measurements

| Metric | Gemini `gemini-3-flash-preview` | DeepSeek `deepseek-chat` |
|---|---|---|
| Live call succeeded | yes (`HTTP 200`, `OK`) | yes (`HTTP 200`, `OK`) |
| Tokens, tiny probe | 7 in / 1 out / **49 total** | 11 in / 1 out / 12 total |
| Cost, tiny probe | **$0.000000** (free tier) | $0.000004 |
| Tokens, 600-char labelling prompt | ~819–834 total | ~597–622 total |
| Reported tier | `standard` | not reported |
| Cost per 1,000 segments (free tier) | **$0.00** | ~$0.004 (if tokens scale linearly) |

Two facts worth keeping: Gemini's `totalTokenCount` is ~5× its prompt+completion count because
**reasoning tokens are billed and quota-charged**; and free-tier Gemini is free in money but not in
quota, which becomes the operational limit for bulk labelling.

## The labels (verbatim, truncated to 200 chars in the report)

| segment | Gemini | DeepSeek |
|---|---|---|
| `…:00000200` | `{"label_ka": "მაკა ბოჭორიშვილის გამოსვლა პარიზის მშვიდობის ფორუმზე"}` | `{"label_ka": "ბოჭორიშვილი პარიზის მშვიდობის ფორუმზე"}` |
| `…:00094334` | `{"label_ka": "მშვიდობა და ბავშვთა უფლებების დაც…` (truncated by the 200-char display limit) | `{"label_ka": "მშვიდობა ეროვნულ პრიორიტეტად"}` |
| `…:00188992` | `{"label_ka": "საქართველო პარიზის მშვიდობის ფორუმზე"}` | `{"label_ka": "საქართველო პარიზის მშვიდობის ფორუმზე"}` |

## Reading it honestly

- **Both models produce valid, on-topic Georgian labels.** Neither produced English, neither produced a
  40-word sentence for a "6 words maximum" instruction.
- **Both obey the JSON shape** in all three cases — which matters more than eloquence, because the
  pipeline parses it.
- **Gemini names the person** ("მაკა ბოჭორიშვილის გამოსვლა…"), DeepSeek names the event
  ("ბოჭორიშვილი პარიზის მშვიდობის ფორუმზე"). Neither is wrong; the second is closer to a topic label, the
  first closer to a headline. For agenda analysis the shorter, event-centred form is more useful —
  but three segments cannot establish a preference.
- **Two of three labels are near-identical across vendors**, which is weak evidence that the task is easy
  rather than that both models are equally good: agreement on easy items says nothing about disagreement
  on hard ones.

## What this does not establish

1. **Not a quality verdict.** Three segments, one prompt, one instruction. A model that labels easy
   segments well may still collapse on ambiguous ones — the hard cases are exactly where the frame
   analysis (M5) will live.
2. **Not a cost comparison for the real workload.** The free tier is $0 until its quota bites; the paid
   tier is cheap but real. The binding constraint is quota, not money.
3. **Not independent validation.** The two vendors agree here, but agreement on a simple labelling task
   is not the cross-vendor validation D-010 requires — that check belongs to whichever method's output
   is being validated, not to this benchmark.

## What to do with it

Judge the three pairs above. If the shorter, event-centred style is what you want, instruct for it in
the prompt (`prompt_version` bump) rather than switching providers. The provider decision is already
made on cost grounds (D-025: Gemini primary, DeepSeek validator); what this benchmark tests is whether
the free model is *adequate*, and on three segments it shows no reason to think otherwise — which is the
weakest form of "yes" and should be re-run at 30 segments before any report depends on it.
