# Phase 2 findings: evidence and proposed fixes

**Written 2026-09-14 from the code at `aa4d2f9`. Nothing described here has been
changed.** Each section ends with a proposed fix that needs approval first.

> **Status, later the same day.** Sections 1–4 were approved and fixed in
> `9b2d764` (live on production 08:31 UTC). The benchmark question this raised
> was decided (Benchmark A) and fixed in `a2418ba` (live 09:11 UTC). Results are
> in `BACKTEST_RERUN_ADJUSTED_2026-09-14.md`. Section 1 item d, the Render disk
> and `QUANT_DATA_DIR` check, is still open.

## 1. "database is locked"

**What happened.** Production logged `sqlite3.OperationalError: database is
locked` at `stock_universe.py:180` (`DELETE FROM nse_stocks`) at 11:35:26 on
2026-09-13. That was five seconds after "Application startup complete"
(11:35:21).

**Evidence.**

- **Four modules bypass `db.get_conn`.** `stock_universe.py`, `screener.py`,
  `news.py` and `alerts.py` write to a local SQLite file directly. Production's
  main data is in Postgres; the tables these four write are not.
- **Three of them give up after 5 seconds.** `stock_universe.py` (17
  connections), `screener.py` and `alerts.py` use `sqlite3.connect` with no
  timeout, which waits 5 seconds for a lock and does not turn on WAL.
  `db.get_conn` and `news.py` wait 30 seconds and use WAL.
- **The failing line has moved.** The `DELETE` is at line 192 in the current
  code; the log's line 180 predates the NSE pause check added on 2026-09-13.
- **Startup runs two writers at once.** `main.py:333–334` starts
  `ensure_universe_loaded` and `ensure_screener_cache` together on the thread
  pool.
- **The screener holds the lock while waiting on Yahoo.** `screener.py:71–101`
  opens one connection and, for each stock, calls Yahoo's `.info` and inserts a
  row, committing every 25 stocks. From its first insert until the next commit
  it holds SQLite's write lock, through up to 25 Yahoo calls. The code notes
  that one call can hang 20–30 seconds on a throttled server
  (`alpha_model.py:137`).
- **The screener build runs whenever its cache is empty,** which is every start
  if the file does not survive restarts.
- **The file probably does not survive.** `DB_PATH` is
  `QUANT_DATA_DIR/quant_platform.db`, falling back to the backend folder inside
  the container. `render.yaml` attaches a disk at `/app/data` but never sets
  `QUANT_DATA_DIR`. On 2026-09-09 production's NSE and BSE lists were both empty
  (`STEP3_FINDINGS_2026-09-09.md`).
- **Not verified:** whether the Render dashboard has a disk attached and
  `QUANT_DATA_DIR` set.

**An explanation consistent with all of it:**
1. A restart begins with an empty SQLite file.
2. The screener build takes the write lock while waiting on Yahoo.
3. The universe refresh waits 5 seconds and fails.

**Impact today.**
- The NSE refresh is paused, so it attempts no write, and production's NSE list
  stays empty (`/stock/search` shows bare symbols).
- The BSE refresh is not paused and uses the same connection pattern.
- The universe lists, the screener cache and the news cache are rebuilt from
  nothing after every restart, if the file is not kept.

**Proposed fix, not implemented.**

- **a. One connection helper** for the four modules, with a 30-second wait and
  WAL, as `db.get_conn` already does for SQLite. No schema or data change.
- **b. No lock held during a network call.** The screener fetches each batch
  from Yahoo first, then writes the batch in one short transaction.
- **c. One startup writer at a time.** Load the universe, then build the
  screener cache, in one background task instead of two at once.
- **d. You check the Render dashboard.** On the backend service: is a disk
  mounted at `/app/data`, and is `QUANT_DATA_DIR` set to `/app/data`? If there
  is no disk, decide between adding one (a paid add-on) and moving these tables
  to Postgres (a code change).
- **Tests:**
  - Hold a write lock in another connection for 6 seconds and check the
    universe write waits and succeeds.
  - With a slow fake Yahoo, check the screener build holds no lock while
    waiting.
- **Cost:** one backend build, deployed outside the scan window.

## 2. Sharpe and Sortino are defined several ways

Four modules compute Sortino differently:

| Module | Shown in | Return measure | Downside measure |
|---|---|---|---|
| `simulator._compute_sortino` (`simulator.py:1187`) | Historical backtest, portfolio metrics | mean daily excess return × √252 | standard deviation of the losing days only, around their own mean |
| `momentum_backtest._annualised` (`momentum_backtest.py:77–79`) | momentum backtest | mean monthly excess return × √12 | standard deviation of the losing months only |
| `strategy_compare._metrics` (`strategy_compare.py:43–54`) | strategy comparison | CAGR − risk-free rate | standard deviation of the losing days only, × √252 |
| `pit_backtest._stats` (`pit_backtest.py:569–585`) | point-in-time backtest | CAGR − risk-free rate | root-mean-square of the losing months, divided by the number of losing months, × √12 |

