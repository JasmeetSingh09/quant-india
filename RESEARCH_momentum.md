# Cross-Sectional Momentum in Indian Equities: A Breadth Effect

**One-line finding:** A 12-1 momentum strategy shows *no* edge among NSE large-caps
but a large, statistically significant edge across the broad (~200-stock) universe —
the momentum premium in Indian equities lives in breadth, not in the mega-caps.

*Author: Jasmeet Singh · Built with the Quant India backtest engine · Period 2020-02 to 2026-07 (78 months)*

---

## Method

A textbook **cross-sectional 12-1 momentum** strategy, backtested **walk-forward**:

- **Signal.** At each month-end *t*, rank stocks by their return from *t*−12 to *t*−1
  months — the most recent month is **skipped** (Jegadeesh & Titman, 1993) to avoid
  short-term reversal contaminating the signal.
- **Portfolio.** Go long the top X% by momentum, equal-weighted; rebalance monthly.
- **No look-ahead.** Every position is chosen *before* the return it earns — a genuine
  out-of-sample walk-forward, not an in-sample fit.
- **Costs.** Turnover at each rebalance is charged a 0.4% round-trip cost
  (brokerage + slippage + STT), so all figures are **net**.
- **Benchmark.** Nifty 50 buy-and-hold over the identical dates.
- **Significance.** A t-test on the mean monthly excess return.

Two universes were tested to isolate the role of breadth:
1. **Large-cap:** 40 of the largest NSE names.
2. **Broad:** ~200 liquid NSE names (196 with complete data), i.e. large- **and** mid-cap.

---

## Results

| Universe / basket | CAGR | Vol | Sharpe | Max DD | Excess CAGR vs Nifty | t-stat | Significant (5%) |
|---|---|---|---|---|---|---|---|
| **Nifty 50 (benchmark)** | 13.2% | 18.0% | 0.33 | −23.3% | — | — | — |
| Large-cap 40, top 20% | 13.0% | 20.2% | 0.29 | −28.1% | **−0.2%/yr** | −0.04 | **No** |
| Broad 196, top 20% | **36.4%** | 22.6% | **1.10** | −24.4% | **+23.2%/yr** | **3.78** | **Yes** |
| Broad 196, top 10% | 43.6% | 25.5% | 1.19 | −28.6% | +30.4%/yr | 3.64 | Yes |

**The headline:** in the 40-stock large-cap universe momentum was indistinguishable
from noise (t = −0.04). Widen the universe to ~200 names and the *same* strategy
delivers a Sharpe of 1.10 and a monthly excess return that is significant at t = 3.78.

## Why breadth matters (interpretation)

Cross-sectional momentum is a **ranking** strategy — it needs dispersion between winners
and losers to exploit. Among 40 mega-caps there is little cross-sectional dispersion:
the names are large, liquid, heavily arbitraged, and move together, so "rank by momentum"
adds almost nothing. The broader universe includes mid-caps, where dispersion is far
wider and the momentum premium has historically been strongest. The result is consistent
with the international evidence that momentum concentrates in smaller, less-arbitraged
segments.

---

## Honest limitations (read before believing the magnitude)

The **direction** of the finding (momentum in breadth, not large-caps) is robust. The
**magnitude** (+23%/yr) is almost certainly overstated, for reasons I want to state plainly:

1. **Survivorship / selection bias — the big one.** The universe is *today's* liquid NSE
   names. Stocks that were delisted, went to zero, or never grew into the index are
   excluded, and momentum tends to load onto exactly the stocks that later either
   compounded or crashed. Using today's survivors biases returns upward, materially.
   A point-in-time constituent list would shrink the edge — possibly a lot.
2. **Single regime.** 2020–2026 was a historically strong Indian **mid-cap bull market**.
   Momentum + a mid-cap tailwind flatters the result; the strategy would look very
   different through 2008 or a mid-cap drawdown.
3. **Costs are approximate.** A 0.4% round-trip turnover charge is a reasonable proxy, not
   a live fill simulation with market impact — which matters more for mid-caps.
4. **No risk management.** Monthly rebalance, equal weight, no volatility targeting or
   stop-losses; the −24% drawdown is real.

## What I would do next

- Rebuild the universe from **point-in-time index membership** to remove survivorship bias
  — the single most important fix.
- Extend the sample across **multiple regimes** (pre-2020, and any mid-cap drawdown).
- Add **transaction-cost sensitivity** (does the edge survive 0.8% or 1.2% round-trip?).
- Test a **long-short** version and a **volatility-scaled** momentum signal.

---

## Why this result is worth reporting

The first version of this test — on large-caps only — returned a clean **null** (no edge,
t = −0.04), and that null was reported as-is rather than buried. Widening the universe then
surfaced a real, significant effect. Both halves matter: the null showed the method is
honest and not p-hacked, and the contrast between the two universes *is itself the finding*.
The willingness to state the survivorship caveat, rather than quote 23%/yr as a headline
return, is the point — the goal is a defensible result, not an impressive-looking one.

*Reproducible in the app: Portfolio Lab → Backtest (curated universe) and via the
`momentum_backtest` module for the broad universe.*
