# Pre-registration: value and quality from as-published annual reports

**Status: APPROVED by the owner on 2026-10-06 and in force from this commit.** Drafted 2026-09-26; the owner's
decisions of 2026-10-04 and 2026-10-05 are recorded below. Nothing in it may change after this commit.
No result exists: the reports are still being collected (426 of 1,056 company-years on disk, 2026-10-06),
and the reports read so far were used only to build the figure reader, never joined to returns.

## The question, and what it is not

Among the most-traded NSE stocks, 2012–2026, do stocks that the app's **value**
and **quality** formulas rank highest beat the ones they rank lowest? The formulas
are fed only with accounts **as first published**.

It is not a test of the live scores. Those read Yahoo's current data and three
sector peers Yahoo picks today, and neither can be rebuilt for a past date. It
tests the app's formulas with the inputs that can be rebuilt. The table says
exactly which parts that is.

| App input | In this test | Why |
|---|---|---|
| P/E, P/B | Yes, from report profit and equity, and price at formation | |
| Three sector peers for P/E and P/B | **No**: the app's own fallback constants instead (P/E 22 ± 8, P/B 3.2 ± 1.5) | Peers chosen by Yahoo today cannot be rebuilt for past dates |
| ROE | Yes | |
| Piotroski points 1–4 (ROA > 0, CFO > 0, ROA > 5%, CFO/assets > ROA) and 9 (revenue growth) | Yes | |
| Piotroski point 7 | Counted as 1 for every stock, as the app does | |
| Piotroski points 5 (leverage), 6 (current ratio), 8 (gross margin) | **No** | Debt reads are unreliable; current ratio and gross margin are not extracted |
| | | **Known difference from v1.5.0 (owner, 2026-10-05):** v1.5.0 scores point 5 from the balance sheet's long-term debt. This test keeps it at 0 for every stock, because the reader's debt figures are unchecked. The result therefore tests v1.5.0's quality formula with point 5 removed, and is reported that way. |
| Free-cash-flow yield | **No**, dropped and the weights renormalised, as the app does when it is missing | Capital expenditure is not extracted |
| Distress: negative equity, loss-making, negative operating cash flow | Yes | |
| Distress: interest coverage | **No** | Not extracted |

## Scores, computed exactly like this

All money in Rs crore. "Profit" is profit for the year after tax, including discontinued operations.

**Value.**
- P/E = market cap / profit. P/B = market cap / total equity.
- Market cap = closing price on the formation day (as printed in the archive) x shares.
- Shares = share capital / face value. The face value is the one the reader's face-value check confirmed. Shares are adjusted for splits and bonuses in the stored corporate actions between the year end and the formation day.
- A P/E or P/B that is zero or negative is dropped. If both are dropped, the score is -0.5, as in the app.
- raw = -0.6 x (P/E - 22) / 8 - 0.4 x (P/B - 3.2) / 1.5. A dropped leg sits at its constant, as in the app.
- Value score = tanh(raw / 2).

