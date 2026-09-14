"""
statement_factors_test.py — factor test 2 rebuilds quality, value and growth
from annual statements. These checks pin the arithmetic before any result.

Every expected number is worked by hand from the formulas in
docs/PREREG_FACTOR_TEST2_2026-09-13.md, which copy the live code:
alpha_model._compute_quality_factor, alpha_model._compute_value_factor,
alpha_v2._growth_factor and metrics.piotroski_score. A test that recomputed them
with the same code would pass whatever the code did.

Offline and deterministic.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "research"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""), flush=True)


def close(a, b, tol=1e-4):
    return a is not None and b is not None and abs(a - b) <= tol


try:
    import statement_factors as S
except ImportError as e:
    check("statement_factors can be imported", False, str(e))
    print(f"\npassed {len(PASS)}, failed {len(FAIL)}")
    sys.exit(1)

print("=" * 74 + "\n1. A FIGURE IS USED ONLY ONCE IT WAS PUBLISHED\n" + "=" * 74)
check("a 31 March year-end is usable from 31 May (60 days, then month-end)",
      S.available_from("2024-03-31") == "2024-05-31", S.available_from("2024-03-31"))
check("a 31 December year-end is usable from 29 February in a leap year",
      S.available_from("2023-12-31") == "2024-02-29", S.available_from("2023-12-31"))
periods = ["2023-03-31", "2024-03-31", "2025-03-31"]
check("at 30 April 2024 the FY2024 accounts are not yet public: FY2023 is used",
      S.usable_period(periods, "2024-04-30") == "2023-03-31", str(S.usable_period(periods, "2024-04-30")))
check("at 31 May 2024 FY2024 becomes usable",
      S.usable_period(periods, "2024-05-31") == "2024-03-31", str(S.usable_period(periods, "2024-05-31")))
check("before any year is public there is nothing to use",
      S.usable_period(periods, "2023-04-30") is None, str(S.usable_period(periods, "2023-04-30")))

# A healthy company, FY2024 against FY2023, priced at 150 with 10 shares.
CUR = {"Net Income": 100.0, "Stockholders Equity": 800.0, "Total Assets": 1500.0,
       "Operating Cash Flow": 150.0, "Capital Expenditure": -50.0,
       "Total Revenue": 1000.0, "Gross Profit": 300.0, "Current Assets": 600.0,
       "Current Liabilities": 400.0, "Long Term Debt": 200.0, "Diluted EPS": 10.0,
       "Operating Income": 160.0, "Interest Expense": 20.0,
       "Ordinary Shares Number": 10.0}
PREV = {"Total Revenue": 900.0, "Net Income": 80.0}
PRICE = 150.0

print("\n" + "=" * 74 + "\n2. PIOTROSKI, AS THE LIVE CODE COMPUTES IT\n" + "=" * 74)
# roa = 100/1500 = 0.0667: F1 and F3. OCF > 0: F2. F4 and F5 are never awarded
# by the live code for NSE stocks (Yahoo's summary gives it no total assets or
# equity). Current ratio 1.5: F6. F7 fixed. Gross margin 30%: F8. Revenue up: F9.
# That is seven points. (A first draft of this test said six, a counting slip
# caught before the code it tests existed.)
check("the healthy company scores 7", S.piotroski_proxy(CUR, PREV) == 7,
      str(S.piotroski_proxy(CUR, PREV)))
check("without last year's revenue the growth point is not awarded",
      S.piotroski_proxy(CUR, None) == 6, str(S.piotroski_proxy(CUR, None)))

print("\n" + "=" * 74 + "\n3. QUALITY\n" + "=" * 74)
# 0.4*(7/9) + 0.4*((0.125-0.12)/0.08)/3 + 0.2*((100/1500-0.035)/0.04)/3 = 0.372222
raw = 0.4 * (7 / 9) + 0.4 * ((0.125 - 0.12) / 0.08) / 3 + 0.2 * ((100 / 1500 - 0.035) / 0.04) / 3
check("healthy company: raw 0.37222, score tanh(raw)",
      close(raw, 0.372222) and close(S.quality_score(CUR, PREV, PRICE), math.tanh(0.372222)),
      f"{S.quality_score(CUR, PREV, PRICE)} vs {math.tanh(raw):.5f}")

only_f = dict(CUR)
for k in ("Stockholders Equity", "Operating Cash Flow", "Capital Expenditure"):
    only_f.pop(k)
# No equity -> no ROE; no cash flow -> no FCF yield. Only Piotroski remains, and
# with no OCF the cash-flow point is lost: F = 6. Renormalised: raw = 6/9.
check("with only Piotroski available the score renormalises to tanh(F/9)",
      close(S.quality_score(only_f, PREV, PRICE), math.tanh(6 / 9)),
      str(S.quality_score(only_f, PREV, PRICE)))

DISTRESSED = dict(CUR, **{"Stockholders Equity": -50.0, "Net Income": -30.0,
                          "Operating Cash Flow": -10.0, "Operating Income": 10.0,
                          "Interest Expense": 20.0})
q = S.quality_score(DISTRESSED, PREV, PRICE)
check("negative equity, a loss, negative cash flow and cover of 0.5x: capped at "
      "neutral, then -1.25, then tanh",
      q is not None and q <= math.tanh(-1.25) + 1e-9, str(q))

print("\n" + "=" * 74 + "\n4. VALUE, ON THE MODEL'S MARKET FALLBACK\n" + "=" * 74)
# P/E 15 -> z -0.875; P/B 150/80 = 1.875 -> z -0.88333; raw 0.878333; tanh(raw/2)
check("healthy company: tanh(0.878333 / 2)",
      close(S.value_score(CUR, PRICE), math.tanh(0.878333 / 2)), str(S.value_score(CUR, PRICE)))
no_book = dict(CUR)
no_book.pop("Stockholders Equity")
check("only P/E available: the P/B leg sits at the mean and adds nothing",
      close(S.value_score(no_book, PRICE), math.tanh((-0.6 * -0.875) / 2)),
      str(S.value_score(no_book, PRICE)))
neg = dict(CUR, **{"Diluted EPS": -2.0, "Stockholders Equity": -50.0})
check("both multiples non-positive: distressed, -0.5", S.value_score(neg, PRICE) == -0.5,
      str(S.value_score(neg, PRICE)))
nothing = {"Ordinary Shares Number": 10.0}
check("no valuation data at all: not ranked (None), not scored as neutral",
      S.value_score(nothing, PRICE) is None, str(S.value_score(nothing, PRICE)))

print("\n" + "=" * 74 + "\n5. GROWTH, FISCAL YEAR OVER FISCAL YEAR\n" + "=" * 74)
check("revenue +11.1%, earnings +25%: mean of tanh(0.1111/0.30) and tanh(0.25/0.50)",
      close(S.growth_score(CUR, PREV), (math.tanh((1000 / 900 - 1) / 0.30) + math.tanh(0.25 / 0.50)) / 2),
      str(S.growth_score(CUR, PREV)))
check("a loss last year gives no earnings-growth leg; revenue alone is used",
      close(S.growth_score(CUR, {"Total Revenue": 900.0, "Net Income": -5.0}),
            math.tanh((1000 / 900 - 1) / 0.30)),
      str(S.growth_score(CUR, {"Total Revenue": 900.0, "Net Income": -5.0})))
check("no prior year: growth cannot be scored", S.growth_score(CUR, None) is None,
      str(S.growth_score(CUR, None)))

print("\n" + "=" * 74 + "\n6. A MONTH IS RANKED ONLY WITH 50 SCORED STOCKS\n" + "=" * 74)
# Run 1 of factor test 2 applied the 50-stock minimum before scoring, then ranked
# growth on as few as 14 stocks (top group: 3) for 11 months. The
# pre-registration counts stocks with a usable score for the factor tested.
import factor_test2_run as R


def _row(i, score, fwd):
    return {"ticker": f"T{i:03d}", "turnover": 1e8 + i, "fwd": {1: fwd},
            "scores": {"growth": score}}


# 200 priced stocks, only 49 with a growth score: skipped.
thin = [_row(i, i / 100 if i < 49 else None, 0.10) for i in range(200)]
# 50 scored stocks, returns 0%..4% by score fifth, plus 50 unscored stocks up 100%.
# Net of the scored stocks' own average (2%) the fifths are -2, -1, 0, +1, +2%;
# counting the unscored stocks in the market would shift every fifth by -50%.
full = ([_row(i, i / 100, 0.01 * (i // 10)) for i in range(50)]
        + [_row(100 + i, None, 1.0) for i in range(50)])
res = R.test_factor({"2024-01": thin, "2024-02": full, "2024-03": full, "2024-04": full},
                    "growth", 1)["top_minus_bottom"]
check("a month with 49 scored stocks is not ranked, however many are priced",
      res.get("n") == 3, str(res.get("n")))
check("the skipped month and its scored count are recorded",
      res.get("months_skipped_too_few_scored") == [["2024-01", 49]],
      str(res.get("months_skipped_too_few_scored")))
check("group returns are net of the scored stocks only",
      res.get("group_mean_excess_pct") == [-2.0, -1.0, 0.0, 1.0, 2.0],
      str(res.get("group_mean_excess_pct")))
check("the spread is the top fifth minus the bottom fifth: +4%",
      res.get("mean_pct") == 4.0, str(res.get("mean_pct")))

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
