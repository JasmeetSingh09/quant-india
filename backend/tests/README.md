# Test suite

Property-based / edge-case stress tests for Quant India's numerical core. These
hammer the algorithms with tens of thousands of randomized inputs and assert
mathematical invariants (not just "does it run"), so a change that breaks a
model's correctness is caught.

## Run

```bash
cd backend
python tests/test_core_properties.py        # ~81k checks: calculators, risk, Monte Carlo, alpha, optimizers
python tests/test_new_algorithms_stress.py   # ~87k checks: Black-Scholes, Risk Parity, Max Diversification,
                                             #   risk decomposition, low-vol & momentum backtests, seasonality
python tests/test_modules_integration.py     # import-safety of every module + signal/optimizer integration
```

Each prints `TOTAL CHECKS`, `FAILURES`, and a category breakdown of any failures.

## What is checked (examples)

- **Black-Scholes** — put-call parity across 6k random inputs, European price
  bounds, Greek sign/range bounds, prob-ITM ∈ [0,100], monotonicity in spot &
  vol, and implied-vol round-trip (price → IV recovers the input vol).
- **Optimizers** — weights sum to 1 and are non-negative; Risk Parity produces
  equal risk contributions; Max Diversification's ratio ≥ 1; risk-decomposition
  contributions sum to 100%.
- **Backtests** — drawdowns ≤ 0, hit-rate ∈ [0,100], finite stats, honest
  caveats present; run on synthetic price paths (no network).
- **Calculators / risk sizing** — invariants over ~30k random inputs (SIP/lumpsum
  monotonicity, tax boundaries, Kelly/vol-target/position bounds).

Network calls (yfinance) are monkeypatched with synthetic data so the suite is
deterministic and offline. A notable "failure" caught during development —
deep-ITM European puts priced below undiscounted intrinsic — turned out to be
*correct* option behavior and a naive test assertion, not a code bug; the test
now uses the proper European lower bound.
