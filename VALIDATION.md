# Validation

How each quantitative model in Quant India is implemented, how it was tested, and
what it assumes. Nothing here is a mathematical proof — every claim below is
**validated against theoretical expectations** via behavioural and property tests
that anyone can re-run:

```bash
cd backend
python tests/test_core_properties.py         # 81,215 assertions, offline
python tests/test_new_algorithms_stress.py   # 87,173 assertions, offline
```

**168,388 assertions, currently passing.** These are property/edge-case tests
(invariants over randomised inputs), not just smoke tests. Both RNGs (numpy and
the stdlib `random`) are seeded and these two suites make no network calls, so
they are **deterministic** — repeated runs produce an identical check count and
result, which is what makes the number above checkable rather than asserted.
Measured 2026-09-09: `test_core_properties.py` returned 81,215 on three
consecutive runs.

### A third suite, and why its count is not in that number

```bash
python tests/test_modules_integration.py     # import-safety + integration
```

This one is **not offline and not deterministic**, and the number above
deliberately excludes it. It resolves synthetic tickers (`B0.NS`, `V1.NS`, `Z.NS`)
against live Yahoo, so its log fills with 404s, it takes **over fifteen minutes**,
and its result depends on Yahoo's availability and rate limiting. That is not
import cost — all 90 modules import in **9.2 seconds** together.

Until it is network-isolated, run it as an integration check, not as evidence for
a headline count. It currently reports **1,613 checks, 0 failures** (2026-09-09),
which would make 170,001 in total — but that third figure is only as stable as
Yahoo is, which is why the headline stops at 168,388.

An earlier version of this file claimed all three suites passed and that "all
network calls are monkeypatched". Neither was true of this third suite. It was
also **failing**: `compute_alpha_score` memoises per ticker (`_SCORE_CACHE`,
15-minute TTL), which is correct in production and fatal to a test that patches
the four factor functions and calls it 41 times expecting 41 different answers —
it returned the first answer every time. The model was never wrong; clearing the
cache between iterations gives 41 checks and 0 failures. But forty of those
checks had been asserting nothing while still counting themselves, which is worse
than failing, and it survived because nobody ran the command.

---

## Status

| Algorithm | Status | How it was validated |
|---|---|---|
| Markowitz Mean-Variance | ✓ Validated | Weights sum to 1, non-negative, no NaN over randomised covariances; objective switches (max Sharpe / min variance / max return) behave as expected |
| Black-Litterman | ✓ Validated | Behavioural: a bullish view raises both the posterior return and the weight; output differs from Markowitz on identical inputs |
| Hierarchical Risk Parity | ✓ Validated | Behavioural: near-duplicate assets (corr 0.98) are jointly under-weighted vs independent assets |
| Equal Risk Contribution | ✓ Validated | Risk contributions are equal by construction and sum to 100% |
| Maximum Diversification | ✓ Validated | Diversification ratio >= 1 always (a mathematical necessity) |
| Efficient Frontier | ✓ Validated | Volatility increases monotonically with return across the efficient arm |
| Monte Carlo | ✓ Validated | Percentiles ordered (p5<=p25<=median<=p75<=p95), probabilities in [0,100], seed-reproducible |
| Black-Scholes / Greeks | ✓ Validated | Put-call parity over 6,000 random inputs; ATM 1y call = 10.4506 vs textbook 10.45; implied vol round-trips |
| Risk metrics (Sharpe/Sortino/VaR/CVaR) | ✓ Validated | Invariants over ~11,000 randomised inputs |
| Kelly / vol targeting | ✓ Validated | Recommended weight is the min of half-Kelly, vol-target and cap; bounded [0, cap] |
| Momentum factor | ✓ Validated | Sign correct on synthetic up/down/flat series; score bounded [-1,1] over 500 random walks |

---

## Formulations, assumptions, and limitations

### Markowitz Mean-Variance
Maximise Sharpe = (wᵀμ − rf) / sqrt(wᵀΣw), subject to Σwᵢ = 1 and wᵢ ≥ 0 (SLSQP).
Σ uses **Ledoit-Wolf shrinkage**, not the sample covariance, because the sample
estimate is noisy and Markowitz error-maximises on it.

- **Assumes:** μ estimated as the trailing mean of log returns × 252 — this is a
  *past average, not a forecast*, and can be negative.
- **Limitation:** "Maximise Return" is a linear objective, so its solution is always
  a single-asset corner unless capped. The UI warns about this.

### Black-Litterman
The implementation follows the canonical **He–Litterman Bayesian framework**, using
reverse-optimised equilibrium returns, explicit investor views (P, Q), a confidence
matrix Ω, and posterior expected returns for optimisation:

```
pi     = delta * Sigma * w_mkt                       (equilibrium excess returns)
Omega  = diag( (1 - confidence_i) * (P_i Sigma P_iᵀ) )
mu_BL  = [ (tau*Sigma)^-1 + Pᵀ Omega^-1 P ]^-1 · [ (tau*Sigma)^-1 pi + Pᵀ Omega^-1 Q ]
```

