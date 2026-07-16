# Cross-Sectional Momentum in Indian Equities: How Much Survives an Honest Universe?

**One-line finding:** A 12-1 momentum strategy appears to beat the Nifty by **+23%/yr** —
but roughly **half of that edge is look-ahead in universe selection**, and once the
universe is chosen point-in-time the excess is **no longer statistically significant** in
all but the broadest universe. The momentum premium in Indian equities is real only in
*breadth*, and much smaller than a naive backtest claims.

*Author: Jasmeet Singh · Quant India backtest engine · 2020-02 to 2026-07 (78 months)*

---

## Method

Cross-sectional **12-1 momentum**, backtested **walk-forward**:

- **Signal.** At each month-end *t*, rank by return from *t*−12 to *t*−1 months — the most
  recent month is **skipped** (Jegadeesh & Titman 1993) to avoid short-term reversal.
- **Portfolio.** Long the top 20% by momentum, equal-weighted, rebalanced monthly.
- **No look-ahead in timing.** Every position is chosen *before* the return it earns.
- **Costs.** 0.4% round-trip on turnover each rebalance — all figures are **net**.
- **Benchmark.** Nifty 50 buy-and-hold over identical dates. **Significance:** t-test on
  mean monthly excess return.

### The key experiment: universe construction

The naive backtest takes **today's** ~200 liquid NSE names and trades them back in 2020 —
that is look-ahead: you are using knowledge of *who ended up liquid*. The corrected version
applies a **point-in-time (PIT) screen**: at each rebalance, eligibility is the top-N by
**trailing turnover computed only from data available at that date**. A stock enters the
universe only once it was actually liquid *then*.

---

## Results

| Universe | CAGR | Sharpe | Max DD | Excess vs Nifty | t-stat | Significant (5%) |
|---|---|---|---|---|---|---|
| **Nifty 50 (benchmark)** | 13.2% | 0.33 | −23.2% | — | — | — |
| Large-cap 40 (static) | 13.0% | 0.29 | −28.1% | −0.2%/yr | −0.04 | **No** |
| Broad ~196 **(static, biased)** | 36.4% | 1.10 | −24.4% | **+23.2%/yr** | 3.78 | Yes |
| **PIT top-150 liquidity** | 34.0% | 0.97 | −28.6% | **+20.8%/yr** | 3.09 | Yes |
| **PIT top-100 liquidity** | 24.9% | 0.63 | −31.9% | **+11.7%/yr** | 1.50 | **No** |
| **PIT top-50 liquidity** | 21.1% | 0.47 | −30.8% | +7.9%/yr | 0.85 | **No** |

### What this shows

1. **Selection look-ahead was worth ~11.5 pp/yr.** Excess falls from **+23.2%** (today's
   list) to **+11.7%** (PIT top-100) — about **half the headline edge was an artifact** of
   knowing which names would still be liquid in 2026.
2. **Significance collapses.** t drops from **3.78 → 1.50** (PIT-100) and **0.85** (PIT-50).
   Under an honest universe the edge is *not* distinguishable from luck except in the
   broadest (top-150) universe.
3. **Breadth is the real variable, and it's monotonic.** The edge grows with universe width:
   40 large-caps (t=−0.04) → PIT-50 (0.85) → PIT-100 (1.50) → PIT-150 (3.09). Momentum is a
   *ranking* strategy: it needs cross-sectional dispersion, which mega-caps don't provide.
   This is consistent with the international evidence that momentum concentrates in
   smaller, less-arbitraged segments.
4. **Risk got worse, not better.** The PIT versions have *deeper* drawdowns (−29% to −32%
   vs −24%) for less return — the naive backtest flattered risk as well as return.

---

## Remaining limitations (stated plainly)

The PIT screen fixes *selection* look-ahead. It does **not** fix everything:

1. **Delisting survivorship — still present, still inflating.** Companies that failed or
   delisted between 2020–2026 are absent from the data source entirely, so even the PIT
   universe is "survivors only." Momentum tends to load on stocks that later either
   compound or collapse, so the true edge is likely **lower than even the PIT numbers**.
   Not fixable without a point-in-time constituent/delisting database.
2. **Liquidity ≠ index membership.** Trailing turnover is a *proxy* for "was this an
   investable large/mid-cap then." A real Nifty-200 historical membership list would be
   cleaner.
3. **Single regime.** 2020–2026 was a strong Indian mid-cap bull market. Momentum + mid-cap
   tailwind flatters results; 2008 or a mid-cap drawdown would look very different.
4. **Costs approximate.** 0.4% round-trip is a reasonable proxy, not a fill simulation with
   market impact — which bites hardest in exactly the smaller names where the edge lives.

## What I would do next
- Source **point-in-time index membership incl. delisted names** — the last big bias.
- Extend across **multiple regimes** (pre-2020, mid-cap drawdowns).
- **Cost sensitivity**: does the PIT-150 edge survive 0.8% / 1.2% round-trip?
- Test **long-short** and **volatility-scaled** momentum.

---

## Why this is the result worth reporting

The naive version of this study produced a headline any student could post: *"my strategy
beat the Nifty by 23% a year, Sharpe 1.1, t=3.78."* Correcting a single methodological
flaw — look-ahead in universe selection — **erased half the edge and destroyed the
significance** in most universes.

Three honest outcomes came out of this, and all three are reported: a **null** on
large-caps, a **significant but much smaller** effect in the broadest PIT universe, and an
explicit statement that the number is *still* optimistic because of delisting survivorship
I cannot remove with free data. The defensible claim here is the **direction** — momentum in
Indian equities lives in breadth and is far weaker than a naive backtest suggests — **not**
any headline return figure.

*Reproducible: `momentum_backtest(universe=BROAD_UNIVERSE, pit_universe_size=100)` in
`backend/modules/momentum_backtest.py`; in-app via Portfolio Lab → Backtest.*
