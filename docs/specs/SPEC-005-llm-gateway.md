# SPEC-005: LLM gateway — cache, cost metering, budget guard, model fallback

Feature:      LLM gateway
Priority:     P1 — unblocks topic labels and every LLM method (M4, M5)
Status:       See `SPEC-005.status`
Dependencies: SPEC-001 (`llm_calls`, `runs`), SPEC-007 (topic labels to humanise)
Related docs: D-010 (validator = different vendor) · **D-025** (Gemini free primary, DeepSeek validator) ·
              `ANALYTICAL-POLICY.md` G-6
Tier:         `[SW]` Structured

---

## 1. Overview

One gateway through which every LLM call passes, so that four properties hold by construction rather
than by discipline:

1. **Nothing is paid for twice** — responses are cached by prompt hash.
2. **Every call is costed and attributed** — tokens, cost, model and tier land in `llm_calls`.
3. **The budget cannot be exceeded silently** — a call that would overshoot is refused before it is made.
4. **A retired or overloaded model does not break the pipeline** — each provider is called through a
   fallback chain.

Measured facts this is built on (D-025): DeepSeek responds and is metered; Gemini's free tier responds;
a `gemini-2.5-flash` name that worked in documentation returned *"no longer available to new users"*; and
"Say OK" consumed **26 total tokens** (2 prompt + 1 candidate + 23 reasoning).

### Non-goals

- No streaming, no function calling, no embeddings (embeddings are local, SPEC-007).
- No prompt library: prompts belong to the methods that use them and carry a `prompt_version`.
- No automatic model-quality judgement: the benchmark produces material for a human to judge (D-010).

## 2. Contract

`gtaf llm-check` — one minimal live call per configured provider, reporting status, model, tokens and
cost. The smoke test that proves the keys work in *this* environment.

`gtaf llm-benchmark --limit N` — the same Georgian instruction sent to both providers over N segments,
recording outputs for human judgement plus objective metrics (latency, tokens, cost, JSON validity).
Its output goes to `reports/` (a generated artefact), and a hand-written summary lives in
`docs/LLM-BENCHMARK.md`, because this machine's shell cannot write into `docs/` (see STATUS).

In code: `Gateway.ask(prompt, *, prompt_version, role)` returns an `LLMResponse` with
`text, provider, model, input_tokens, output_tokens, total_tokens, cost_usd, cached`.

## 3. Rules

| Rule | Implementation |
|---|---|
| Cache | `call_hash = sha256(provider + model + prompt_version + prompt)`; a hit returns the stored text with `cached=True` and **cost 0** |
| Cost | input tokens × input price + output tokens × output price, per million; free-tier models price at 0 |
| Budget | before any call, `spent_this_month + estimate(prompt) > budget` → `BudgetExceededError`, no request made |
| Fallback | per-provider ordered model list; `404`, `503` and timeout move to the next model, `429` (quota) stops that provider |
| Vendor rule | `require_different_vendors(primary, validator)` raises if they match — D-010 |
| Logging | every non-cached call writes one `llm_calls` row with tokens, cost, response and tier |

**Quota is not a failure.** A `429` from Gemini's free tier means "wait", not "retry another model":
rotating models to dodge a quota is the same mistake as rotating IPs to dodge a block (D-025, D-024).

## 4. Acceptance criteria (EARS)

- **FR-1** WHEN the same prompt, version, model and provider are asked twice, THE SYSTEM SHALL return the
  cached text and record **no** new cost.
- **FR-2** WHEN a call is made, THE SYSTEM SHALL write one `llm_calls` row with provider, model,
  prompt_version, input/output tokens, cost and the response.
- **FR-3** IF the estimated cost would exceed the remaining monthly budget, THE SYSTEM SHALL raise before
  sending any request, and SHALL NOT write a call row.
- **FR-4** IF a model returns `404` (retired) or `503` (overloaded) or times out, THE SYSTEM SHALL try the
  next model in that provider's chain and record which one answered.
- **FR-5** IF a model returns `429`, THE SYSTEM SHALL stop that provider with a quota error and SHALL NOT
  try the next model.
- **FR-6** WHEN asked to pair a primary and a validator from the same vendor, THE SYSTEM SHALL raise.
- **FR-7** WHEN `gtaf llm-check` runs, THE SYSTEM SHALL report per provider: ok/failed, model used, tokens,
  cost, and the failure reason verbatim when it fails.
