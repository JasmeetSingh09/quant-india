# Product additions: decision record

**Written 2026-09-23. Approved in principle by the owner the same day
("approve 5, 1, 2, 4").** This record fixes what each addition computes, what
it must never claim and how it is tested. **Nothing is built until the owner
approves this document.**

## Rules that apply to all four

- **Model:** no change to the frozen v1.4.1 model (weights, formulas,
  thresholds, labels). `GET /strategy/drift/v1.4.1` must stay free of
  behavioural drift.
- **Data:** no new data source. Prices come from the existing Yahoo loader
  (`data_fetcher.download_close`); scores from the nightly scan; evidence from
  `factor_evidence.py`. No NSE or BSE collection, no new index data.
- **Rankings:** use the existing rank wording (`frontend/src/signalLabel.js`),
  never "buy", "best" or "winner".
- **Evidence:** a factor is shown with its evidence status from
  `factor_evidence`, never on its own.
- **Missing data** shows as "not available", never as zero.
- **Load:** new endpoints are read-only unless stated, bounded in size, and
  cached with `swr_cache` or `bounded_cache` where the answer is shared.
- **Tests:** each addition ships with offline tests in the CI gate, and each
  test must fail against the code before the change. The frontend must build.

## Order of work

1. Glossary wiring (#5)
2. Rolling correlation (#1)
3. Stock comparer (#2)
4. Thesis records (#4)

Each is a separate change, reviewed and deployed on its own.

---

## #5 Glossary wiring

**What exists.**
- `frontend/src/glossary.js`: 63 terms.
- `frontend/src/components/Term.jsx`: tooltip component.
- **Correction (same day):** the first draft said no page used the glossary.
  The underlined `<Term>` form is unused, but the "?" form (`<InfoTip>`) was
  already on 9 pages. The real problems were wrong definitions (p-value,
  Sharpe, confidence, pairs trading) and no limits line; 4 tables lacked tips.

**What it adds.**
1. **Terms on screen:** use `<Term>` on the first appearance of each defined term
   on every page that shows it: Sharpe, Sortino, CVaR, drawdown, beta, alpha
   score, Piotroski, P/E, regime and so on.
2. **"Can't tell you" line:** each glossary entry gains `limits`, one line on
   what the number cannot tell you.
   - Example: Sharpe — "Uses past volatility; says nothing about a crash that
     has not happened yet."
3. **Consistency:** entries must match the app's own definitions. Examples:
   - Sharpe and Sortino follow `risk_metrics.py`;
   - "confidence" means data coverage;
   - momentum is the stock's own 12-1 return.

**Must never claim:** that a metric predicts returns.

**Tests** (a new `glossary_test`, run in the frontend build or as a Node script):
- every `<Term k=…>` used in the code exists in the glossary;
- every entry has `limits`;
- no entry contains "buy", "sell", "guarantee" or "predict" outside a
  negation;
- Sharpe, Sortino and momentum definitions contain the key phrases from
  `risk_metrics.py` and `alpha_model.py`.

**Size:** half a day. Frontend only; no backend deploy.

---

## #1 Correlation over time

**Question it answers:** does diversification hold up when the market falls?

**Endpoint:** `GET /portfolio/correlation-over-time?tickers=…&months=36`,
read-only, 2 to 15 tickers.

**Computes**, from monthly total returns via the existing adjusted Yahoo
loader:
1. **Rolling correlation:** the 12-month rolling average pairwise correlation
   of the holdings, month by month.
2. **Most correlated pairs:** the 12-month rolling correlation for the 3 most
   correlated pairs.
3. **Calm versus falling months:**
   - **Falling months** are months where the **Nifty 50 fell 5% or more**.
     They are defined by the market, not the portfolio, so the split does not
     depend on the holdings' own returns.
   - **Calm months** are all other months.
   - Reported: average pairwise correlation in each, the number of months in
     each, and the months themselves.

**Must say, beside the numbers:**
- **Correlation rises mechanically when markets are more volatile** (the
  Forbes–Rigobon effect). Some of the rise in falling months is that effect,
  not a change in how the stocks relate. The figures are measured, not
  adjusted.
- **With fewer than 6 falling months** in the window, the falling-month figure
  is shown as "too few months to compare", not as a number.
- **Past correlation** does not guarantee future correlation.

**Must never claim:** a diversification "score" or a recommendation to add
or remove a stock.

**Regime labels:** not used. The existing regime model (a hidden Markov model
fitted over the full Nifty history) labels past months using later data, which
is look-ahead for this purpose. The simple 5% rule is transparent and uses
only that month.

**Tests** (a new `correlation_over_time_test`, offline, synthetic prices):
- three series with a known correlation that switches in marked months: the
  rolling figure and the falling/calm split match hand-computed values;
- fewer than 6 falling months gives "too few", not a number;
- a ticker with missing history is reported as excluded, never filled;
- identical series give correlation 1; the average ignores the diagonal;
- the response always carries the Forbes–Rigobon note.

**Size:** 1–2 days. One backend deploy.

---

## #2 Stock comparer

**What it adds:** a side-by-side view of 2 to 6 stocks, reached from the
Stocks page ("Compare") and from the dashboard picks. The owner asked
(2026-09-23) for metrics, value, charts and risk. It has five parts.

**1. Charts** (period selectable: 6 months, 1 year, 3 years, 5 years)
- **Growth of Rs 100:** each stock's adjusted price, rebased to 100 at the
  start of the period, on one chart. The Nifty 50 is shown as a dashed line
  and labelled "price index, excludes dividends".
- **Drawdown chart:** how far each stock sat below its own previous peak on
  every day of the period.

**2. Value** (from `/stock/metrics`, "as reported by Yahoo on <date>, not
point-in-time"):
- P/E, forward P/E, P/B, P/S, EV/EBITDA and dividend yield;
- market cap and sector, so the comparison is not quietly across different
  industries. If the stocks are in different sectors, a note says multiples
  are not directly comparable.

**3. Quality and business** (same source and label):
- ROE, ROA, operating and profit margins, revenue and earnings growth;
- debt-to-equity and current ratio;
- free cash flow;
- the Piotroski F-score (0–9), with how many of its 9 tests could be run.

**4. Risk** (computed from adjusted daily prices over the chosen period, by
one new read-only endpoint):
- volatility (annualised) and maximum drawdown with its dates;
- the worst single month;
- 95% CVaR of daily returns: the average loss on the worst 5% of days;
- **beta against the Nifty 50,** computed by us from prices. Yahoo's own
  `beta` field is not used: its benchmark and window are not stated;
- a correlation matrix of the compared stocks;
- Sharpe and Sortino, defined as in `risk_metrics.py`.

**5. Model view:**
- alpha score, rank label (`signalLabel`) and data coverage from the nightly
  scan;
- each factor's contribution, with its evidence badge (`EvidenceBadge`), so
  momentum shows "Passed" and the others "Untested".

**Highlights:** in each row the highest and lowest value may be shaded and
labelled "highest" or "lowest", never "best". Higher is not better for every
row (volatility, P/E, drawdown), so no row declares a winner.

**New endpoint:** `GET /stock/compare?tickers=…&period=1y`
- **Read-only**, 2–6 tickers.
- **Returns** the rebased and drawdown series (weekly points for periods of 3
  years or more, to keep the response small) and the risk figures.
- **Cached** per ticker set and period with `swr_cache` for 15 minutes.
- **Reuses** `download_close` and `risk_metrics`; no new data source.

**Must never claim:**
- a winner, a recommended stock or an overall verdict;
- that past risk or return predicts future risk or return;
- the untested factors' values as evidence.

**Must say, beside the numbers:**
- risk figures are "measured over <period>; past only";
- the value and quality figures are Yahoo's current view, not point-in-time.

**Tests** (`stock_compare_test`, offline, synthetic prices):
- **Hand-worked figures:** rebasing starts every series at exactly 100;
  maximum drawdown and its dates, CVaR, beta (a series built as 1.5 × the
  index plus noise gives about 1.5) and the correlation matrix all match
  hand-worked values; Sharpe and Sortino equal `risk_metrics` exactly.
- **Missing data:** a ticker with missing history is reported as excluded,
  never filled; a missing metric shows "not available".
- **Limits:** 1 or 7 tickers are refused with a message.
- **Frontend check:** no rendered label contains "best", "buy" or "winner".

**Size:** 2–3 days. One backend deploy, plus the frontend.

---

## #4 Thesis records

**Purpose:** record the *reasoning* behind a pick, not only the pick, so a
later review can say which part was wrong. This is the difference between
"the model said so" and research, for ISEF and the Wharton report.

**Storage:** new tables in the existing database (Postgres in production).
Private to each signed-in user through the existing `current_user_id` sign-in
check.

- **`theses`:** one row per thesis.
  - Who and what: `id`, `user_id`, `ticker`, `created_at`, `status` (open or
    closed), `closed_at`, `close_reason`.
  - The reasoning: `stance` ("expect to outperform" / "expect to
    underperform" / "watching"), `horizon_months`.
- **`thesis_revisions`: append-only; a revision is never edited or deleted.**
  - Identity: `id`, `thesis_id`, `created_at`.
  - Content: `reasons`, `evidence`, `bear_case`, `risks`.
  - Triggers: `invalidation` (one or more "what would make me wrong"
    statements), optionally with a measurable part (price closes below a
    level, or the model's rank label falls to "Ranked low" or below).
  - Change record: `what_changed`, **required on every revision after the
    first.**
  - A snapshot at writing time: price, alpha score and rank label, stored so
    the record shows what was known then.

**Behaviour:**
- **Opening:** needs at least a reason, a bear case and one invalidation
  trigger.
- **Changing the view** creates a new revision, and the app refuses one
  without `what_changed`.
- **Measurable triggers:** checked against the latest stored price and scan
  result, and shown as "trigger met on <date>". The app flags; it never closes
  a thesis or acts by itself.
- **Closing:** needs a reason (e.g. "trigger met", "horizon reached",
  "changed my mind"). Closed theses stay readable.
- **Deleting:** a user may delete their own thesis and all its revisions. It
  is their data.

**Must never:**
- suggest a thesis;
- rate one as right or wrong on returns alone;
- share one without the user's explicit action.

**Endpoints** (all require sign-in; all writes are the user's own data):
- `POST /theses`, `GET /theses`, `GET /theses/{id}`
- `POST /theses/{id}/revisions`, `POST /theses/{id}/close`
- `DELETE /theses/{id}`

**Tests** (a new `thesis_records_test`, offline, SQLite):
- a thesis without a bear case or a trigger is refused;
- a second revision without `what_changed` is refused;
- revisions cannot be edited, and old ones read back unchanged;
- one user cannot read, revise or delete another user's thesis;
- a price trigger flags only when the stored close crosses the level, and
  never changes the status;
- the snapshot stores the values at writing time, not later ones;
- the Postgres and SQLite schemas create identically, following the existing
  `advice_log` pattern.

**Size:** 3–4 days. One backend deploy, plus the frontend.

---

## Owner decisions needed

1. Approve this record as written, or mark changes.
2. **Falling-month rule (#1):** Nifty 50 down 5% or more in the month. Keep,
   or pick another threshold now, before anything is computed.
3. **Who builds:** Claude Code, or Codex once it is set up, with Claude Code
   reviewing. Either way, the tests above are the bar.
