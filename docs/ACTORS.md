# Actors — seed dictionary (SPEC-011)

Status: **provisional seed**, 2026-11-20. Fifteen public figures who appear in Georgian political
coverage. This is not a complete list and does not claim to be: it exists so the matcher has something to
match, and so the *format* is fixed before the list grows.

Why a dictionary rather than a model: the measured ASR failures are concentrated in names
(`დიჰმის` for `დირჰამის`, split names like `ნურმა გომედოვი`, dropped suffixes — D-028). A dictionary with
fuzzy matching handles those explicitly and can be audited; a black-box NER model would produce confident
output that nobody can check line by line.

## Format

```yaml
- id: saakashvili              # stable key, used in output and joins
  ka: სააკაშვილი              # nominative form as written in text
  en: Saakashvili             # English rendering for the report
  role: ex-president          # short descriptor, not a claim
  aliases: [მიხეილ სააკაშვილი]  # optional extra forms
```

- `ka` is the **nominative** surname; the matcher derives inflected forms itself.
- `aliases` hold full-name and alternative spellings as they appear in captions.
- `role` is a label for the reader, never used in analysis.

## Maintenance

Add a name when it appears in a report. Do **not** add a name because it might be interesting: every entry
is a claim that this person is worth tracking, and a list that grows without a rule becomes an editorial
choice disguised as data.
