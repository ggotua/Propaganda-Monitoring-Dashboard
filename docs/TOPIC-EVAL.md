# TOPIC-EVAL — M1 topic modelling (SPEC-007)

Status: **complete for the first slice** (2026-11-13). Corpus: 2,355 fixed-window segments from 263
videos, 9 days, one channel. Numbers below come from the commands recorded at the end.

---

## 1. Model selection (SPEC-007 §2)

600 segments, identical parameters (`min_topic_size=15`, UMAP seed 42), Georgian stopwords + `max_df=0.4`:

| model | topics | outlier rate | median size | largest | seconds |
|---|---|---|---|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2` (384-d) | 11 | 30.0 % | 33 | 77 | 28.1 |
| `paraphrase-multilingual-mpnet-base-v2` (768-d) | 8 | **22.8 %** | 66 | 95 | 53.6 |

**Chosen: mpnet-base**, on the spec's primary criterion (lowest outlier rate), at ~1.9× embedding time.
Recorded as D-020.

**The first run, before stopwords, was worthless and proved the point.** Every cluster's top terms were
`და, რომ, ეს, არის, ამ, არ` — "and, that, this, is, this, not". The model was clustering Georgian
*grammar*, and 30 % of segments were "outliers" because they were grammatically unremarkable. Adding a
conservative stopword list plus a document-frequency ceiling (`max_df=0.4`) turned the same pipeline
into subject clusters. Nothing else changed.

**A flaw in this evaluation, disclosed:** the 600-segment sample was `ORDER BY segment_id LIMIT 600`,
which sorts by video id, so it drew from a small number of videos rather than across the corpus. That
is why the outlier rate measured here (22.8 %) is much better than the full-corpus rate (38.6 % below).
The model comparison is still usable — both models saw the same biased sample — but the *absolute*
22.8 % was not representative and should not be quoted.

## 2. Full-corpus run

`gtaf topics` over all 2,355 segments, mpnet:

| metric | value |
|---|---|
| segments clustered | 2,355 |
| topics discovered | 30 |
| outliers (`topic_id = -1`) | **910 = 38.6 %** |
| coverage (clustered share) | 61.4 % |
| method version | `bertopic-paraphrase-multilingual-mpnet-base-v2-1` |
| LLM cost | **0** (labels are keywords; SPEC-005 gateway does not exist yet) |

Largest topics and their top terms (Georgian, verbatim):

| topic | n | top terms | reading |
|---|---|---|---|
| t0 | 168 | ვიზიტი, ურთიერთობების, სავაჭრო, სტრატეგიული, ჩინეთი, ჩინეთში | China state visit / strategic trade |
| t1 | 100 | პაციენტი, გულის, ტკივილი, ექიმი, დაავადების, კვლევა | patients, cardiac care, doctors |
| t2 | 98 | ევროკავშირი, დიალოგი, ევროპა, ამერიკის, რუსეთს | EU / US / Russia diplomacy |
| t3 | 81 | სააკაშვილი, გია, სამხედრო, ვუთხარი | Saakashvili, reported speech |
| t4 | 79 | მილიონი, ბიუჯეტი, სოციალური, 000 | municipal budget |
| t5 | 76 | დუბლინში, პოლიტიკური გაერთიანების, ლიდერები, სამიტი | Dublin summit |
| t6 | 67 | საკონსტიტუციო სასამართლოს, კონსტიტუციური | Constitutional Court |
| t7 | 64 | ბავშვის, მამა, მშობლები, დედის | children and parents |
| t8 | 51 | პარტია, ნაციონალური, 2012, აიკრძალა | party bans |
| t9 | 51 | მოსარჩელე, სარჩელის, მოსამართლე | plaintiffs, judge, proceedings |
| t10 | 51 | გაიხარეთ, გილოცავთ, უღრმესი მადლობა, ბელგიაში | **greetings and thanks — a format, not a subject** |

## 3. Validity review — the three questions, answered

**Q1. Do topics track bulletin structure rather than agenda?** **Partly yes.** 29 of 30 topics describe
subjects. **t10 is a format cluster** — greetings, congratulations, "deepest thanks", a location tag —
51 segments (2.2 % of the corpus) that share etiquette, not content. A user reading "greetings" as a
topic would learn nothing about coverage. It must be excluded from any agenda chart, or renamed as a
format bucket and shown separately.

**Q2. Does ASR noise become the signal?** **Yes, in the labels.** t3's keywords include `მარრა` and
`იქა`, which are not words; t4's includes `000`, an artefact of spoken numerals. These do not define the
clusters (the clusters are real: Saakashvili, the budget), but the *labels* are contaminated. Until
SPEC-005 provides LLM labels, every keyword label must be read as evidence of a cluster's content, not
as a topic name — which is exactly what SPEC-007 §1 forbids presenting.

**Q3. Is the outlier rate doing the work?** **Yes, badly enough to constrain every claim.** 38.6 % of
segments are unclassified. A sentence like "topic t0 is 7 % of coverage" describes 61 % of the corpus,
not all of it. Every share must be reported with the outlier rate beside it, and shares must never be
normalised to 100 % without saying so. This is the single most important caveat in this document.

**A fourth, unpredicted finding:** the outlier rate nearly doubled between the 600-segment evaluation
sample (22.8 %) and the full corpus (38.6 %). The cause is sample bias (§1), and it is a warning about
this whole class of evaluation: a convenience sample produced a number 16 points optimistic.

## 4. What may and may not be claimed from this run

**May be claimed:** the method works end to end; clusters correspond to recognisable subjects; cost is
zero; results are deterministic and reproducible.

**May not be claimed:** any agenda share as a property of a channel's output; any cross-channel
comparison (one channel only); any trend (9 days); any topic label as a human-meaningful name.

## 5. Reproduction

```
python spikes/topic_model_eval.py                 # model comparison, writes .tmp/topic_eval.json
python -m gtaf topics --top 12                    # full corpus, persists to topics/res_topics
```