**Quality.**
- ROA = profit / total assets. ROE = profit / total equity. ROE is not computed when equity is not positive.
- F = [ROA > 0] + [CFO > 0] + [ROA > 0.05] + [CFO / total assets > ROA] + 1 + [revenue > last year's revenue].
- The three points that can't be computed are 0 for every stock, as the app scores a missing input. **DECIDED (owner, 2026-10-04): kept**, so the test checks the formula the app actually uses.
- raw = (0.4 x F / 9 + 0.4 x ((ROE - 0.12) / 0.08) / 3) / 0.8. Without ROE, raw = F / 9.
- Distress penalties: negative equity 0.5, loss-making 0.25, negative operating cash flow 0.25. If any apply, raw = min(raw, 0) - total penalty.
- Quality score = tanh(raw).

## Data rules

- **Accounts:** standalone statements, read by `research/ar_extract.py`. A figure is used only if it is:
  - verified by the reader's own checks (balance sheet totals agree; profit, EPS and share capital give a real face value); or
  - accepted by `research/ar_review.py` (the quoted line is on the cited page, and either the checks pass or two independent readers agree).
- **Missing data:** a figure that isn't accepted is missing. It is never filled with zero or estimated. A company-year missing an input is left out of that score for that year, and every exclusion is counted.
- **When accounts count as public:** accounts for the year ending March Y are used from the first trading day of **January Y+1**, nine months after the year end.
  - The Companies Act 2013 (s.96) sets the AGM within six months, but the Registrar can extend that by three months, and the deadlines were extended for everyone in 2020 and 2021.
  - A six-month lag could therefore use accounts before they were public; nine months cannot. The cost is that the accounts are three months staler.
  - For other year ends, use the first month-end at least nine months after the year end.
- **Universe:** portfolios are formed at each month-end from January Y+1 to December Y+1. The candidates are the securities ranked in the top 100 by traded value in financial year Y (April Y-1 to March Y), from the stored point-in-time archive.
  - At formation, both the ranking and the accounts are in the past.
  - Funds and ETFs are excluded.
  - Companies that later stopped trading stay in.
- **Financial companies** (banks, lenders, housing finance, insurers): excluded from both tests. **DECIDED (owner, 2026-10-04): excluded.** Their revenue, operating cash flow and assets don't mean what these formulas assume. The list, and how each company was classified, is committed before the run.
- **Returns:** the same machinery as factor test 1 (`backend/modules/pit_validation.py`):
  - the NSE end-of-day archive, adjusted for splits, bonuses and dividends;
  - ISIN identity joins;
  - a security with no price at the end of a holding period counts as -100%;
  - "net of the market that month" means net of the equal-weighted mean return of the stocks scored that month,
    the convention factor test 1 uses (stated at commit, 2026-10-06, so nothing is left implicit).
- **Period:** formation months January 2013 to the last month whose holding period ends inside the archive. The archive ends when NSE collection was paused on 2026-09-08.

## Hypotheses

At each formation month, scored stocks are split into 5 equal groups by score. A month with fewer than 50 scored stocks is skipped. The statistic is the mean, across formation months, of the top group's return minus the bottom group's, each net of the market that month.

- **Primary (8):** value and quality, each at 1, 3, 6 and 12-month holding, as in factor test 1. **DECIDED (owner, 2026-10-04): all four horizons.**
  - The draft had proposed 12 months only. The owner chose all four, accepting the cost stated in "Power" below: the significance level is split eight ways, so a real effect is harder to detect.
- **Secondary:** none.
- **Standard error:** Newey-West with lag h - 1 for an h-month holding period, because the holding periods overlap.

## Decision rule

- **Primary:** a significance level of 0.05 / 8 = 0.00625 each (Bonferroni), for all eight tests.
- **Demonstrated edge:** a positive mean spread and a p-value below the level.
- **Reversed:** a significant negative spread. Not an edge.
- **No demonstrated edge:** anything else. It means the data did not show one, not that none exists.
- **Insufficient data:** if fewer than 80% of eligible company-years have every input accepted, the tests are not run. Coverage is always reported separately for companies still trading and those that stopped, because a gap there is survivorship bias.

## Power, stated before the result

About 100 stocks, fewer after the exclusions, is a small sample for these factors.
- Our earlier estimate was a standard error of about 0.6% a month on the spread, against an academic value premium of about 0.7% a month.
- So a real, ordinary-sized premium would most likely be reported as **no demonstrated edge**.
- Testing eight horizons at 0.00625 each, rather than two at 0.025, makes this worse: the smallest detectable spread is larger. This was a deliberate choice for completeness (owner, 2026-10-04).
- The runner reports the smallest spread this test could have detected (80% power at the primary level), computed from the realised volatility.
- A null result will be described with that number beside it, never as "value does not work".

## Reported but not tested

- **Placebo:** the same run with scores randomly shuffled within each month, 200 times. This shows the machinery gives about zero when there is nothing to find. It is also run first, as the plumbing check.
- **Single measures:** book-to-price, earnings-to-price and ROE, each sorted alone. Exploratory: they help separate "the idea works but our formula does not" from "neither shows anything". Never a finding.
- Coverage, exclusions, and the number of stocks per group each month.

## Commitments

- The runner (`research/value_quality_test_run.py`) is committed before it is run with real scores. Only the placebo run may come before that.
- One run. Every result is reported: edge, reversed, none or insufficient data.
- No change after the numbers are seen to the formulas, universe, period, availability lag, exclusions, groups, horizons or thresholds.
- A technical failure is rerun once with identical settings, and recorded.
- **The frozen model is not changed by the result.** Any change goes through a written proposal and a new version (AGENTS.md rule 3).

## Decisions (owner; the plan as a whole approved 2026-10-06)

1. **Missing Piotroski points:** zero for every stock, as the app does. Chosen so the test checks the app's real formula.
2. **Financial companies:** excluded from both tests (banks, lenders, housing finance, insurers).
3. **Horizons:** all four (1, 3, 6 and 12 months) are primary, eight tests at 0.05 / 8 each. The draft's 12-month-only proposal was not taken.
4. **Piotroski point 5 (owner, 2026-10-05):** stays 0 for every stock, even though v1.5.0 now scores it from the balance sheet. Recorded as a known difference (see the input table).
5. **The plan as a whole (owner, 2026-10-06):** approved. The owner alone approves this app's plans.
