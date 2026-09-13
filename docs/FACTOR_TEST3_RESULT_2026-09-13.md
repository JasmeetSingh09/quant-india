# Factor test 3 result: the sentiment component reads headlines correctly

**Run:** 2026-09-13, 21:39–21:41 UTC, `python research/sentiment_test3_run.py`
on this project's own FinBERT copy. **Rules:**
`docs/PREREG_FACTOR_TEST3_SENTIMENT_2026-09-13.md`, pushed at 21:39:15 UTC
(`decf894`), before the run. **Raw output:** `docs/factor_test3_sentiment_result.json`.

## Verdict, by the pre-registered rules: **works**

| Measure | Result | 95% interval | Rule |
|---|---|---|---|
| Macro-F1 | **0.734** | 0.724 to 0.743 | Lower bound at least 0.60: **met** |
| Accuracy | **73.2%** | 72.2% to 74.1% | Lower bound at least 10 points above the baseline: **met (+36 points)** |
| Baseline: always "positive" | 35.9% accuracy, macro-F1 0.176 | | |
| Cohen's kappa | 0.60 | | Agreement beyond chance |

## The data

SEntFiN 1.0: 10,752 human-labelled Indian financial headlines (2002–2017,
Economic Times and Moneycontrol). **7,906 used**: 2,834 naming more than one
entity were excluded by rule, and 13 could not be read. The labels are balanced:
2,837 positive, 2,376 negative, 2,693 neutral.

## Where it goes wrong

Rows are what people said; columns are what the app's labelling said.

| People \ Model | positive | negative | neutral |
|---|---|---|---|
| **positive** (2,837) | **1,993** | 192 | 652 |
| **negative** (2,376) | 112 | **1,766** | 498 |
| **neutral** (2,693) | 328 | 341 | **2,024** |

| Label | Precision | Recall | F1 |
|---|---|---|---|
| Positive | 0.82 | 0.70 | 0.76 |
| Negative | 0.77 | 0.74 | 0.76 |
| Neutral | 0.64 | 0.75 | 0.69 |

- **Its main mistake is caution:** 1,150 headlines people called positive or
  negative were labelled neutral (23% of them). That dilutes a sentiment score
  towards zero rather than pointing it the wrong way.
- **Opposite-polarity errors, the damaging kind, are rare: 304 of 5,213 polar
  headlines (5.8%).** Good news called bad: 192. Bad news called good: 112.
- **Neutral is the weakest label:** 669 neutral headlines were given a tone.

## What this does and does not show

- **It shows** the component the app uses to read news tone agrees with people
  on most Indian financial headlines it was never trained on, and rarely gets
  the direction wrong.
- **It does not show** that sentiment predicts returns. That needs news as it
  was published on each past date, which the app never stored; it waits for the
  forward test from 27 December 2026.
- **It does not test** whether an article is matched to the right company, a
  separate step fixed on 2026-09-03.
- **The headlines are 2002–2017.** Today's financial news may be written
  differently.
- **SEntFiN shares an author with FinBERT's training data** (Financial PhraseBank),
  though not its headlines. Any shared annotation style would flatter the model.

## Not changed by this result

Sentiment's weight (10% in V2) and the evidence page's "cannot test yet" status
are unchanged. This test clears the component, not the factor.
