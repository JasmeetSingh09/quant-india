# What V1 is

**Phase 0 record, written 2026-09-14 from the code at `aa4d2f9` and the frozen
specification stored on production.** It describes; it changes nothing. Where
the code and an older comment disagree, the code is described and the comment
is listed under "Stale claims".

## Three names that get confused

| Name | What it is | Where |
|---|---|---|
| **V1, the four-factor model** | Momentum, sentiment, quality, value. Produces every live score and Buy/Sell label, the nightly scan and Top Picks. Stamped `alpha-v4-distress-coverage` on each result. | `backend/modules/alpha_model.py` |
| **V2, the six-factor model** | V1's four factors plus growth and low risk, reweighted. Shown only on `/alpha/v2` and `/alpha/compare`, and read by some research tools. Stamped `alpha-v2-six-factor`. | `backend/modules/alpha_v2.py`; differences in `PHASE0_V1_V2_DIFFERENCES_2026-09-14.md` |
| **Specification v1.0–v1.4** | A hashed, dated record of the parameters of **both** models plus backtest, validation, cost, universe and portfolio settings. "V1.4 frozen" means this record. Its `model` field says six-factor because it names V2 as the model under study; V1's weights are recorded beside it. | `backend/modules/strategy_version.py`; stored in production, `GET /strategy/version/v1.4` |

## Specification history

| Version | Frozen (UTC) | Hash | What it is |
|---|---|---|---|
| v1.0 | 2026-08-25 07:52 | `e2a77417287e88e8` | First freeze, before the point-in-time backtest. Its capture silently missed min_holdings, the universe sizes, the rebalance frequency and the momentum definition. |
| v1.1 | 2026-09-01 14:43 | `1361629a4a524307` | Metadata only: low risk moved out of "not historically testable". |
| v1.2 | 2026-09-01 14:48 | `8b63feb433a98741` | **Retracted.** Frozen against a stale deployment; its notes claimed fields its stored spec did not contain. |
| v1.3 | 2026-09-01 14:55 | `f22f9044e049a6c7` | First complete record. Behaviour identical to v1.0. |
| **v1.4** | 2026-09-01 15:33 | `be3d21c31d9eec0d` | Current. Inline numbers promoted to named constants so the hash covers them; behaviour identical, proved by 339 recorded outputs. |

## What V1 computes for one stock

Every input is fetched **live** on the day of scoring: Yahoo prices, Yahoo
company information and statements, and news feeds. Nothing is point-in-time,
so V1 as a whole cannot be recomputed for a past date.

Each factor returns a score from −1 to +1 and a confidence from 0 to 1. A factor
that cannot be measured returns score 0, confidence 0 and a reason.

### Momentum, weight 35%

1. Download about 430 calendar days of Yahoo closes, adjusted for splits and
   dividends.
2. Fewer than 60 closes: score 0, confidence 0, reason "price data unavailable"
   (no closes) or "price history too short" (some closes).
3. Window: from 252 trading days ago to 21 trading days ago. The most recent
   month is skipped.
4. Return over the window, divided by annualised volatility of daily returns in
   the window.
5. Score = tanh(that ratio ÷ 1.5).
6. Confidence = 0.4 + 0.6 × (share of the 252-day window available).

This is the stock's own 12-1 return adjusted for volatility. It is not ranked
against other stocks.

### Sentiment, weight 25%

1. Headlines for the stock from the last 14 days.
2. FinBERT labels each headline positive, negative or neutral, with a
   confidence.
3. Each headline counts +confidence, −confidence or 0.
4. Weighted by recency with a 3-day half-life. An undated headline is treated
   as 7 days old.
5. Weighted average, then multiplied by confidence, where confidence =
   min(1, total weight ÷ 7). Few or old headlines pull the score toward 0.

### Quality, weight 25%

Three parts, each used only if its input exists, then reweighted over the parts
present:

| Part | Weight | Calculation |
|---|---|---|
| Piotroski score | 0.4 | F-score ÷ 9 |
| ROE | 0.4 | ((ROE − 12%) ÷ 8%) ÷ 3 |
| FCF yield | 0.2 | ((free cash flow ÷ market cap − 3.5%) ÷ 4%) ÷ 3 |

ROE and free cash flow come from Yahoo's summary, falling back to values derived
from the statements.

**Distress penalties.** Negative book value −0.5; interest cover below 1.5×
−0.25; a loss −0.25; negative operating cash flow −0.25. With any flag, the
score is first capped at 0, then the penalties are subtracted.

Score = tanh(result). Confidence = 0.85 × (weights of the parts present).

### Value, weight 15%

1. Trailing P/E and price-to-book from Yahoo. A non-positive multiple is dropped
   as distress.
2. Both dropped for distress: score −0.5, confidence 0.6. Both simply missing:
   score 0, confidence 0.
3. Compared with up to 3 sector peers: their mean and spread, with the spread
   floored at 1 for P/E and 0.5 for P/B. With fewer than 2 peers, fixed
   averages are used: P/E 22 ± 8, P/B 3.2 ± 1.5. A missing leg sits at the mean.
4. Score = tanh((−0.6 × P/E z-score − 0.4 × P/B z-score) ÷ 2).
5. Confidence = min(1, 0.5 + 0.1 × peers with a P/E), halved when only one
   multiple is usable.

### The composite