- **FR-8** THE SYSTEM SHALL never log or print an API key.
- **FR-9** THE SYSTEM SHALL compute cost with integer token counts and document the price table's date.

## 5. Price table

Prices change and model names churn, so the table is **data with a date**, not a constant buried in code.
Free-tier Gemini models price at 0 with a comment; DeepSeek uses its published per-million rates. `FR-9`
requires the arithmetic to be verified by a hand-worked test, because a wrong price is invisible — it just
produces a plausible number.

## 6. Boundaries

✅ Always: add a model to a chain with its price; improve a failure message.

⚠️ Ask first: changing a price; adding a provider; raising the default budget.

🚫 Never: retry a `429` on the same or another model; cache across different `prompt_version`s; log a
prompt containing corpus text at info level (hash it instead); let a same-vendor pair validate itself.

## 7. Testing

`tests/test_llm.py` with a fake transport: cache hit costs nothing, budget refusal sends nothing, fallback
on `404`/`503`, stop on `429`, vendor rule, cost arithmetic verified by hand, and that no key string ever
appears in a log line or an exception.

---

## Implementation Status

STATUS: COMPLETE
Implemented: 2026-11-14
Approved: 2026-11-14 (standing delegation)

### Files created

| Path | Purpose |
|---|---|
| `src/gtaf/domain/llm.py` | `ModelSpec`, price table with a check date, cost arithmetic, cache key, vendor rule, error types |
| `src/gtaf/infrastructure/llm_providers.py` | Gemini and DeepSeek transports, `.env` loader, status→error mapping |
| `src/gtaf/infrastructure/llm_gateway.py` | cache, cost metering, budget guard, fallback chain |
| `src/gtaf/infrastructure/repository.py` | `get_cached_call`, `store_call`, `spent_between` |
| `src/gtaf/cli.py` | `llm-check`, `llm-benchmark` |
| `tests/test_llm.py` | 17 tests, transport faked |

### Verification with evidence

```
Claim:     Lint, strict types and tests clean
Command:   ruff check src/ tests/ spikes/ ; mypy ; pytest -q
Exit code: 0 / 0 / 0
Summary:   All checks passed ; 35 files clean ; 179 passed
Verdict:   PASS

Claim:     Both providers answer a live call, with real token and cost numbers
Command:   gtaf llm-check
Exit code: 0
Summary:   gemini    ok  model=gemini-3-flash-preview tokens=7/1/49 cost=$0.000000 tier=standard
           deepseek  ok  model=deepseek-chat         tokens=11/1/12 cost=$0.000004
           spent this month: $0.000004
Verdict:   PASS

Claim:     Same Georgian task runs on both vendors and is recorded
Command:   gtaf llm-benchmark --limit 3
Exit code: 0
Summary:   6 responses; labels in docs/LLM-BENCHMARK.md
           2 of 3 labels near-identical across vendors; all valid JSON
Verdict:   PASS
```

### Deviations from the original spec

1. **The benchmark's output path is `reports/`, not `docs/`.** This machine's shell cannot write into
   `docs/` — the directory lacks the sandbox identity's ACE that `src/`, `reports/` and the others
   carry — so the first run failed with `PermissionError`. Generated artefacts therefore go to
   `reports/` (gitignored), and `docs/LLM-BENCHMARK.md` is hand-written analysis over them. This is also
   a better separation: `docs/` is authored, `reports/` is produced.
2. **Price table is data with a check date** rather than a constant, and free-tier models are marked so
   the budget guard can never block them.
3. **`estimate_tokens` divides by 2, not 4**, over-estimating on purpose: it feeds the budget guard, and
   refusing a call slightly early is cheaper than overshooting a cap.
4. **No `python-dotenv`**: a 12-line loader instead, because the format used here is two keys and
   comments (SPEC-005 §6).

### Lessons learned

- The first budget test passed for the wrong reason: the chain used *free* models, whose estimate is
  zero, so the cap could never trip. It now uses a paid chain, and a companion test asserts that a free
  model is permitted even at the cap boundary.
- Model names churn faster than specs: two of the four candidates probed were retired 404s within ten
  minutes of each other. A single hardcoded model would have shipped broken.
- Reasoning tokens make `totalTokenCount` the only honest number: "OK" reported 49 total against 8
  visible.

### Next

Topic labels can now be generated for the 30 clusters (SPEC-007) at zero marginal cost through Gemini;
SPEC-014/015 then have human-readable topics to work with. The benchmark should be re-run at 30 segments
before any report cites a label quality claim.