- `w_mkt` comes from **actual market caps** (not equal weights).
- `delta = 2.5` (He & Litterman 1999 market risk-aversion).
- **tau defaults to 0.05** and is now **user-selectable** (API `tau`, and a slider in
  the optimiser UI, range 0.01-0.10). It is not adaptive — it does not auto-fit to data.
- Views are absolute (P is an identity-style selector); **relative views are not supported.**
- Default `max_weight = 0.35`.

### Hierarchical Risk Parity (López de Prado 2016)
Correlation → distance matrix → hierarchical clustering → quasi-diagonalisation →
recursive bisection. Uses no expected returns at all — only Σ.

### Equal Risk Contribution / Maximum Diversification
- **ERC:** minimise the dispersion of risk contributions wᵢ·(Σw)ᵢ / sigma_p (Maillard 2010).
- **MaxDiv:** maximise the diversification ratio (wᵀ sigma) / sqrt(wᵀΣw) (Choueifaty 2008).
- Both are **covariance-only** — they never look at expected returns, so a negative
  "expected return" on their output is descriptive, not a failure.

### Monte Carlo — how covariance is actually preserved
**Neither multivariate-normal sampling nor naive independent draws.** The assets are
first collapsed into the portfolio's **realised historical return series**:

```
r_port(t) = sum_i w_i * r_i(t)        # actual joint daily observations
```

That single univariate series is then simulated four ways:

| Method | What it does | Covariance treatment |
|---|---|---|
| **bootstrap** | resample historical portfolio days i.i.d. | **Exact** — each sampled day is a real day on which the assets moved together |
| **block** | resample consecutive blocks | Exact, and preserves autocorrelation / volatility clustering |
| normal | draw N(mu, sigma) of the portfolio series | Enters only through the portfolio sigma |
| t | Student-t (dof=5), scaled to sigma | Same, with fatter tails |

- **Why this is defensible:** for a **fixed-weight, buy-and-hold** portfolio the
  bootstrap preserves the realised covariance *by construction* — arguably more
  faithful than assuming multivariate normality.
- **Limitations (stated plainly):** it does **not** model per-asset paths, so it
  cannot simulate rebalancing, per-asset attribution, or a shock to one asset's
  correlation. It assumes the historical correlation regime persists. The
  normal/t methods impose a distributional shape the data may not have.

### Black-Scholes
European options only. Closed-form price + delta, gamma, vega, theta, rho, and
risk-neutral P(ITM). Greeks are reported in trader units (vega per +1% vol, theta
per calendar day, rho per +1% rate).

- **Assumes:** constant volatility and lognormal prices — both violated in reality
  (this is why the volatility smile exists).
- **Limitation:** no dividends; American exercise is not modelled. A European put
  can legitimately trade below intrinsic value (the discounting effect) — the tests
  use the correct European lower bound, not the American one.
- **Implied volatility is ill-posed for near-worthless options.** As vega -> 0 the
  price stops responding to sigma (a 2.6-vol-point range can map to prices of
  0.0002 vs 0.0079), so the vol cannot be recovered from the price. This is a
  property of the inverse problem, not of the solver; the round-trip test asserts
  recovery only where vega is meaningful.

### Risk-free rate
**Default 6.5%** (`RISK_FREE_RATE`, an RBI repo-rate proxy), now **user-selectable**
per request (API `risk_free_pct`; UI offers RBI repo / 10-yr G-Sec / custom).
Every Sharpe figure inherits whichever value is chosen. The presets are **static
reference values — not live yields**; nothing is fetched from a bond feed.

### Constraints
| Constraint | Supported |
|---|---|
| Long-only (wᵢ ≥ 0) | ✅ enforced everywhere |
| Weights sum to 1 | ✅ enforced everywhere |
| Max weight per stock | ✅ Markowitz (slider) and BL (0.35 default) |
| Min weight per stock | ✅ Markowitz |
| **Long/short** | ❌ not supported |
| **Sector limits** | ❌ not supported |
| **Turnover / tax constraints** | ❌ not supported |

---

## Known limitations (whole platform)

1. **Data source.** Prices/fundamentals come from `yfinance` (Yahoo), which
   rate-limits cloud IPs and can return *partial* payloads. Metrics are cached and
   truncated payloads are rejected, but data quality is bounded by the source.
2. **Survivorship bias.** Backtests use currently-listed names; delisted companies
   are absent from the data source entirely, which biases returns upward. See
   `RESEARCH_momentum.md`, where correcting universe look-ahead removed roughly
   half of a measured momentum edge.
3. **Expected returns are historical averages**, not forecasts, everywhere except
   Black-Litterman.
4. **Not investment advice.** These are research/education tools; signals are a
   screen, not a recommendation.

---

*Re-run everything yourself: the suites in `backend/tests/` are deterministic and
require no network access.*
