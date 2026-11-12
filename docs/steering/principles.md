# principles.md — non-negotiable rules

Load-bearing, declarative, and short on purpose. If a change violates one of these, the change is
wrong or this file needs a deliberate decision entry — not an exception.

1. **If it is uncertain whether something is in scope, it is not.**
2. **No number reaches a report without a query a colleague can re-run.**
3. **Never guess a classification.** `NULL` / `unknown` is a valid, reportable answer; a plausible
   guess is not.
4. **A channel with poor data is caveated, never dropped.** Dropping one silently changes the
   research question.
5. **One writer.** Readers open read-only. A lock collision fails loudly and is never retried.
6. **No ambient state in a method.** Everything external arrives through the injected context (D-006).
7. **Never weaken an assertion, a CHECK or a threshold to make a test pass.** That hides the finding
   instead of resolving it.
8. **Migrations are append-only.** History is evidence.
9. **Absence is not evidence.** A module that is not installed is not a module that is incompatible;
   a probe that has not run has not found a negative.
10. **Every LLM-derived figure carries its validation figure and its agreement rate**, and the
    validator is always a different vendor (D-010).
11. **Secrets never appear in code, logs, config, prompts or commit messages.** Reference the
    environment variable, never the value.
12. **A document that looks finished is not approved.** Only the `.status` file authorises work.
13. **Attribute the decision.** Every non-obvious choice gets a `decisions.md` entry with its
    rejected alternatives and a revisit trigger, or it will be re-argued forever.
14. **Measurement before optimisation, and measurement before scoping.** If a claim lacks a command
    and an exit code behind it, it is a hypothesis, not a result.
