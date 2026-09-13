# Pre-registration: factor test 3 — does the sentiment component read headlines correctly?

**Written:** 2026-09-13, before the run. **Committed before any result exists.**

## The question, and what it is not

Does the app's sentiment component label Indian financial headlines the way
human annotators do, on headlines it was not trained on?

This tests the **component**, not the factor. It cannot show that sentiment
predicts returns: that needs news as it was published on each past date, which
the app never stored, and it waits for the forward test from 27 December 2026.
It also does not test whether the app matches an article to the right company;
that was a separate defect, fixed on 2026-09-03.

## The component, exactly as the app runs it

`backend/modules/sentiment.py`: the Hugging Face `text-classification` pipeline
with `ProsusAI/finbert`, all three scores returned, the text cut to its first
512 characters, and the label taken as **whichever of positive, negative and
neutral scores highest**. The runner loads the same model the same way.

## Data

- **SEntFiN 1.0** (Sinha, Kedas, Kumar and Malo, *JASIST* 2022), MIT licence,
  `github.com/pyRis/SEntFiN`: 10,752 headlines from The Economic Times and
  Moneycontrol, 2002–2017, about NSE-500 companies and other entities, each
  entity labelled positive, neutral or negative by people.
- **Only headlines that name exactly one entity.** In a headline naming several,
  the entities can carry different tones and the headline has no single correct
  label; the app scores whole headlines.
- **Not FinBERT's training data.** Its model card says it was fine-tuned on
  Financial PhraseBank (Malo et al., 2014), which is why that dataset was not
  used. SEntFiN shares an author, not headlines; any shared annotation style
  would flatter the model, so a pass is read with that in mind.

## Measures

- **Primary:** macro-F1 over the three labels, with a 95% bootstrap interval
  (2,000 resamples of headlines, seed 20260913).
- **Secondary:** accuracy with the same interval; Cohen's kappa; precision,
  recall and F1 per label; the full confusion matrix.
- **Baseline:** always answering the most common human label.
- **Reported separately, because it does the most damage in the app:** the
  share of headlines people called positive or negative that the model gave the
  **opposite** polarity.

## Decision rule, fixed now

| Verdict | Rule |
|---|---|
| **Works** | Macro-F1 lower bound at least **0.60**, and accuracy lower bound at least **10 points above** the baseline's accuracy |
| **Fails** | Macro-F1 lower bound below **0.40**, or accuracy lower bound not above the baseline |
| **Weak** | Anything in between |

The thresholds are a judgement made in advance, not a published standard: 0.60
macro-F1 is a three-label classifier that is clearly better than chance on every
label, and the 10-point margin rules out a model that mostly agrees by saying
"neutral" to a dataset that is mostly neutral.

## Commitments

- The run happens once. Every result is reported.
- The single-entity filter, the thresholds and the measures do not change after
  the numbers are seen.
- No other subset (by year, source, company or label) is reported as a finding;
  any such cut is labelled exploratory.