- **Alpha score** = 100 × (0.25 × sentiment + 0.35 × momentum + 0.25 × quality
  + 0.15 × value), from −100 to +100. An unmeasured factor contributes 0; the
  other weights are **not** scaled up to replace it.
- **Refused** when momentum has no confidence **and** Yahoo has no market cap:
  - with a short price history, "No market data found … fewer than 60 days of
    prices and no market cap";
  - otherwise, "No market data found … Check the symbol".
- **Labels.** Strong Buy above 40; Buy above 15; Strong Sell below −40; Sell
  below −15; otherwise Neutral. The comparisons are strict.
- **"Confidence"** is the weighted data coverage, labelled "Data coverage". It
  is not a probability of being right.
- **Stated horizon:** about 21 trading days. Not a long-term view.

## Where V1 is used

- **The nightly universe scan** (`universe_scan.py`) scores every eligible NSE
  stock with `compute_alpha_score` and stores the results.
- **Cap tiers** are by market-cap rank only: 1–100 large, 101–250 mid, 251 and
  below small.
  - `LARGE_CAP_MIN` (Rs 1 lakh crore) and `MID_CAP_MIN` (Rs 33,000 crore) are no
    longer used to classify. They are kept for older stored rows.
  - They are still captured in the frozen record's `universe_rules`.
- **Top Picks and the stock pages** (`/alpha/score`, `/alpha/explain`) show V1
  scores and labels.

## Portfolio and risk settings in the frozen record

| Setting | Value |
|---|---|
| Risk-free rate | 6.5% a year (`model_config.RISK_FREE_RATE`) |
| Benchmark | Nifty 50, `^NSEI` |
| Trading costs | brokerage 0.03%, STT 0.1%, stamp duty 0.015%, exchange 0.00345%, GST 18% on brokerage and exchange; 0.415% per unit of turnover |
| Portfolio limits | one stock at most 25%, one sector at most 40%, at least 5 holdings |
| Point-in-time backtest | 0.4% round trip, 12-month lookback, 1-month skip, at least 5 holdings, Rs 1 crore monthly turnover floor |

**Not yet frozen as one definition: Sharpe and Sortino.** Four modules compute
Sortino four different ways, and two compute Sharpe differently. The same
portfolio gets different figures on different pages. Evidence and a proposed
fix are in `PHASE2_FINDINGS_2026-09-14.md`.

## Known defects V1 carries

These are recorded, not fixed, because changing them changes V1.

- **Piotroski tops out at 7, not 9.** F4 and F5 read total assets and leverage
  from Yahoo's summary, which never has them for NSE stocks, so both are always
  0. F7 (no dilution) is always 1. The statements already fetched do hold those
  inputs.
- **Nothing is point-in-time.** Fundamentals, peers and news are today's.
- **Sector peers come from today's sector map.**
- **News matching:**
  - On 2026-09-09, 148 market-wide headlines were each scored for more than 5
    companies. Google News results skip the relevance check that the general
    feed's results pass through.
  - "state bank" can match banks other than SBI. That was confirmed in the code
    on 2026-09-09, but no article matched that day.
- **Degraded nights.** The scans of 2026-09-11, 12 and 13 ran with most company
  data missing (`docs/degraded_cycles.json`).

## Stale claims in the code

The code's own comments say things the code does not do. Correcting them is
text only, but it is a backend change, so it waits for approval.

- **Momentum is described wrongly.** `alpha_model.py` lines 16–21 describe it as
  a rank among NSE peers from 1-, 3- and 6-month returns. The code computes the
  stock's own 12-1 return adjusted for volatility. The docstring of
  `_compute_momentum_factor` records why it replaced the sector-relative
  percentile.
- **The weights were not fitted, as far as the repo shows.** Lines 29–30, 60–61
  and 795 say the weights were fitted by regression on 2019–2022 data and
  validated on 2023–2024. The weights 0.25 / 0.35 / 0.25 / 0.15 have been
  unchanged since the repository's first commit (`b2c6360`, 2026-06-22), and
  `retrain_weights` never writes them. The claim appears in code and API
  docstrings, not on the website.
- **"Research" figures are unconfirmed.** Quality's constants (ROE 12% ± 8%, FCF
  yield 3.5% ± 4%) are described as "derived from our research on NSE
  2019–2024". No such study was found in the repo.

## What the drift check reports today

`GET /strategy/drift/v1.4` says behaviour has drifted. Neither item comes from
a change to V1's scoring:

1. **The archive start date.** The frozen value is 2024-01-01; production now
   has 2011-07-04. The archive was extended backwards.
2. **`scan_complete_fraction`** (0.9) is now captured but was not recorded in
   v1.4.

**Decision needed:** record both as documented operational changes, or freeze
v1.4.1.

## Evidence so far

| Part | Status | Source |
|---|---|---|
| Momentum as V1 computes it | Demonstrated edge, 2011–2026, mostly outside the most liquid third | `FACTOR_TEST1_RESULT_2026-09-13.md` |
| Sentiment component | Reads headlines correctly (macro-F1 0.73) | `FACTOR_TEST3_RESULT_2026-09-13.md` |
| Quality, value | No lead, approximate test | `FACTOR_TEST2_RESULT_2026-09-13.md` |
| Composite score and labels | Untested; needs the forward record | from 2026-12-27 |

## Rule for changing V1

Any change to a behavioural parameter is a new specification version, with
notes saying what changed and why, frozen before any result it is used for. A
result looking better is never the reason.
