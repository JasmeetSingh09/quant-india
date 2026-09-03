"""
model_config.py — the values that must agree across modules.

A constant duplicated in nine files is nine constants. The risk-free rate was
written as 0.065 in momentum_backtest, pit_backtest, pit_validation, research,
risk_management, simulator (twice), strategy_compare, fama_french and
portfolio_optimizer, all meaning the same thing: the RBI repo rate as a proxy.
Nothing made them agree except that nobody had edited one of them yet. Updating
the rate would have meant finding all nine, and missing one would have produced
two different Sharpe ratios for the same portfolio on two pages of the same app,
with no error anywhere.

This module holds the values where agreement is REQUIRED. It imports nothing,
so anything may import it.

What is deliberately NOT here
-----------------------------
Constants that look alike but are independent decisions. pit_backtest and
pit_validation both define MIN_MONTHLY_TURNOVER = 1e7; they are the same number
today and they are separate choices — the liquidity floor of a backtest and the
liquidity floor of a factor study can legitimately diverge, and collapsing them
would silently couple two experiments. The same applies to MIN_HOLDINGS in
momentum_backtest, pit_backtest and portfolio_fix: a backtest's minimum basket
size and a portfolio's minimum diversification are different requirements that
happen to share a value.

Where two constants must agree, they live here. Where they merely match, they
stay apart and this docstring says why.
"""

# The risk-free rate used in every Sharpe and Sortino calculation, as an annual
# decimal. RBI repo rate proxy. Changing this changes every risk-adjusted
# figure the platform reports, which is exactly why it should be changed in one
# place and show up as specification drift when it is.
RISK_FREE_RATE = 0.065

# The benchmark index. Written as "^NSEI" in four separate modules, all
# meaning the Nifty 50. Two of them disagreeing would put two different
# excess returns on the same page.
BENCHMARK_INDEX = "^NSEI"
BENCHMARK_NAME = "Nifty 50"

# Conversions, stated once so a stray 250 or 365 cannot creep into an
# annualisation and be mistaken for a modelling choice.
TRADING_DAYS_PER_YEAR = 252
MONTHS_PER_YEAR = 12

# Indian delivery-equity costs for a round trip, as percentages of turnover.
# Held here because the backtest and the strategy comparator must charge the
# same rate or their results are not comparable.
COST_BROKERAGE_PCT = 0.03
COST_STT_PCT = 0.1
COST_STAMP_DUTY_PCT = 0.015
COST_EXCHANGE_PCT = 0.00345
COST_GST_PCT = 18.0

# How much of the day's universe a scan must cover before it counts as an
# observation of the market rather than of whichever stocks answered.
# Shared: the scanner enforces it and the health report measures against
# it, and the two disagreeing would mean a pass the collector called
# complete showing as incomplete in its own audit.
SCAN_COMPLETE_FRACTION = 0.90

def is_refusal(factor_result) -> bool:
    """
    True when a factor answered "I could not measure this" rather than "I
    measured this and it is zero".

    Every failure path in alpha_model returns the same shape:

        {"score": 0.0, "confidence": 0.0, "reason": "..."}

    and every successful path returns a score with a positive confidence and no
    reason at all. Both halves of the test are load-bearing:

      - confidence alone is not enough. The value factor returns score -0.5 at
        confidence 0.6 with a reason of "unusable valuation" for a company with
        negative book value. That is a deliberate judgement, not a refusal, and
        treating it as one would erase a real finding about a real company.
      - reason alone is not enough, for the same case.

    This lives here rather than in either caller because the recorder and the
    provenance layer must agree on it exactly. They ask the question for
    different purposes — one decides whether to store a number, the other
    decides whether an observation is fully evidenced — and if their answers
    ever diverged, the database would contain rows whose provenance flag
    contradicted their own contents.
    """
    if not isinstance(factor_result, dict):
        return False
    if "reason" not in factor_result:
        return False
    try:
        return float(factor_result.get("confidence") or 0) == 0.0
    except (TypeError, ValueError):
        return False


MUST_AGREE = (
    "RISK_FREE_RATE, TRADING_DAYS_PER_YEAR, MONTHS_PER_YEAR, BENCHMARK_INDEX, "
    "is_refusal "
    "and SCAN_COMPLETE_FRACTION are shared "
    "definitions: two modules disagreeing about them would report different "
    "risk-adjusted numbers for the same data. Liquidity floors and minimum "
    "holdings are NOT shared — they match today by coincidence of judgement, "
    "and are separate parameters on purpose."
)
