# Step 5 — Portfolio Lab

First run 2026-09-09, re-run and corrected 2026-09-10 against production
(https://quant-india.onrender.com). Read-only throughout: every endpoint tested
computes and returns, none writes. V1.4 untouched. No fixes made — each finding
below changes endpoint behaviour and is proposed for a decision.

## Scope

Portfolio Lab is where the app stops describing the market and starts telling
someone what to do with money. The failures that matter here are not crashes;
they are answers that look reasonable and are not.

Tested: the API behind the Portfolio Lab pages — `/portfolio/build`,
`/portfolio/scenarios`, `/portfolio/shock`, `/portfolio/suggest-fix`,
`/portfolio/fit`, `/portfolio/what-if`, `/optimizer/stability`.

**Not tested:** `/portfolio/add` and `/portfolio/advise` require sign-in, and the
Portfolio Lab pages themselves need an account to open. I will not create an
account or enter credentials, so those need a human.

Harness: [step5_portfolio_lab_audit.py](step5_portfolio_lab_audit.py), results
in [step5_results.json](step5_results.json).

## What works — and some of it is very good

| Area | Result |
|---|---|
| Guided build | 5 names, all positive, sums to ₹100,000, largest position 40% |
| Loss-limit verdict | agrees with its own downside at 5%, 20% and 60%; at 5% it says plainly the portfolio is "MORE than the 5% you said you could accept" |
| Scenario arithmetic | all 6 outcome blocks coherent (worst-5% below median, both percentages match their rupee values); all 5 deltas equal after minus base |
| Market shock | a −20% Nifty shock is reported as −20.0%, never a gain |
| suggest-fix on a 95/5 portfolio | 4 concrete steps, labelled "Highly concentrated", reports median, downside and loss probability |
| Honest limits | suggest-fix says outright: "With 2 holdings, the most even split possible is 50% each — so no re-weighting can get any position under 25%. This portfolio needs more names, not different weights." |
| fit on a priceable stock | INFY judged on correlation, sector and concentration |
| Refusals | what-if refuses an empty portfolio, two nonexistent tickers, and SMALL250 (one of the securities the scan cannot price) |
| Optimiser fragility | an unconstrained 100%-in-one-stock result is flagged: "That is not robustness" |
| JSON | no bare NaN or Infinity in any response |

## Findings, most harmful first

### 1. The portfolio shown is not the portfolio simulated

| Holdings sent | Weights shown | Base return | Same portfolio without the bad ticker |
|---|---|---|---|
| RELIANCE 50%, **ZZZQQQ123** 50% (does not exist) | RELIANCE 50, ZZZQQQ123 50 | 2.19% | 100% RELIANCE: **2.19%** |
| **RELIANC** 50% (a typo), TCS 50% | RELIANC 50, TCS 50 | −11.18% | 100% TCS: **−11.18%** |

No warning field, no note, nothing in the response says half the portfolio was
ignored.

**Mechanism.** In `backend/modules/monte_carlo.py`, `_portfolio_daily_returns`
(line 66) fetches a price series per ticker; a ticker with none never enters the
frame (120–124). Line 130 keeps only tickers that have prices, line 132
renormalises the survivors back to 100%, and nothing records what was dropped.
Meanwhile `_norm` in `backend/modules/portfolio_scenarios.py` (21–23) keeps the
unpriced ticker in the displayed weights.

**Why it ranks first.** A typo is the mistake users actually make. The answer to
it is a precise downside figure for a different portfolio, with no sign that
anything happened.

The same endpoint refuses SMALL250 outright, so the handling is asymmetric. The
likely reason is that a ticker returning a sparse series empties the shared
`.ffill().dropna()` frame and forces an error, while a ticker returning nothing
never enters the frame at all — an inference, not traced.

### 2. Scenarios presents alpha-picked stocks as a free lunch

| Scenario | Stocks added | Return | Downside |
|---|---|---|---|
| Add GAYAPROJ at 15% (alpha +72) | GAYAPROJ | **+8.11** | **+6.94** |
| Diversify to 6 stocks | GAYAPROJ, DCBBANK, SPARC | **+9.39** | **+7.15** |

Both suggestions improve return **and** downside at once. The added names come
from `_candidates_not_held` (`portfolio_scenarios.py:56`): the highest-alpha buys
in the scan. "Diversify to 6 stocks" never mentions that — its explanation is
generic diversification.

**The improvement is circular.** 34.58 of GAYAPROJ's 72.26 alpha points are
momentum: it was selected for strong past returns. The simulation is a
bootstrap of past returns. A stock chosen for good past returns will look good
when its future is resampled from those same returns. The "improvement" is the
selection, replayed.

**The app contradicts itself.**

- `backend/modules/portfolio_fix.py:201` — "The app does not pick which — that would be a forecast."
- `backend/modules/portfolio_fit.py:151` — "Whether this stock beats the market is a prediction, and the track record has not shown the model can make one."
- `/alpha/explain` on GAYAPROJ — "it has no proven historical alpha"; Fama-French finds no significant alpha (r² 0.0165).
- The scenarios response's own guidance (`portfolio_scenarios.py:160`) — "Most improvements are trades — a little expected return given up for a smaller loss".

The only caveat is page-level: "Simulated from past returns. Not a prediction,
not financial advice." This belongs with the agreed UI-honesty work — it is the
STRONG BUY problem again, inside Portfolio Lab. Fixing it is a presentation
decision, not a model change.

### 3. "Stable" for weights that are pinned in place

With `max_weight=0.4`, the optimiser returns RELIANCE 40, HDFCBANK 40, INFY 20,
TCS 0. Three weights sit exactly on a bound (the 40% cap or zero) and the fourth
is the remainder — nothing can move, and across 20 perturbed trials nothing does.
The verdict: **"Stable… driven by the covariance structure rather than by return
estimates."** The constraint is driving it, not the covariance.

**Source.** `backend/modules/optimizer_stability.py` line 113 treats a result as a
corner only when `top_weight > 90`; otherwise line 121 calls anything with a
mean shift under 2 points "Stable". `corner_solution` (143) has the same blind
spot. The author's own comment beside that code: "A corner solution does not
move, and calling that 'stable' is the most dangerous thing this function could
say."

And the unconstrained verdict's advice — "Set a maximum weight per stock" — is
exactly what produces the capped corner that then gets called Stable.

### 4. fit claims overlap it never measured

SMALL250: HTTP 200, `fit_score` 50.2, and the verdict "Adds little
diversification. **It overlaps with what you hold**, so it mostly increases an
existing bet." The only component present is `concentration` (health 50.0 → 50.1).

**Source.** `portfolio_fit.py` adds a correlation component only when correlation
can be computed (89–101), then picks a verdict from the average of whatever
components exist (127–136). A lone, near-neutral concentration score lands in
the 45–70 band, whose wording asserts overlap. The honest branch — "Not enough
data to judge fit." (127–128) — is unreachable whenever concentration computes,
which is always. `what-if` refuses this same security.

### 5. A negative holding vanishes without a word

RELIANCE −50,000 beside TCS: HTTP 200, weights shown TCS 100%. `_norm` drops
non-positive values (`portfolio_scenarios.py:23`). Display matches simulation,
but nothing tells the user RELIANCE was discarded.

## Worth knowing, not a defect

The stated loss limit grades the portfolio but does not shape it. With the risk
profile held at "balanced", the build returned the same downside (−10.09%) at
loss limits of 5%, 20% and 60%. The verdict is honest about the mismatch at 5%
and says what to change, so this is a product question rather than a bug.

## A defect in yesterday's universe filter, found during this step

Today's natural cycle (2026-09-10) ran with the filter: **2,713 attempted, 2,706
scored, 4 failed.** It worked on its first real cycle.

**It will not keep working.** The live exclusion count fell from **182 to 4**
overnight. The rule (`backend/modules/universe_scan.py:885–925`) looks at the
last 3 distinct cycles and excludes a ticker only if it failed with no market
data in all 3. An excluded ticker is not attempted, so it writes no row. The next
cycle enters the window with no failure recorded for it, it drops to at most 2 of
3, and it is re-admitted. Tomorrow's scan will re-attempt about 178 of the 182.

For a permanently dead ticker the pattern is: excluded for one cycle, then
re-attempted and failing for three, then excluded again — about one day in four.

- **Harm to outputs: none.** Every consumer already filters `alpha_score IS NOT
  NULL`. The filter just stops saving time and the failure count comes back.
- **A dependent defect:** the scan-failure audit now lists excluded tickers
  (3BBLACKBIO, AASTHA, ABMKNO…) as "recovered_today". They were not recovered;
  they were not attempted.
- **Why the 16 tests missed it:** every fixture was a static history. None
  modelled a ticker being excluded and therefore absent from the next cycle.
- **Minor, unexplained:** scan status reports 2,713 done while the rows total
  2,710 (2,706 + 4). Not investigated.

## Corrections to the 2026-09-09 report

- **"Negative holdings are accepted — simulates fine in a long-only tool" was
  wrong.** The negative position is dropped from both the displayed weights and
  the simulation (finding 5). It is not simulated as a short.
- **The first harness made five mistakes:** it failed suggest-fix for having no
  suggestions (they are under `steps`); failed it for hiding the return side (it
  reports `median_pct`); never ran its scenarios coherence check (the keys are
  `p5_value` and `median_value`, not `p5` and `median`); passed three bad-input
  checks that each sent one holding and were rejected for the count; and passed
  a concentration check that matched "95" in the echoed weights — what-if never
  mentions concentration at all. Two false failures, four vacuous passes, one
  silent absence.
- **A draft of the corrected harness only checked that stability's keys
  existed.** It passed with the least-stable weight moving 0.0%, which turned out
  to be finding 3. Replaced before archiving.

## Fixed the same day: findings 1, 2 and the universe filter

Commit `0d92399`, deployed 2026-09-10 17:17 UTC while the scan was idle.

- **Finding 1.** `simulate()` now refuses when any holding cannot be priced and
  names it; what-if and scenarios pass the refusal through. A failed fetch is
  never cached. Live: `{"RELIANCE.NS": 50000, "RELIANC.NS": 50000}` returns
  HTTP 400, "No price history could be fetched for RELIANC ... Nothing was
  simulated".
- **Finding 2.** Scenarios no longer adds stocks at all. "Add X at 15%" and
  "Diversify to N" are gone. For fewer than 8 holdings the page says more names
  cut risk most and that choosing them by score would be a forecast. "Drop X"
  now carries the no-track-record caveat. Live: 3 scenarios, all from current
  holdings.
- **Universe filter.** Each ticker is judged on its own last 3 attempts, so a
  skipped cycle no longer erases its failures. An excluded ticker is retried
  once its latest attempt is over 7 days old. Live exclusion count: **187**
  (was 4 under the broken rule). A 60-day forward simulation in
  `universe_filter_test.py` keeps a dead ticker out on 15 of 60 days under the
  old rule and fails it; the new rule passes.
- **Failure audit.** A ticker not attempted this cycle is counted as
  `not_attempted_today`, not as recovered. Live, cycle 2026-09-10 vs 09-09:
  182 not attempted, 2 recovered (APOORVA, LUMINO, both tried and scored),
  4 failed in both. The old code would have called all 184 recovered.
- **Why the full data-integrity call timed out.** Not a regression. Timed one
  domain at a time on 2026-09-11: identity 162 s, continuity 74 s, prices 66 s,
  missing_data 10 s, news 8 s, fundamentals_pit 2 s, scan_failures under 1 s.
  That is about 5.4 minutes in all, and the client gave up at 280 s. Use
  `?domain=` for anything interactive.

Every new check was run against the pre-fix code first and failed there.
Offline suites after the fix: unpriced_holdings 18/0 (new), universe_filter
24/0, data_integrity 109/0, core properties 81,215/0, stress 87,173/0.

**Harness re-run after the fix: 35 passed, 3 failed.** The three failures are
findings 3, 4 and 5, which were not in scope. Three checks apply only when
scenarios names a stock, and no longer run because it names none (an earlier
version of this note said four: 31 + 8 = 39 checks, minus 3, plus 2 new, is
38). The two new checks are that scenarios never adds an unheld stock and that
it advises more names without picking them. Both pass.

## Fixed 2026-09-11: findings 3, 4 and 5

- **Finding 3, stability.** A weight on a limit (the cap, or zero) cannot move.
  When every weight but one is on a limit and the mean shift is under 2
  points, the verdict is now "Held in place by the limits, not by the data",
  with `corner_solution` and `pinned_by_limits` true and the pinned tickers in
  `at_limit`. Weights that are free to move and do not are still "Stable";
  weights on limits that jump between corners are still "Unstable".
- **Finding 4, fit.** Without a correlation, the verdict no longer uses the
  three bands ("brings something", "overlaps", "doubling"), all of which
  describe co-movement. It says the stock was only partly judged, that there
  is not enough price history to measure how it moves with the holdings, and
  which components the score covers. `not_measured` lists what is missing. A
  priceable stock still gets a normal verdict.
- **Finding 5, negative holdings.** what-if (including an edited portfolio),
  scenarios and fit refuse a negative amount, name the holding, and simulate
  nothing. A zero in an edit still removes a stock.

`backend/tests/lab_findings_test.py` (new, offline): 20 of 28 checks failed on
the pre-fix code and all 28 pass after. The 8 that passed before are the
over-correction guards, which must pass both times.

## The first scan under the corrected filter (cycle 2026-09-11)

Started 00:09 UTC, finished 02:34. 187 tickers excluded, 2,709 attempted,
2,634 scored, 72 failed. The 4 that failed on 09-10 were excluded and not
attempted. One failure, INFRABEES, has no recorded reason.

The other 71 failures are new, all "No market data found", for stocks that do
trade. The five checked (ABANSENT, AKCAPIT, ALPINETEX, BI, BIRLAPREC) each
scored on the four previous cycles, and Yahoo returned prices for ten of the 71
at 05:05 UTC the same morning. This looks like a one-night source failure. The
filter needs three consecutive no-data attempts, so none is excluded. If the
same names fail again on 09-12 and 09-13 they would be excluded for a week, and
the rule would need a guard against a source outage, such as making no
exclusions from a cycle whose failure count jumps.

## The audit harness

**31 passed, 8 failed** on the first 2026-09-10 run, before the fixes above. Every failure is one of the
findings above, and every check asserts on the response shape the endpoint
actually returns rather than a guessed key name.

| Checks | Result |
|---|---|
| Guided build; loss-limit verdict at 5%, 20%, 60% | all pass |
| Scenario arithmetic; shock sign | all pass |
| suggest-fix: steps, concentration label, both outcomes, honest two-stock limit | all pass |
| Scenarios disclose why alpha-picked additions improve both axes (2) | **fail** — finding 2 |
| suggest-fix and scenarios agree on whether naming a stock is a forecast | **fail** — finding 2 |
| fit uses correlation for a priceable stock | pass |
| fit never claims overlap without measuring correlation | **fail** — finding 4 |
| what-if refuses empty, two nonexistent, and SMALL250 | all pass |
| what-if shows the portfolio it simulates: fake ticker, typo (2) | **fail** — finding 1 |
| Negative holding: display matches simulation | pass |
| Negative holding refused or explained | **fail** — finding 5 |
| Stability: unconstrained 100% corner flagged | pass |
| Stability: capped corner not called stable | **fail** — finding 3 |
| JSON a browser can parse, on all 10 calls | all pass |

The harness exits 1 while any finding stands. It makes live requests, so it is
kept here beside its results rather than in `backend/tests/`, whose suites run
offline.

## Proposed fixes, for a decision

1. **Unpriced holdings (finding 1):** have the simulation return the tickers it
   could not price; refuse, or disclose prominently, whenever any holding is
   unpriced; never renormalise silently.
2. **Scenarios (finding 2):** either stop naming stocks, consistent with
   suggest-fix, or label alpha-picked additions as such with the track-record
   caveat beside the numbers. V1.4 is untouched either way.
3. **Stability (finding 3):** count weights sitting on a binding cap or floor as a
   corner, and only call an allocation stable when its weights are free to move.
4. **fit (finding 4):** when correlation cannot be computed, say "Not enough data
   to judge fit" or refuse as what-if does — never the overlap wording.
5. **Negative holdings (finding 5):** refuse, or say what was discarded.
6. **Universe filter:** count a ticker's no-data failures over the last N cycles
   in which it was actually attempted, re-attempt excluded tickers on a fixed
   cadence (say weekly) so they can still recover, and make the failure audit
   distinguish "excluded" from "recovered". This changes the daily scan.

Findings 1 and 2 do the most harm to a user: one gives wrong numbers for a
typo, the other presents a forecast the app elsewhere refuses to make as a
measured improvement.
