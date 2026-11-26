# Verification evidence

One block per claim, appended by `sdd_evidence`. Evidence is a record, not a summary of what someone believes happened: a completion claim does not survive stale evidence.

Never edit a block after the fact. Re-run the check and append a new block.

## SPEC-001 — YYYY-MM-DDTHH:MMZ
Claim:     [what is asserted]
Command:   [the exact command that proves it]
Exit code: [0, or the actual number]
Summary:   [what the output showed]
Verdict:   PASS | FAIL

## SPEC-018 — 2026-11-26T09:49Z
Claim:     The web corpus ingests from both channels' sitemaps and the stance model labels criticism of a government-side figure in an opposition outlet.
Command:   .venv\Scripts\python.exe -m gtaf ingest-web --source tvpirveli --sitemap --limit 120 --delay 0.4 ; .venv\Scripts\python.exe -m gtaf ingest-web --source imedi --sitemap --limit 120 --delay 0.4 ; .venv\Scripts\python.exe -m gtaf stance-web --target ivanishvili --limit 30
Exit code: 0
Summary:   Ingest stored 120 TV Pirveli and 120 Imedi publications (113 with text for Imedi, 120 for TV Pirveli, 0 failed, 0 robots-blocked), taking the corpus to 286. Stance labelling on Ivanishvili produced imedi(pro-government): critical 1; tvpirveli(opposition): critical 4, unclear 5, neutral 0, supportive 0. Kobakhidze produced 2 neutral in each source — too few to read.
Verdict:   PASS
