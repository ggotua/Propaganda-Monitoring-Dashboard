# Web corpus: first findings

Corpus: **1,699 publications** from two outlets, 2026-11 to 2026-11-28 — Imedi (pro-government, 821) and
TV Pirveli (opposition, 611). Stance labelled by a language model (prompt `stance-v5`) toward nine named figures,
**283 labels**. Human agreement on the final checks: 12/12, then 20/20. See `D-043`, `D-044`, `D-045`.

## 1. Each outlet evaluates its own side favourably and the other side unfavourably

| Figures | Outlet | Publications | `critical` | `supportive` |
|---|---|---|---|---|
| Government figures (7) | Imedi (pro-government) | 107 | **0 (0.0 %)** | 4 |
| Government figures (7) | TV Pirveli (opposition) | 117 | **29 (24.8 %)** | 1 |
| Opposition figures (2) | Imedi (pro-government) | 37 | **26 (70.3 %)** | 1 |
| Opposition figures (2) | TV Pirveli (opposition) | 22 | **3 (13.6 %)** | 0 |

Government figures: Kobakhidze, Ivanishvili, Garibashvili, Mdinaradze, Papuashvili, Kavelashvili,
Bochorishvili. Opposition figures: Saakashvili, Zourabichvili.

The clean number is the first row: **Imedi published 107 items naming a government figure and the model found
not one critical evaluation among them**, while the opposition outlet carried 29 in 117. In the other direction
Imedi is sharply critical of Saakashvili (26 of 37) — so the model is not unable to label criticism, and the
outlet is not unable to publish it. The asymmetry is in *whom* the criticism is aimed at.

## 2. Per target

| Target | Outlet | supportive | critical | neutral | unclear | n |
|---|---|---|---|---|---|---|
| bochorishvili | pro-government | 0 | 0 | 26 | 0 | 26 |
| bochorishvili | opposition | 0 | 0 | 5 | 0 | 5 |
| garibashvili | opposition | 0 | 5 | 7 | 0 | 12 |
| ivanishvili | pro-government | 3 | 0 | 5 | 0 | 8 |
| ivanishvili | opposition | 1 | 9 | 6 | 2 | 18 |
| kavelashvili | pro-government | 0 | 0 | 9 | 0 | 9 |
| kavelashvili | opposition | 0 | 1 | 13 | 1 | 15 |
| kobakhidze | pro-government | 1 | 0 | 29 | 0 | 30 |
| kobakhidze | opposition | 0 | 12 | 34 | 4 | 50 |
| mdinaradze | opposition | 0 | 2 | 5 | 3 | 10 |
| papuashvili | pro-government | 0 | 0 | 34 | 0 | 34 |
| papuashvili | opposition | 0 | 0 | 4 | 3 | 7 |
| saakashvili | pro-government | 1 | 26 | 8 | 1 | 36 |
| saakashvili | opposition | 0 | 3 | 8 | 1 | 12 |
| zourabichvili | pro-government | 0 | 0 | 1 | 0 | 1 |
| zourabichvili | opposition | 0 | 0 | 10 | 0 | 10 |

## 3. What this is not

- **Not airtime.** These are website publications. Only Imedi has a broadcast corpus, and its concordance with
  the site was measured once: Spearman rho = 0.74 on 3–13 November (D-036). No such check exists for TV Pirveli.
- **Not a validated classifier.** G-8 agreement was measured on hand-checked samples: 28/30 exact and 20/20 on
  the final random draw, with `critical` recall measured at 4/5. `supportive` remains thinly measured (6 rows
  corpus-wide) and must not be reported as a rate.
- **Not a count of articles about these people.** Mentions require the name in the text; a strict first-name rule
  means a bare "ივანიშვილი" is only Bidzina when "ბიძინა", "ოცნების დამფუძნებელი" or "საპატიო თავმჯდომარე"
  appears nearby.
- **Not deduplicated across outlets.** Deduplication removes republication within one outlet, not syndication
  between outlets.

## 4. Open codebook question

Imedi calls Saakashvili "the convict". Under `stance-v5` this is read as legal status and labelled `neutral`.
If it should count as `critical` framing, the rule belongs in `docs/STANCE-RULES.md` and the prompt version must
change — which requires a fresh gate on a new holdout sample. Recorded, not changed: altering the prompt now
would invalidate the 20/20.