**The standard definition** (Sortino and Price, 1994): downside deviation is the
square root of the average, over **all** periods, of the squared shortfall below
a stated target, annualised.

**The same portfolio gets four answers.** Five years of simulated daily returns,
CAGR 11.1%, volatility 18.9%:

| Formula | Sortino |
|---|---|
| simulator | 0.48 |
| momentum_backtest | 0.61 |
| strategy_compare | 0.38 |
| pit_backtest | 0.27 |
| Standard, target = risk-free rate, daily | 0.45 |
| Standard, monthly | 0.50 |

**One case breaks outright.** If every losing day loses exactly 1%, the
simulator reports **0.00**: the spread of identical losses is zero, and the
function returns 0 when it is. The standard definition gives −0.56.

**Sharpe differs too.** The simulator uses mean daily excess return ÷ daily
standard deviation × √252; `strategy_compare` and `pit_backtest` use (CAGR −
risk-free rate) ÷ volatility.

**The existing check cannot catch this.** `tests/independent_recompute.py:100`
uses the same (CAGR − risk-free) ÷ downside-volatility form it is meant to check.

**Proposed fix, not implemented.**
- One written definition of Sharpe and one of Sortino, target = the risk-free
  rate, used by all four modules, with hand-worked tests.
- **What it changes:** reported risk figures, including the Sortino of the
  frozen point-in-time backtest. No score or label changes.
- **What it needs:** your approval and a specification note, because the figures
  of a recorded result change.

## 3. Two backtests use unadjusted prices

This is a data problem, not wording.

- **`pit_backtest.py`** reads raw exchange closes (`pit_backtest.py:81, 129`)
  and applies no corporate-action adjustment; its limits text says so (lines
  411–413). A split or bonus inside a holding month appears as a crash or a jump
  for that stock. This backtest produced the recorded result "7.85% CAGR,
  p = 0.61", attributed to v1.0.
- **`momentum_variants.py`** loads prices with `pit_validation._load` but not
  `_apply_adjustment` (`momentum_variants.py:153`), so it is unadjusted too, as
  its text says (line 344).
- **`pit_validation.py`**, which produced factor test 1, does apply the
  adjustment (lines 637–642; 19,047 actions applied in the 2026-09-13 run).

**Proposed fix, not implemented.**
- Before Phase 3, route both through the adjustment `pit_validation` uses.
- Rerun both and record the reruns as new results. The old results stay on
  record, labelled unadjusted.
- This changes backtest figures, not the model, and needs approval.

## 4. Stale text

| Where | Says | Actually |
|---|---|---|
| `pit_validation.py:966–968` | prices are "unadjusted for splits and dividends" | adjusted; the same response reports `adjusted_for_corporate_actions: true` |
| `pit_backtest.py:25–29`, `408–410` | the archive starts in January 2024, about eighteen months | the archive starts 2011-07-04 |
| `alpha_model.py:16–21` | momentum is a rank among peers from 1-, 3- and 6-month returns | the stock's own 12-1 return adjusted for volatility |
| `alpha_model.py:29–30`, `60–61`, `795` | weights fitted by regression on 2019–2022, validated on 2023–2024 | weights unchanged since the first commit; no fit found |
| `main.py:1144–1150` | "proprietary" scoring, in the API documentation | a marketing word; covered by the agreed wording work |

The "unadjusted" text in `pit_backtest.py:411` and `momentum_variants.py:344`
is **true** (section 3).

**Proposed fix, not implemented:** text-only corrections in one commit, and one
backend build. `pit_backtest`'s text waits for the section 3 decision.

## Not checked in this pass

- **Whether the pages show the same numbers the backend computes.** The test for
  it needs the network, so it is not in the gate.
- **Server memory,** about 1.4–1.6 GB of 2 GB.
- **Market-wide headlines scored as company news** (open in
  `STEP3_FINDINGS_2026-09-09.md`), not rechecked.

## Decisions needed

1. **Section 1:** approve fixes a–c, and check the Render dashboard (d).
2. **Section 2:** approve one Sharpe and one Sortino definition, with the
   risk-free rate as the target.
3. **Section 3:** approve moving both backtests to adjusted prices and rerunning
   them.
4. **Section 4:** approve the text corrections.
5. **Drift:** record the two drifted items as documented changes, or freeze
   v1.4.1 (see `PHASE0_V1_METHODOLOGY_2026-09-14.md`).
