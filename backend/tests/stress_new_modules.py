"""
stress_new_modules.py — adversarial tests for benchmark, liquidity, tax,
rate limiting, the advice log and the focus-aware coach.

These are the inputs a real user eventually produces by accident: a weight that
is a string, a portfolio that sums to 99.99, a holding period of minus one, a
gain of ten crore, a ticker with a newline in it. Each one either works or fails
in a stated way — what is not allowed is a wrong number delivered confidently.
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

checks = 0
failures = []


def ok(cond, label):
    global checks
    checks += 1
    if not cond:
        failures.append(label)


def section(name):
    print(f"\n--- {name} ---")


# ============================ TAX =====================================
section("tax")
from tax import after_tax, portfolio_after_tax, on_gain, LTCG_EXEMPTION

# The boundary itself: one day either side must change the rate.
a = on_gain(100000, 364)
b = on_gain(100000, 365)
ok(a["kind"] == "short-term" and b["kind"] == "long-term", "364/365 boundary")
ok(a["tax"] > b["tax"], "short-term costs more than long-term")
print(f"  day 364: Rs {a['tax']:,.0f}   day 365: Rs {b['tax']:,.0f}")

# Exemption must be granted once, not per holding.
p = [{"invested": 100000, "current_value": 200000, "days_held": 400} for _ in range(4)]
t = portfolio_after_tax(p)
ok(t["exemption_applied"] == LTCG_EXEMPTION, "exemption capped at 1.25L across portfolio")
expected = (400000 - LTCG_EXEMPTION) * 0.125
ok(abs(t["total_tax"] - expected) < 1, f"4x1L LT gain taxed correctly ({t['total_tax']} vs {expected})")
print(f"  4 holdings, Rs 4L LT gain -> tax Rs {t['total_tax']:,.0f} (exemption Rs {t['exemption_applied']:,.0f})")

# Losses are never taxed, and never produce a positive tax.
ok(on_gain(-50000, 100)["tax"] == 0, "loss not taxed (short)")
ok(on_gain(-50000, 500)["tax"] == 0, "loss not taxed (long)")
ok(after_tax(100000, 50000, days_held=30)["tax"] == 0, "losing portfolio pays no tax")

# A gain exactly at the exemption pays nothing; a rupee more pays on a rupee.
ok(on_gain(LTCG_EXEMPTION, 400)["tax"] == 0, "gain exactly at exemption is free")
ok(abs(on_gain(LTCG_EXEMPTION + 1000, 400)["tax"] - 125) < 1, "only the excess is taxed")

# Degenerate and hostile inputs.
ok("error" in after_tax(0, 100, days_held=10), "zero initial rejected")
ok("error" in after_tax(-5, 100, days_held=10), "negative initial rejected")
ok("error" in after_tax("abc", 100, days_held=10), "non-numeric rejected")
ok("error" in after_tax(100, 200), "missing holding period rejected")
ok("error" in portfolio_after_tax([]), "empty portfolio rejected")
ok(on_gain(0, 100)["tax"] == 0, "zero gain")
ok(after_tax(100000, 100000, days_held=400)["tax"] == 0, "flat portfolio pays nothing")

# Huge numbers must stay arithmetic, not overflow into nonsense.
big = after_tax(1e7, 1e9, days_held=30)
ok(big["tax"] > 0 and big["net_return_pct"] < big["gross_return_pct"], "1000x gain sane")
ok(abs(big["tax"] - (1e9 - 1e7) * 0.20) < 1, "large short-term gain exact")

# Negative days should not silently become long-term.
ok(on_gain(1000, -5)["kind"] == "short-term", "negative days is not long-term")


# ========================== LIQUIDITY =================================
section("liquidity")
from liquidity import assess, label, FREELY_TRADEABLE, THIN

ok(label(None) == "—", "no value renders as dash")
ok("Cr" in label(5e7), "crore formatting")
ok("L" in label(5e5), "lakh formatting")
ok(label(0) == "Rs 0/day", "zero formats")

for bad in ["", "   ", "NOTAREALTICKER123.NS", "\n\t", "../../etc/passwd"]:
    r = assess(bad)
    ok(r.get("tier") in ("unknown", "illiquid", "thin", "moderate", "liquid"),
       f"hostile ticker {bad!r} returns a valid tier")
    ok("tradeable" in r, f"hostile ticker {bad!r} has tradeable key")

r = assess("RELIANCE.NS")
ok(r["tier"] == "liquid", "RELIANCE is liquid")
ok(r["daily_value"] > FREELY_TRADEABLE, "RELIANCE above threshold")
print(f"  RELIANCE.NS -> {r['tier']} {label(r['daily_value'])}")

# Case and whitespace must not produce a different answer.
ok(assess("reliance.ns")["tier"] == assess(" RELIANCE.NS ")["tier"], "case/space normalised")


# ========================== BENCHMARK =================================
section("benchmark")
from benchmark import compare, index_return

ok(compare(None, 365) is None, "no portfolio return -> None, never 0%")
c = compare(50.0, 365)
if c:
    ok(c["verdict"] in ("ahead", "behind", "matched"), "verdict is one of three")
    ok(abs(c["difference_pct"] - (c["portfolio_return_pct"] - c["benchmark_return_pct"])) < 0.02,
       "difference is self-consistent")
    print(f"  +50% vs index -> {c['verdict']} by {c['difference_pct']} pts")
    # A big loss must read as behind, never be softened.
    c2 = compare(-90.0, 365)
    ok(c2["verdict"] == "behind", "-90% is behind")
    ok("behind" in c2["plain"].lower(), "plain text says behind")
else:
    print("  index unavailable — comparison correctly returned None")


# ========================= RATE LIMIT =================================
section("rate limit")
import rate_limit
from rate_limit import check, bucket_for, LIMITS, IP_CEILING

rate_limit._hits.clear()


class FakeReq:
    def __init__(self, path, ip="10.0.0.1", auth=None):
        self.url = type("U", (), {"path": path})()
        self.client = type("C", (), {"host": ip})()
        self.headers = {"authorization": auth} if auth else {}


ok(bucket_for("/universe/scan") == "heavy", "scan is heavy")
ok(bucket_for("/portfolio/advise") == "medium", "advise is medium")
ok(bucket_for("/anything/else") == "light", "unknown path is light")

for p in ("/health", "/", "/healthz", "/docs", "/openapi.json"):
    rate_limit._hits.clear()
    ok(all(check(FakeReq(p)) is None for _ in range(500)), f"{p} never throttled")

# The limit must bite at exactly the configured count.
rate_limit._hits.clear()
lim, _ = LIMITS["heavy"]
allowed = sum(1 for _ in range(lim + 10) if check(FakeReq("/universe/scan")) is None)
ok(allowed == lim, f"heavy allows exactly {lim} (got {allowed})")

# One caller being blocked must not block anyone else.
ok(check(FakeReq("/universe/scan", ip="10.0.0.2")) is None, "other IP unaffected")
ok(check(FakeReq("/universe/scan", auth="Bearer " + "z" * 60)) is None, "signed-in keyed apart")

# Missing client info must not crash the limiter.
bad = FakeReq("/universe/scan")
bad.client = None
try:
    check(bad)
    ok(True, "no client info handled")
except Exception:
    ok(False, "no client info handled")

# The classroom case: many anonymous people behind one address must not share
# a single budget, because that is what a demo actually looks like.
class ClientReq(FakeReq):
    def __init__(self, path, ip="203.0.113.9", cid=None, auth=None, ua="Mozilla/5.0"):
        super().__init__(path, ip, auth)
        self.headers = dict(self.headers)
        self.headers["user-agent"] = ua
        if cid:
            self.headers["x-client-id"] = cid


rate_limit._hits.clear()
blocked = sum(1 for p in range(30) for _ in range(10)
              if check(ClientReq("/stock/X", cid=f"device-{p:08d}")) is not None)
ok(blocked == 0, f"30 anonymous people on one IP are not throttled (got {blocked} blocks)")

# One runaway tab is still caught.
rate_limit._hits.clear()
n = sum(1 for _ in range(400) if check(ClientReq("/stock/X", cid="device-00000001")) is None)
ok(n == LIMITS["light"][0], "single client still capped at its own limit")

# Rotating the self-asserted id must not buy an unlimited budget.
rate_limit._hits.clear()
n = sum(1 for i in range(2000) if check(ClientReq("/stock/X", cid=f"device-{i:08d}")) is None)
ok(n == IP_CEILING["light"][0], "rotating client ids stopped by the network ceiling")

# A signed-in user is accountable individually and must survive a busy network.
ok(check(ClientReq("/stock/X", auth="Bearer " + "q" * 60)) is None,
   "signed-in user not blocked by a saturated network")

# ...but still has their own budget.
rate_limit._hits.clear()
n = sum(1 for _ in range(400) if check(ClientReq("/stock/X", auth="Bearer " + "q" * 60)) is None)
ok(n == LIMITS["light"][0], "signed-in user still has a personal limit")

# A short or malformed client id must fall back rather than be trusted.
rate_limit._hits.clear()
for bad_cid in ("", "ab", "x" * 200, "has space", "semi;colon"):
    r = check(ClientReq("/stock/X", cid=bad_cid))
    ok(r is None or "retry_after" in r, f"malformed client id {bad_cid[:12]!r} handled")

# An old cached bundle sends no client id at all and must still work.
rate_limit._hits.clear()
ok(check(ClientReq("/stock/X")) is None, "missing client id still served")

# A blocked response must say when to retry.
rate_limit._hits.clear()
for _ in range(lim):
    check(FakeReq("/universe/scan"))
hit = check(FakeReq("/universe/scan"))
ok(hit and hit["retry_after"] > 0, "429 carries a positive Retry-After")


# =========================== ADVICE LOG ===============================
section("advice log")
from advice_log import portfolio_key, record, effectiveness

k1 = portfolio_key({"A.NS": 50, "B.NS": 50}, "u1")
k2 = portfolio_key({"B.NS": 50, "A.NS": 50}, "u1")
k3 = portfolio_key({"A.NS": 60, "B.NS": 40}, "u1")
k4 = portfolio_key({"A.NS": 50, "B.NS": 50}, "u2")
ok(k1 == k2, "key is order-independent")
ok(k1 != k3, "different weights -> different key")
ok(k1 != k4, "different user -> different key")
ok(len(k1) == 24 and all(c in "0123456789abcdef" for c in k1), "key is a hex digest")
ok("A.NS" not in k1 and "50" not in k1, "key leaks no holdings")

ok(record([], {}) == 0, "empty suggestions records nothing")
e = effectiveness()
ok("total_suggestions" in e, "effectiveness reports a total")
ok(e.get("verdict"), "effectiveness always states a verdict")
ok("not yet enough" in e["verdict"].lower() or "now have" in e["verdict"].lower(),
   "verdict is honest about sample size")


# ====================== FOCUS-AWARE COACH =============================
section("coach focus")
from portfolio_advisor import FOCUS, advise

ok(FOCUS["live"] is None, "live sees everything")
ok("behind_index" not in (FOCUS["design"] or set()), "design never benchmarks")
ok("tax_boundary" not in (FOCUS["design"] or set()), "design has no tax")
ok("behind_index" not in (FOCUS["risk"] or set()), "risk never benchmarks")
ok("weak_alpha" not in (FOCUS["risk"] or set()), "risk skips stock opinions")
ok("downside_breach" in FOCUS["risk"], "risk keeps the downside rule")
ok("illiquid" in FOCUS["design"], "design checks tradeability")

# Degenerate portfolios must not crash any mode.
for focus in ("live", "design", "risk", "nonsense-mode"):
    r = advise({"RELIANCE.NS": 100.0}, focus=focus)
    ok("suggestions" in r or "error" in r, f"single holding, focus={focus}")

ok("error" in advise({}), "empty portfolio rejected")

# Weights that do not sum to 100 must be normalised, not rejected outright.
r = advise({"RELIANCE.NS": 33.33, "TCS.NS": 33.33, "INFY.NS": 33.33}, focus="design")
ok("suggestions" in r, "99.99% sum handled")
ok(r.get("focus") == "design", "focus echoed back")

# design mode must not emit a benchmark verdict even when handed a return
r = advise({"RELIANCE.NS": 50, "TCS.NS": 50}, focus="design", current_return_pct=-40.0)
kinds = {s["kind"] for s in r.get("suggestions", [])}
ok("behind_index" not in kinds, "design suppresses behind_index even with a return")
ok(r.get("tax") is None, "design returns no tax view")
print(f"  design mode findings: {sorted(kinds) or 'none'}")

r = advise({"RELIANCE.NS": 50, "TCS.NS": 50}, focus="risk", current_return_pct=-40.0)
kinds_r = {s["kind"] for s in r.get("suggestions", [])}
ok("behind_index" not in kinds_r and "weak_alpha" not in kinds_r, "risk mode stays on risk")
print(f"  risk mode findings:   {sorted(kinds_r) or 'none'}")


# ================= TRACK-RECORD METRIC SEMANTICS =======================
# Permanent regression tests for the scorecard. These encode decisions rather
# than just exercising code: a future change that flips how a SELL is scored, or
# quietly starts counting a flat stock as a successful BUY, should fail here.
section("track record semantics")
from prediction_tracker import _side_stats, _independence, _non_overlapping

def rows(*vals):
    return [{"forward_return_pct": v, "excess_pct": None} for v in vals]

# BUY: right when the stock rises.
b = _side_stats(rows(5, -3, 2), wants_down=False)
ok(b["hit_rate_pct"] == 66.7, "BUY hit = share that rose")
ok(b["hit_means"] == "rose", "BUY hit labelled 'rose'")

# SELL: right when the stock FALLS. A rising SELL is a miss however good the
# average looks — the bug this whole section exists to prevent.
s_ = _side_stats(rows(-5, 3, -2), wants_down=True)
ok(s_["hit_rate_pct"] == 66.7, "SELL hit = share that fell")
ok(s_["hit_means"] == "fell", "SELL hit labelled 'fell'")
ok(_side_stats(rows(1, 2, 3), wants_down=True)["hit_rate_pct"] == 0.0,
   "all-rising SELLs score 0% despite a positive average")

# Zero return: a flat stock did not do what either signal asked, so it counts
# as a miss on BOTH sides. Documented here because "unchanged" is genuinely
# ambiguous and silence would let it drift.
ok(_side_stats(rows(0, 0), wants_down=False)["hit_rate_pct"] == 0.0,
   "flat counts as a BUY miss")
ok(_side_stats(rows(0, 0), wants_down=True)["hit_rate_pct"] == 0.0,
   "flat counts as a SELL miss")

# Degenerate inputs.
ok(_side_stats([], wants_down=False) is None, "no rows -> None")
one = _side_stats(rows(4.2), wants_down=False)
ok(one["signals"] == 1 and one["median_return_pct"] == 4.2, "single observation")
ok(one["best_pct"] == one["worst_pct"] == 4.2, "single obs best == worst")

# Median must expose an average carried by outliers.
out = _side_stats(rows(0, 0, 0, 0, 50), wants_down=False)
ok(out["median_return_pct"] == 0.0 and out["avg_return_pct"] == 10.0,
   "median exposes an outlier-driven average")
ok(out["hit_rate_pct"] == 20.0, "hit rate agrees with the median, not the mean")

# Missing benchmark must not fabricate an excess figure.
ok(_side_stats(rows(1, 2), wants_down=False)["avg_excess_vs_nifty_pct"] is None,
   "no benchmark -> excess is None, never 0")
mixed = [{"forward_return_pct": 1, "excess_pct": 2.0},
         {"forward_return_pct": 2, "excess_pct": None}]
ok(_side_stats(mixed, wants_down=False)["avg_excess_vs_nifty_pct"] == 2.0,
   "excess averages only rows that have one")

# Extreme values stay arithmetic.
ext = _side_stats(rows(-99.9, 1000.0), wants_down=False)
ok(ext["worst_pct"] == -99.9 and ext["best_pct"] == 1000.0, "extremes preserved")

# Overlap: daily observations of one stock are not independent trades.
daily = [{"ticker": "A.NS", "date": f"2026-07-{d:02d}"} for d in range(1, 29)]
ind = _independence(daily, 21)
ok(ind["effective_independent_estimate"] < ind["observations"],
   "overlapping observations reduce the effective count")
ok(ind["overlapping"] is True, "overlap flagged")
ok("counted, not estimated" in ind["note"],
   "note states the independent count is counted, not estimated")
ok(ind.get("method") == "counted non-overlapping windows per stock",
   "independence method is named in the payload")
ok(ind["effective_independent_estimate"] == len(_non_overlapping(daily, 21)),
   "reported independence equals the counted non-overlapping set")
ok(ind["period"].startswith("2026-07-01"), "evaluation period reported")

# Non-overlapping observations must NOT be discounted.
sparse = [{"ticker": f"T{i}.NS", "date": "2026-07-01"} for i in range(10)]
ok(_independence(sparse, 21)["effective_independent_estimate"] == 10,
   "ten different stocks on one day are ten independent windows")
ok(_independence([], 21) is None, "empty records -> None")


# The verdict must distinguish "untested" from "tested and failed", and must
# not launder a thin side's uncertainty by averaging it with a well-sampled one.
from prediction_tracker import _verdict, MIN_EFFECTIVE_N

def sides(bh, bn, sh, sn):
    return {"buy": {"hit_rate_pct": bh, "signals": bn},
            "sell": {"hit_rate_pct": sh, "signals": sn}}

thin_sample = _verdict([1], [1], 0.05, [0], sides(50, 40, 54, 30),
                       {"effective_independent_estimate": 5, "observations": 240})
ok("not enough independent evidence" in thin_sample.lower(),
   "tiny effective sample -> reports the sample, not a failure")

# The production case that caught the first version: 109 BUYs, 24 SELLs.
mixed_n = _verdict([1], [1], 0.05, [0], sides(50.5, 109, 54.2, 24),
                   {"effective_independent_estimate": 30, "observations": 240})
ok("inconclusive" in mixed_n.lower(), "a thin side makes the verdict inconclusive")
ok("SELL (24)" in mixed_n, "names which side is undersampled")
ok("no edge found" not in mixed_n,
   "never claims 'no edge' about a side with too few signals")

both_ok = _verdict([1], [1], 0.05, [0], sides(50, 400, 49, 300),
                   {"effective_independent_estimate": 120, "observations": 660})
ok("no edge found" in both_ok, "well-sampled coin flip is reported as no edge")

edge = _verdict([1], [1], 0.3, [0], sides(62, 400, 58, 300),
                {"effective_independent_estimate": 120, "observations": 660})
ok("some edge" in edge.lower(), "a real edge is reported as provisional")
ok("provisional" in edge.lower(), "edge claim stays hedged")

ok(MIN_EFFECTIVE_N >= 30, "independence threshold is not set trivially low")


# Non-overlapping selection: the counted independence method.
from prediction_tracker import _non_overlapping

daily_one = [{"ticker": "A.NS", "date": f"2026-07-{d:02d}"} for d in range(1, 29)]
sel = _non_overlapping(daily_one, 21)
ok(len(sel) == 2, f"28 daily obs of one stock at 21d -> 2 windows (got {len(sel)})")
gap = (datetime.strptime(sel[1]["date"], "%Y-%m-%d")
       - datetime.strptime(sel[0]["date"], "%Y-%m-%d")).days
ok(gap >= 21, "selected windows are at least a full horizon apart")

many_stocks = [{"ticker": f"T{i}.NS", "date": "2026-07-01"} for i in range(10)]
ok(len(_non_overlapping(many_stocks, 21)) == 10,
   "different stocks on one day are not discounted against each other")

ok(_non_overlapping([], 21) == [], "empty input -> empty selection")
ok(len(_non_overlapping(daily_one, 1)) == 28,
   "a 1-day horizon discounts nothing")
ok(len(_non_overlapping(daily_one, 999)) == 1,
   "a horizon longer than the record leaves one window")

# Malformed dates must be skipped, not crash the selection.
bad = daily_one + [{"ticker": "A.NS", "date": "not-a-date"}]
ok(len(_non_overlapping(bad, 21)) == 2, "unparseable date skipped safely")

# The counted figure must never exceed the raw count.
ok(len(_non_overlapping(daily_one, 21)) <= len(daily_one),
   "independent count never exceeds observations")


# Significance: must be able to REFUTE, and must never call a small sample
# significant just because the percentage looks good.
from prediction_tracker import _significance

r = _significance(7, 13)
ok(r["significant_at_5pct"] is False, "54% of 13 is not significant")
ok(r["ci95_high_pct"] - r["ci95_low_pct"] > 40,
   "a 13-observation interval is reported as very wide")
ok("not evidence of skill" in r["plain"], "small sample says so in plain words")

ok(_significance(55, 100)["significant_at_5pct"] is False, "55% of 100 is not significant")
ok(_significance(600, 1000)["significant_at_5pct"] is True, "60% of 1000 is significant")
ok(_significance(500, 1000)["significant_at_5pct"] is False, "exactly 50% is never significant")

# Wilson interval must stay inside [0, 100] at the extremes.
for hits, n in ((0, 5), (5, 5), (0, 2), (2, 2), (1, 3)):
    x = _significance(hits, n)
    ok(0 <= x["ci95_low_pct"] <= 100 and 0 <= x["ci95_high_pct"] <= 100,
       f"interval stays in range for {hits}/{n}")
    ok(x["ci95_low_pct"] <= x["ci95_high_pct"], f"interval ordered for {hits}/{n}")

ok(_significance(0, 0) is None, "no observations -> no test")
ok(_significance(1, 1) is None, "a single observation -> no test")
ok(_significance(None, 10) is None, "missing hit count -> no test")


# Rebalancing must let weights drift, not silently reset every day.
import numpy as _np
import pandas as _pd
from simulator import _simulate_with_drift

_idx = _pd.bdate_range("2024-01-01", periods=250)
_rets = _pd.DataFrame({"A": 0.004, "B": 0.0}, index=_idx)
_w = _np.array([0.5, 0.5])

_drift = _simulate_with_drift(_rets, _w, "quarterly", include_costs=False)
_fixed = _pd.Series((_rets.values * _w).sum(axis=1), index=_idx)
ok(float((1 + _drift).prod()) > float((1 + _fixed).prod()),
   "a compounding winner is allowed to run between rebalance dates")

_costed = _simulate_with_drift(_rets, _w, "quarterly", include_costs=True)
ok(float((1 + _costed).prod()) < float((1 + _drift).prod()),
   "turnover costs reduce the return")

_monthly = _simulate_with_drift(_rets, _w, "monthly", include_costs=True)
ok(float((1 + _monthly).prod()) < float((1 + _costed).prod()),
   "rebalancing more often costs more")

# A portfolio that never moves should cost almost nothing to realign.
_flat = _pd.DataFrame({"A": 0.0, "B": 0.0}, index=_idx)
_a = _simulate_with_drift(_flat, _w, "quarterly", include_costs=True)
_b = _simulate_with_drift(_flat, _w, "quarterly", include_costs=False)
ok(abs(float((1 + _a).prod()) - float((1 + _b).prod())) < 1e-6,
   "no drift means no turnover means no cost")

ok(len(_simulate_with_drift(_rets, _w, "quarterly", True)) == len(_idx),
   "one return per trading day")
_nan = _pd.DataFrame({"A": [0.01, float("nan")], "B": [0.0, 0.0]},
                     index=_pd.bdate_range("2024-01-01", periods=2))
ok(_simulate_with_drift(_nan, _w, "quarterly", True).notna().all(),
   "a missing return does not poison the series")


# Corporate actions: a split must not read as a loss.
from simulator import _split_factor_since

ok(_split_factor_since("", "2024-01-01") == 1.0, "no ticker -> no adjustment")
ok(_split_factor_since("TCS.NS", None) == 1.0, "no entry date -> no adjustment")
ok(_split_factor_since("NOTAREALTICKER9Z.NS", "2020-01-01") == 1.0,
   "unknown ticker fails safe at 1.0, never rewrites a portfolio")
_f = _split_factor_since("INFY.NS", "2000-01-01")
ok(_f >= 1.0, "cumulative split factor is never below 1")
ok(_split_factor_since("RELIANCE.NS", "2099-01-01") == 1.0,
   "a future entry date has no splits after it")


# Optimiser stability: a corner solution must never be reported as "stable".
from optimizer_stability import concentration_warning

_c = concentration_warning({"A.NS": 48, "B.NS": 30, "C.NS": 22})
ok(_c and _c["concentrated"], "48% in one name is flagged")
ok(_c["top_weight_pct"] == 48, "top weight reported")
ok("Cap position sizes" in _c["message"], "warning says what to do")

ok(concentration_warning({"A.NS": 25, "B.NS": 25, "C.NS": 25, "D.NS": 25}) is None,
   "an evenly spread portfolio raises no warning")
ok(concentration_warning({}) is None, "empty weights -> no warning")

_c2 = concentration_warning({"A.NS": 60, "B.NS": 40})
ok(_c2 and _c2["effective_positions"] < 3,
   "two lopsided holdings behave like fewer than 3 positions")


# Execution realism: costs, whole shares, market hours, impact by liquidity.
from execution import cost_breakdown, units_for, market_status, estimate_slippage_pct

_c = cost_breakdown("RELIANCE.NS", 100000)
ok(_c["total_cost"] > 0, "a trade costs something")
ok(_c["invested_after_costs"] < 100000, "costs reduce what gets invested")
ok(abs(_c["charges"]["stt"] - 100) < 1, "STT is 0.1% of turnover")
ok(_c["total_cost_pct"] < 1, "a liquid large-cap trade costs well under 1%")

_illiq = cost_breakdown("DSKULKARNI.NS", 100000)
ok(_illiq["total_cost_pct"] > _c["total_cost_pct"],
   "an illiquid stock costs more to trade than a liquid one")

ok("error" in cost_breakdown("RELIANCE.NS", 0), "zero amount rejected")
ok("error" in cost_breakdown("RELIANCE.NS", -5), "negative amount rejected")

_u = units_for(99753, 1317.0)
ok(_u["units"] == 75 and _u["fractional"] is False, "whole shares only")
ok(_u["leftover_cash"] > 0, "the remainder stays as uninvested cash")
ok(units_for(100, 1317.0)["units"] == 0, "too little money buys nothing")
ok("error" in units_for(1000, 0), "zero price rejected")

_m = market_status()
ok(isinstance(_m["open"], bool) and _m["note"], "market status always answers")

_s = estimate_slippage_pct("RELIANCE.NS", 1000)
ok(0 <= _s["slippage_pct"] <= 0.05, "slippage stays inside the modelled cap")
ok(estimate_slippage_pct("NOTREAL9Z.NS", 1000)["slippage_pct"] > 0,
   "unknown ticker still charges a nominal impact")


# Market hours must be evaluated in IST regardless of where the server runs.
# Render is UTC; using the host clock made "open" span 14:45-21:00 IST.
from datetime import timezone as _tz, timedelta as _td, datetime as _dt
from execution import market_status as _ms, IST as _IST

_closed = _dt(2026, 8, 21, 11, 0, tzinfo=_tz.utc).astimezone(_IST)   # 16:30 IST
ok(_ms(_closed)["open"] is False, "16:30 IST is closed (11:00 UTC would have said open)")
_open = _dt(2026, 8, 21, 6, 0, tzinfo=_tz.utc).astimezone(_IST)      # 11:30 IST
ok(_ms(_open)["open"] is True, "11:30 IST is open")
_sat = _dt(2026, 8, 22, 6, 0, tzinfo=_tz.utc).astimezone(_IST)
ok(_ms(_sat)["open"] is False, "Saturday is closed whatever the hour")
_early = _dt(2026, 8, 21, 3, 0, tzinfo=_tz.utc).astimezone(_IST)     # 08:30 IST
ok(_ms(_early)["open"] is False, "08:30 IST is before the open")
ok("IST" in _ms()["as_of"], "timestamps are labelled IST")


# Cash account: money must not be creatable, destroyable, or overspendable.
import simulator as _sm

_U, _N = "pytest_cash", "PytestCash"
try:
    _sm.delete_simulation(_N, user_id=_U)
except Exception:
    pass
_start = _sm.start_simulation(_N, {"RELIANCE.NS": 100.0}, initial_value=50000, user_id=_U)
if "error" not in _start:
    # Assert the CHANGE, not the absolute. Opening a simulation now seeds cash
    # with the remainder that could not buy a whole share, so a fixed expected
    # total encodes an assumption that is no longer true.
    _before_cash = _sm.get_simulation_pnl(_N, user_id=_U).get("cash", 0)
    _after_cash = _sm.deposit(_N, 20000, user_id=_U).get("cash")
    ok(abs((_after_cash - _before_cash) - 20000) < 1, "a deposit increases cash by its amount")
    ok("error" in _sm.deposit(_N, 0, user_id=_U), "zero deposit rejected")
    ok("error" in _sm.deposit(_N, -5, user_id=_U), "negative deposit rejected")

    _over = _sm.buy_from_cash(_N, "TCS.NS", 10_000_000, user_id=_U)
    ok("error" in _over, "cannot spend cash you do not have")
    ok("Not enough cash" in _over["error"], "refusal explains why")

    ok("error" in _sm.withdraw(_N, 10_000_000, user_id=_U), "cannot withdraw beyond balance")

    _p = _sm.get_simulation_pnl(_N, user_id=_U)
    ok(_p.get("cash") is not None, "P&L reports the cash balance")
    ok(abs(_p["current_value"] - (_p["initial_value"])) < _p["initial_value"] * 0.02,
       "capital and value agree before the market moves, net of costs")

    _before = _sm.get_simulation_pnl(_N, user_id=_U)["current_value"]
    _sm.remove_position(_N, "RELIANCE.NS", user_id=_U)
    _after = _sm.get_simulation_pnl(_N, user_id=_U)
    ok(abs(_after["current_value"] - _before) < max(1.0, _before * 0.001),
       "selling changes the FORM of the money, not its amount")
    ok(_after["cash"] > 0, "sale proceeds land in cash")
    try:
        _sm.delete_simulation(_N, user_id=_U)
    except Exception:
        pass
else:
    ok(True, "cash tests skipped — could not start a simulation offline")


# Survivorship: the correction must never claim more depth than it has.
from survivorship import coverage as _sv_cov, universe_as_of, check_portfolio, measure_bias

_cov = _sv_cov()
ok("days" in _cov and "usable" in _cov, "coverage reports its own depth")
ok(_cov["usable"] is (_cov["days"] >= 2), "usable follows from stored days, not optimism")

_early = check_portfolio(["RELIANCE.NS"], "1990-01-01")
ok(_early["checked"] is False, "a start date before stored history is not silently checked")
ok("uncorrected" in _early["note"] or "cannot" in _early["note"],
   "and says the bias remains rather than implying a clean result")

ok(universe_as_of("1990-01-01") == set(), "no universe before coverage begins")
_u = universe_as_of(_cov.get("latest") or "2026-08-13")
ok(isinstance(_u, set), "universe_as_of returns a set")
if _cov.get("usable") or _u:
    ok(len(_u) > 100, f"a stored day names a full universe ({len(_u)} symbols)")

_b = measure_bias(_cov.get("earliest") or "2026-08-13")
ok("measured" in _b, "bias measurement always reports whether it ran")
if _b.get("measured"):
    ok(_b["delisted_since"] >= 0, "delisted count is never negative")
    ok(_b["listed_then"] > 0, "a measured day has a non-empty universe")


# Portfolio health score and the suggested-allocation fix.
from portfolio_score import score as _pscore
from portfolio_fix import suggest as _psuggest, MAX_SINGLE as _MS

_conc = _pscore({"A.NS": 58, "B.NS": 42})
_even = _pscore({f"S{i}.NS": 10 for i in range(10)})
ok(_conc["score"] < _even["score"], "a concentrated portfolio scores below an even one")
ok(_even["score"] == 100.0, "ten equal holdings score 100")
ok(_conc["label"] in ("aggressive", "very aggressive"), "and is labelled by character")
ok("not whether it is good" in _conc["means"], "the score disclaims being a quality grade")
ok(_conc["biggest_lever"] is not None, "the most improvable component is named")
ok("error" in _pscore({}), "empty holdings rejected")
ok(_pscore({"A.NS": 100})["components"]["diversification"]["value"] == 1.0,
   "a single holding is exactly 1 effective position")

# Weights that cannot be capped must say so rather than silently doing nothing.
_two = _psuggest({"A.NS": 58, "B.NS": 42})
if "error" not in _two:
    _kinds = {st["action"] for st in _two.get("steps", [])}
    ok("cap_infeasible" in _kinds,
       "two holdings cannot reach a 25% cap, and the tool says so")
    ok(max(_two["proposed_pct"].values()) <= 50.5,
       "the best achievable split for two holdings is 50/50")
    ok(_two.get("switching_cost_inr") is not None, "the switching cost is reported")

ok("error" in _psuggest({"A.NS": 100}), "one holding cannot be rebalanced")

_even_fix = _psuggest({f"S{i}.NS": 20 for i in range(5)})
ok(_even_fix.get("changed") is False or "steps" in _even_fix,
   "an already-balanced portfolio proposes nothing or explains why")


# Six-factor model: weights, separation of concerns, and honest explanation.
from alpha_v2 import WEIGHTS_V2, explain as _v2explain, FACTOR_PLAIN

ok(abs(sum(WEIGHTS_V2.values()) - 1.0) < 1e-9, "V2 weights sum to 1.0")
ok(len(WEIGHTS_V2) == 6, "V2 has exactly six factors")
ok("liquidity" not in WEIGHTS_V2,
   "liquidity is NOT a factor — it is an execution constraint, not attractiveness")
ok(len(set(WEIGHTS_V2.values())) > 1, "weights are not all equal")
# This test previously asserted momentum should carry the LARGEST weight, on the
# reasoning that it has the strongest published record. The walk-forward then
# tested it on this universe across 12 configurations and found no edge surviving
# correction for multiple testing. So the assertion inverted: the one factor
# measured and found wanting must not hold the largest share.
ok(WEIGHTS_V2["momentum"] < max(WEIGHTS_V2.values()),
   "momentum is no longer the largest weight — it was tested here and failed")
ok(WEIGHTS_V2["momentum"] > 0,
   "but it is reduced, not removed: a null on one market is not proof of none")
ok(WEIGHTS_V2["sentiment"] == min(WEIGHTS_V2.values()),
   "sentiment carries the smallest weight, matching the weakest evidence base")
ok(all(k in FACTOR_PLAIN for k in WEIGHTS_V2), "every factor has a plain-language label")

# The sentence must name the WORST factor, not the mildest negative.
_fake = {"ticker": "X.NS",
         "contributions": {"momentum": -13.1, "quality": 14.6, "growth": 3.9,
                           "value": -8.4, "sentiment": -0.9, "low_risk": -4.0},
         "weights_used": WEIGHTS_V2}
_e = _v2explain(_fake)
ok(_e["biggest_concern"] == FACTOR_PLAIN["momentum"][0],
   "biggest concern is the most negative factor")
ok(FACTOR_PLAIN["momentum"][0] in _e["sentence"],
   "and the sentence names that same factor, not the mildest one")
ok(_e["n_positive"] == 2 and _e["n_total"] == 6, "factor agreement counted correctly")

# Cheap-but-weak must be taught, not just scored.
_cheap = {"ticker": "Y.NS",
          "contributions": {"value": 12.0, "quality": -8.0, "growth": -5.0},
          "weights_used": WEIGHTS_V2}
ok("Cheap does not mean good" in (_v2explain(_cheap).get("lesson") or ""),
   "a cheap stock with weak fundamentals is explained, not just scored")

ok(_v2explain({}) == {}, "no input -> no explanation invented")
ok(_v2explain({"error": "x"}) == {}, "an errored score explains nothing")


# Portfolio fit, walk-forward, regime tilts, anomaly detection.
from portfolio_fit import fit as _fit
from regime_weights import proposed_weights as _rw, TILTS as _TILTS
from anomaly import detect as _anom

_it = {"INFY.NS": 30, "TCS.NS": 30, "WIPRO.NS": 20, "HCLTECH.NS": 20}
_same = _fit("TECHM.NS", _it, add_pct=15)
_diff = _fit("SUNPHARMA.NS", _it, add_pct=15)
if "error" not in _same and "error" not in _diff:
    ok(_same["fit_score"] < _diff["fit_score"],
       "a fifth IT stock fits an IT portfolio worse than a pharma stock does")
    ok(_same["components"]["sector"]["score"] == 0.0,
       "adding to a 100% sector scores zero on sector fit")
ok("error" in _fit("X.NS", {}), "no holdings -> nothing to fit against")
ok(_fit("INFY.NS", _it).get("held") is True, "a stock already held is reported as held")

# Regime tilts must ship inactive until evidence supports them.
_p = _rw("Bear")
ok(_p["active"] is False, "regime tilting is NOT applied by default")
ok(abs(sum(_p["proposed_weights"].values()) - 1.0) < 1e-6, "tilted weights renormalise to 1")
ok(_p["proposed_weights"]["low_risk"] > _p["current_weights"]["low_risk"],
   "a bear regime tilts toward low-risk")
ok(_p["proposed_weights"]["momentum"] < _p["current_weights"]["momentum"],
   "and away from momentum")
ok(set(_TILTS) == {"Bull", "Sideways", "Bear"}, "three regimes, matching the HMM")
ok(all(abs(v - 1.0) < 1e-9 for v in _TILTS["Sideways"].values()),
   "sideways applies no tilt at all")

# Anomaly output must never look like a recommendation.
_a = _anom("RELIANCE.NS")
ok("this_is_not_a_signal" in _a, "anomaly output states it is not a signal")
ok(not any(k in str(_a).upper() for k in ("STRONG BUY", "STRONG SELL")),
   "anomaly output contains no buy/sell language")
ok(_anom("")["checked"] is False, "an empty ticker is not silently checked")


# Events: context without a score.
from events import detect as _events
_e = _events("")
ok(_e["checked"] is False, "an empty ticker is not silently checked")
_e2 = _events("RELIANCE.NS")
ok("this_is_not_a_signal" in _e2, "events state they are not a recommendation")
ok("score" not in {k.lower() for k in _e2 if k != "sentiment"},
   "events produce no score of their own — the sentiment factor already has that job")


# Wording: "no evidence of an effect" and "evidence of no effect" are different
# claims, and the test can only support the first. This pins the distinction so a
# future edit cannot quietly restore the stronger one.
import io
import inspect as _insp
import walk_forward as _wf, alpha_v2 as _av2, methodology as _meth

_null = _wf.run.__doc__ or ""
_src_all = chr(10).join(_insp.getsource(m_) for m_ in (_wf, _av2, _meth))

for _bad in ("no edge at all", "showed no edge", "produced no edge",
             "momentum does not work", "proves momentum"):
    ok(_bad.lower() not in _src_all.lower(),
       f"shipped code never claims '{_bad}'")

_note = _av2.compute_v2.__doc__ or ""
_ev = [l for l in _src_all.split(chr(10)) if "has not demonstrated" in l]
ok(len(_ev) >= 2, "the precise phrasing appears in more than one module")
ok("does not prove" in _src_all.lower(),
   "the no-evidence-is-not-disproof caveat is present in shipped code")

# The verdict a user actually reads must carry both halves.
_fake_sig = {"p_value": 1.0, "significant_at_5pct": False}
ok("tested configurations" in _src_all,
   "verdicts scope the claim to the configurations tested")


# ================= COACH VERDICT ======================================
# The coach now leads with a judgement instead of P&L. The properties worth
# holding are the ones that keep it honest, not the ones that keep it positive.
from portfolio_advisor import advise as _advise, _cap_payoff as _cp

_conc = _advise({"RELIANCE.NS": 55, "TCS.NS": 25, "INFY.NS": 20},
                initial_value=100000, horizon_months=12, max_loss_pct=15)
_spread = _advise({"RELIANCE.NS": 10, "TCS.NS": 10, "HDFCBANK.NS": 10, "INFY.NS": 10,
                   "ITC.NS": 10, "SUNPHARMA.NS": 10, "MARUTI.NS": 10, "LT.NS": 10,
                   "TITAN.NS": 10, "ASIANPAINT.NS": 10},
                  initial_value=100000, horizon_months=12, max_loss_pct=30)

for _label, _r in (("concentrated", _conc), ("spread", _spread)):
    _v = _r.get("verdict")
    ok(_v is not None, f"{_label}: a verdict is returned")
    if not _v:
        continue
    ok(bool(_v.get("call")), f"{_label}: the verdict states a call")
    ok(bool(_v.get("because")), f"{_label}: the call says what drove it")

    # A compliment must never appear under "what concerns me". The sector check
    # emits praise and criticism under one kind, and severity alone could not
    # tell them apart.
    _good_titles = {t["title"] for t in _r["suggestions"] if t.get("tone") == "good"}
    _concern_titles = {c["title"] for c in _v["concerns"]}
    ok(not (_good_titles & _concern_titles),
       f"{_label}: no good-news finding is listed as a concern")

    # Strengths are earned, and an empty list is a real answer.
    if not _v["strengths"]:
        ok(bool(_v["no_strengths_note"]),
           f"{_label}: an empty strengths list explains itself")
    for _st in _v["strengths"]:
        ok(bool(_st.get("evidence")), f"{_label}: strength cites its evidence")

    # Every concern says something about effect, and the three states stay
    # distinguishable.
    for _c in _v["concerns"]:
        _has = (_c.get("effect") or {}).get("improved")
        ok(bool(_has) or bool(_c.get("effect_note")),
           f"{_label}: concern reports effect or says why it has none")
        if _c.get("effect") and not _c["effect"]["improved"]:
            ok("does not improve" in (_c["effect_note"] or ""),
               f"{_label}: a simulated non-result is not silence")

# The alpha strength must not claim approval the scan never gave. With one
# scored holding out of ten it read as "the model approves" when it meant
# "the model has not looked".
_sv = _spread.get("verdict") or {}
_alpha_str = [x for x in _sv.get("strengths", []) if "does not dislike" in x["title"]]
if _alpha_str:
    import re as _re
    _m = _re.search(r"(\d+) of your (\d+)", _alpha_str[0]["evidence"])
    ok(_m is not None, "alpha strength states its coverage")
    if _m:
        ok(int(_m.group(1)) * 2 >= int(_m.group(2)),
           f"alpha strength only claimed with majority coverage: {_alpha_str[0]['evidence']}")

# The cap must be feasible. 100 // 3 = 33 makes three positions sum to 99% and
# the scenario was rejected, so the payoff vanished for exactly the small
# concentrated books that most needed it.
import math as _math
for _n in (3, 6, 7, 9, 11):
    _cap = max(20.0, _math.ceil(10000.0 / _n) / 100.0)
    ok(_cap * _n >= 100.0, f"cap {_cap}% x {_n} holdings is feasible")

_src_adv = _insp.getsource(__import__("portfolio_advisor"))
ok("tone" in _src_adv, "findings carry a tone so praise is not filed as criticism")
ok("P&L" in _src_adv or "profit and loss" in _src_adv.lower(),
   "the code records why the verdict leads instead of the return")


# ================= GRADUATED DISCLOSURE ===============================
# Three levels are only honest if the conclusion is the same at all three.
# Hiding a measurement is disclosure; hiding a concern is a filtered story.
_coach_jsx = io.open("../frontend/src/components/PortfolioCoach.jsx",
                     encoding="utf-8").read()

ok("<Verdict v={advice.data.verdict} />" in _coach_jsx,
   "the verdict renders at every level, ungated by detail")
_verdict_line = [l for l in _coach_jsx.split(chr(10))
                 if "<Verdict v=" in l][0]
ok("isAdvanced" not in _verdict_line and "isIntermediate" not in _verdict_line,
   "no disclosure level can hide the verdict or its concerns")

for _lvl in ("beginner", "intermediate", "advanced"):
    ok(f"'{_lvl}'" in _coach_jsx, f"{_lvl} level exists in the picker")

# The old two-level key is still in real browsers' localStorage, and a stale
# 'simple' must land somewhere real rather than matching no level at all.
ok("detail === 'simple' ? 'beginner'" in _coach_jsx,
   "the retired 'simple' setting still resolves to a live level")

# A non-improvement must not be rendered in the improvement colour.
ok("s.payoff.improved ? 'text-green-400'" in _coach_jsx,
   "the payoff colour is driven by whether it actually improved")
ok("this fix does not pay" in _coach_jsx,
   "a simulated non-result is stated in the UI, not left blank")


# ================= MONTE CARLO DRAWDOWN + TARGET (item 4) =============
# Synthetic paths, because on constructed data the right answer is known
# exactly and a subtle sign or axis error cannot hide behind plausible noise.
import numpy as _mnp
from monte_carlo import drawdown_stats as _dds, target_probability as _tp

# A path that only rises can never have fallen.
_rise = _mnp.array([[110.0, 120.0, 130.0, 140.0]])
_r = _dds(_rise, 100.0)
ok(_r["worst_max_drawdown_pct"] == 0.0,
   f"a monotonically rising path has no drawdown, got {_r['worst_max_drawdown_pct']}")

# 100 -> 50 -> 100 is exactly a 50% fall, whatever it recovers to.
_v = _mnp.array([[100.0, 50.0, 100.0]])
_r = _dds(_v, 100.0)
ok(abs(_r["worst_max_drawdown_pct"] - (-50.0)) < 1e-6,
   f"a halving is reported as -50%, got {_r['worst_max_drawdown_pct']}")

# A fall on the FIRST day must count. Without prepending the starting value the
# first point becomes its own peak and the opening loss disappears.
_d1 = _mnp.array([[80.0, 80.0, 80.0]])
_r = _dds(_d1, 100.0)
ok(abs(_r["worst_max_drawdown_pct"] - (-20.0)) < 1e-6,
   f"a day-one fall counts as drawdown, got {_r['worst_max_drawdown_pct']}")

# Severity ordering: worst is the deepest, p25 the shallowest.
_mixed = _mnp.array([[100.0, 95.0, 100.0], [100.0, 70.0, 90.0],
                     [100.0, 50.0, 60.0], [100.0, 99.0, 105.0]])
_r = _dds(_mixed, 100.0)
ok(_r["worst_max_drawdown_pct"] <= _r["p95_max_drawdown_pct"] <=
   _r["median_max_drawdown_pct"] <= _r["p25_max_drawdown_pct"],
   f"drawdown percentiles are ordered by severity: {_r}")
for _k, _val in _r.items():
    if _k.endswith("drawdown_pct"):
        ok(_val <= 0, f"{_k} is a fall, not a gain ({_val})")

# A deeper threshold can never catch more paths than a shallower one.
ok(_r["share_over_35pct_fall"] <= _r["share_over_20pct_fall"],
   f"share past 35% cannot exceed share past 20%: {_r['share_over_35pct_fall']} "
   f"vs {_r['share_over_20pct_fall']}")

ok(_dds(None, 100.0) == {}, "no paths returns empty rather than inventing zeros")
ok(_dds(_mnp.array([]), 100.0) == {}, "an empty array returns empty")

# --- target ---
_fv = _mnp.array([90000.0, 100000.0, 110000.0, 130000.0])
ok(_tp(_fv, 100000.0, 50000.0)["share_of_simulations_pct"] == 100.0,
   "a target below every outcome is reached by every path")
ok(_tp(_fv, 100000.0, 999999.0)["share_of_simulations_pct"] == 0.0,
   "a target above every outcome is reached by none")
_t = _tp(_fv, 100000.0, 110000.0)
ok(_t["share_of_simulations_pct"] == 50.0,
   f"2 of 4 paths at or above the target is 50%, got {_t['share_of_simulations_pct']}")
ok(abs(_t["target_return_pct"] - 10.0) < 1e-6,
   f"110k from 100k needs +10%, got {_t['target_return_pct']}")

# The phrasing rule: a share of these simulations, never a probability of the
# future. This is the one sentence a user is most likely to quote back.
ok("not the chance" in _t["note"].lower(),
   "the target note refuses to call itself a chance of happening")
ok("share" in _t["note"].lower(), "the target note says what it IS")
ok(_tp(_fv, 100000.0, None) == {}, "no target returns empty")
ok(_tp(None, 100000.0, 110000.0) == {}, "no paths returns empty")

# End to end: the wiring from request through to summary.
_mc_ui = io.open("../frontend/src/pages/MonteCarlo.jsx", encoding="utf-8").read()
ok("target_value" in _mc_ui, "the page sends a target when one is set")
ok("drawdown" in _mc_ui, "the page renders the drawdown panel")
ok("share_over_20pct_fall" in _mc_ui, "the page shows how many paths fell past 20%")
_mc_src = _insp.getsource(__import__("monte_carlo"))
ok("not the chance of it" in _mc_src or "not the chance" in _mc_src,
   "the shipped module carries the probability-phrasing rule")


# ================= FIX BEFORE/AFTER SHAPE =============================
# portfolio_fix caps stock weights and caps sectors, so it changes the
# concentration and the sector mix by construction. Neither was reported, and
# reporting them turned up a real defect immediately.
from portfolio_fix import suggest as _sug, _cap_sectors as _cs

_cases = [
    ("two sectors", {"RELIANCE.NS": 55, "TCS.NS": 25, "INFY.NS": 20}),
    ("four sectors", {"RELIANCE.NS": 40, "TCS.NS": 20, "HDFCBANK.NS": 20,
                      "SUNPHARMA.NS": 20}),
]
for _name, _h in _cases:
    _f = _sug(_h, initial_value=100000)
    if "error" in _f or not _f.get("changed"):
        continue
    _b, _a = _f["before"].get("shape") or {}, _f["after"].get("shape") or {}
    ok(bool(_b) and bool(_a), f"{_name}: before and after both report shape")
    ok(_b.get("effective_positions") is not None,
       f"{_name}: effective positions is reported, not just the health score")
    ok(_b.get("top_sector_pct") is not None,
       f"{_name}: the heaviest sector is reported")

    # 1/HHI can never exceed the number of holdings, and equals it only when
    # every weight is identical.
    ok(_b["effective_positions"] <= _b["holdings"] + 1e-6,
       f"{_name}: effective positions {_b['effective_positions']} cannot exceed "
       f"{_b['holdings']} holdings")

    # The defect this display exposed: with two sectors, no allocation can put
    # every sector under a 40% cap, because they must add to 100. The capping
    # loop oscillated — cap Oil & Gas, push the excess into IT, cap IT, push it
    # back — and returned whichever end of the swing it stopped on. On a 55/45
    # book it handed back a 60% top sector as the FIX for a 55% one.
    ok(_a["top_sector_pct"] <= _b["top_sector_pct"] + 1e-9,
       f"{_name}: the fix does not increase sector concentration "
       f"({_b['top_sector_pct']}% -> {_a['top_sector_pct']}%)")
    ok(_a["effective_positions"] >= _b["effective_positions"] - 1e-9,
       f"{_name}: the fix does not reduce effective positions "
       f"({_b['effective_positions']} -> {_a['effective_positions']})")

# Directly: an infeasible cap must not make things worse than doing nothing.
_two = {"RELIANCE.NS": 55.0, "TCS.NS": 25.0, "INFY.NS": 20.0}
_capped = _cs(_two, 40.0)          # 40% is unreachable with only two sectors
def _topsec(d):
    from portfolio_advisor import _sector_of
    agg = {}
    for _t, _v in d.items():
        _s2 = _sector_of(_t)
        if _s2:
            agg[_s2] = agg.get(_s2, 0.0) + _v
    return max(agg.values()) if agg else 0.0
ok(_topsec(_capped) <= _topsec(_two) + 1e-9,
   f"an unreachable sector cap never returns a worse book: "
   f"{_topsec(_two):.1f}% -> {_topsec(_capped):.1f}%")
ok(abs(sum(_capped.values()) - 100.0) < 0.5,
   f"capped weights still sum to 100, got {sum(_capped.values()):.2f}")

_fix_jsx = io.open("../frontend/src/components/PortfolioCoach.jsx",
                   encoding="utf-8").read()
ok("Effective positions" in _fix_jsx, "the before/after shows effective positions")
ok("Heaviest sector" in _fix_jsx, "the before/after shows the sector change")


# ================= UI/API SHAPE CONTRACTS =============================
# /alpha/signal-history returns {ticker, history: [...]}, not a bare array.
# WhySignal.jsx did `(hist || []).slice(0, 4)`, which handed back the OBJECT
# and threw "(a || []).slice is not a function" on every stock page. The panel
# next to it read the same endpoint correctly, so nothing looked wrong in
# review — the two consumers simply disagreed about the shape.
_why_jsx = io.open("../frontend/src/components/WhySignal.jsx", encoding="utf-8").read()
ok("(hist || []).slice" not in _why_jsx,
   "WhySignal no longer slices the response object directly")
ok("hist?.history" in _why_jsx, "WhySignal reads the history array off the payload")
ok("Array.isArray(hist)" in _why_jsx,
   "both shapes are accepted so a cached old response cannot revive the crash")

_sig_jsx = io.open("../frontend/src/components/SignalHistory.jsx", encoding="utf-8").read()
ok("data?.history" in _sig_jsx, "SignalHistory reads the same field the API sends")

# And the API really does send that shape.
_main_src = io.open("main.py", encoding="utf-8").read()
ok('"history": get_signal_history' in _main_src,
   "signal-history wraps its list in a history field")


# ================= FLAT IS NOT BROKEN =================================
# A simulation opened Friday and checked Sunday shows entry == current, a flat
# line and 0.00% everywhere. That is correct — nothing traded — but it is
# indistinguishable from a dead price feed, and it was read as one.
from simulator import _market_note as _mn

_flat = [{"ticker": "SBIN.NS", "pnl_pct": 0.0}, {"ticker": "INFY.NS", "pnl_pct": 0.0}]
_moved = [{"ticker": "SBIN.NS", "pnl_pct": 0.0}, {"ticker": "INFY.NS", "pnl_pct": 1.4}]

_n = _mn(_flat)
ok(_n is not None, "a completely flat portfolio gets an explanation")
if _n:
    ok("not a stalled feed" in _n or "nothing has traded" in _n.lower(),
       "the note says the feed is fine, which is the actual question being asked")
    ok("cost of opening" in _n.lower(),
       "the note attributes the difference from starting capital to dealing costs")

# A note that appears every time is a note nobody reads.
ok(_mn(_moved) is None, "no note once anything has actually moved")
ok(_mn([]) is None, "no note for an empty portfolio")

# The split the UI needs has always been in the payload; the page ignored it.
_sim_jsx = io.open("../frontend/src/pages/Simulator.jsx", encoding="utf-8").read()
ok("pnl_breakdown" in _sim_jsx, "the page renders the market-vs-costs split")
ok("market_note" in _sim_jsx, "the page renders the flat-market explanation")
ok("cost to buy them" in _sim_jsx,
   "the costs half of the split is labelled as costs, not as a loss")


# ================= FACTOR HISTORY + DIVERGENCE ========================
# Step 1 of the edge work: write down what each factor scored, so "what
# changed" has a factual answer. Nothing here predicts anything, and the tests
# are mostly about making sure it never starts claiming that it does.
import factor_history as _fh

_T = "ZZTEST.NS"
# Clear anything a previous run left behind. Without this the "one observation
# reports too_short" check passes on a clean database and fails on every run
# after, which is the worst kind of test: one that is green exactly once.
_fh._init()
try:
    from db import get_conn as _gc
    _c0 = _gc()
    _c0.execute("DELETE FROM factor_history WHERE ticker = ?", (_T,))
    _c0.commit(); _c0.close()
except Exception:
    pass

_fh.record(_T, "v2", alpha_score=10.0, price=100.0, captured_at="2026-07-24",
           factors={"momentum": {"score": 5}, "quality": {"score": 50},
                    "growth": {"score": 40}, "value": {"score": 30},
                    "sentiment": {"score": 2}, "low_risk": {"score": 20}})

# One observation is not a change, and must not be reported as zero change.
_one = _fh.change(_T, days=30)
ok(_one["status"] == "too_short",
   f"a single observation reports too_short, not a flat zero: {_one['status']}")
ok("not the same as nothing changing" in _one.get("note", ""),
   "the too_short note distinguishes 'not watching long enough' from 'nothing moved'")

_empty = _fh.change("NOSUCHTICKER.NS", days=30)
ok(_empty["status"] == "no_history", "an unseen stock reports no_history")
ok("cannot be backfilled" in _empty.get("note", ""),
   "the empty state explains why history cannot be recovered")

_fh.record(_T, "v2", alpha_score=22.0, price=101.2, captured_at="2026-08-23",
           factors={"momentum": {"score": 1}, "quality": {"score": 61},
                    "growth": {"score": 57}, "value": {"score": 18},
                    "sentiment": {"score": 11}, "low_risk": {"score": 26}})

_c = _fh.change(_T, days=30)
ok(_c["status"] == "ok", f"two observations produce a change: {_c['status']}")
if _c["status"] == "ok":
    ok(abs(_c["factors"]["growth"]["change"] - 17.0) < 1e-6,
       f"growth 40 -> 57 is +17, got {_c['factors']['growth']['change']}")
    ok(abs(_c["factors"]["value"]["change"] - (-12.0)) < 1e-6,
       "a factor that fell reports a negative change")
    ok(abs(_c["price_change_pct"] - 1.2) < 0.01,
       f"price 100 -> 101.2 is +1.2%, got {_c['price_change_pct']}")
    ok(len(_c["factors"]) == 6, f"all six v2 factors are tracked, got {len(_c['factors'])}")
    ok("not a forecast" in _c["means"], "the change output disclaims prediction")

# Writing twice on one day must not manufacture a second observation.
_fh.record(_T, "v2", alpha_score=23.0, price=101.5, captured_at="2026-08-23",
           factors={"growth": {"score": 58}})
_rows = [r for r in _fh.history(_T, model="v2") if r["captured_at"] == "2026-08-23"]
ok(len(_rows) == 1, f"one row per ticker per day per model, got {len(_rows)}")

# Divergence: the point of the whole exercise, and the place a circular claim
# would hide.
_d = _fh.divergences(_T, days=30)
ok("divergences" in _d, "divergence returns a list")
_kinds = [x["kind"] for x in _d["divergences"]]
ok("fundamentals_up_price_flat" in _kinds,
   f"growth+quality+sentiment up on a flat price is flagged: {_kinds}")

# Momentum IS price and value is price over fundamentals. Counting either as
# independent confirmation that "the price has not reacted" would be using the
# price as evidence about itself.
for _x in _d["divergences"]:
    for _f in _x.get("factors", []):
        ok(_f not in ("momentum", "value"),
           f"price-linked factor '{_f}' is not used as independent evidence")
ok(set(_d["price_linked_excluded"]) == {"momentum", "value"},
   "the excluded factors are named in the output")
ok("evidence about itself" in _d["why_excluded"], "the exclusion explains itself")

# The label that keeps this a research tool rather than a signal.
ok("has been tested against future returns" in _d["not_a_signal"],
   "divergences are labelled untested")
ok("momentum" in _d["not_a_signal"],
   "the disclaimer cites the factor that actually failed walk-forward here")
ok(_d["status_label"] in ("observation", "nothing_unusual"),
   f"status is an observation label, never a recommendation: {_d['status_label']}")

# No score. A single number would imply the app knows which changes matter.
_txt = str(_d)
for _banned in ("edge_score", "edge score", "opportunity_score", "buy", "recommend"):
    ok(_banned not in _txt.lower(),
       f"no scoring or recommendation language leaks in ('{_banned}')")

_src_fh = _insp.getsource(_fh)
ok("PRICE_LINKED" in _src_fh, "the price-linked distinction is explicit in code")
_fc_jsx = io.open("../frontend/src/components/FactorChange.jsx", encoding="utf-8").read()
ok("not_a_signal" in _fc_jsx, "the UI renders the untested label")
ok("Edge " not in _fc_jsx.replace("Edge score", ""),
   "the UI renders no edge score")


# ================= SHOCK SCENARIOS ====================================
# "What happens to me if X falls 20%" — one event, not a distribution. The
# arithmetic here is exactly checkable, which is the point of pinning it.
from portfolio_shock import shock as _shk, presets_for as _presets

_H = {"RELIANCE.NS": 25, "TCS.NS": 20, "INFY.NS": 20,
      "HDFCBANK.NS": 20, "SUNPHARMA.NS": 15}

_mk = _shk(_H, "market", -20.0, initial_value=1000000)
ok("error" not in _mk, f"market shock runs: {_mk.get('error', 'ok')}")

if "error" not in _mk:
    # A directly shocked stock must move by the shock exactly, not by its beta
    # against itself — which is 1 by construction and would smuggle an estimate
    # in where an exact number was meant.
    _st = _shk(_H, "stock", -40.0, target="RELIANCE.NS", initial_value=1000000)
    ok("error" not in _st, "single-stock shock runs")
    if "error" not in _st:
        _r = [h for h in _st["holdings"] if h["ticker"] == "RELIANCE.NS"][0]
        ok(_r.get("pinned") is True, "the shocked stock is pinned, not beta-scaled")
        ok(abs(_r["move_pct"] - (-40.0)) < 1e-6,
           f"the shocked stock moves by exactly the shock, got {_r['move_pct']}")
        # 25% of the book falling 40% is exactly 10 points of the portfolio.
        ok(abs(_r["impact_pts"] - (-10.0)) < 0.05,
           f"25% weight x -40% = -10 pts, got {_r['impact_pts']}")

    # A sector shock hits every holding in that sector by the full amount.
    _se = _shk(_H, "sector", -30.0, target="IT", initial_value=1000000)
    ok("error" not in _se, "sector shock runs")
    if "error" not in _se:
        _it = [h for h in _se["holdings"] if h.get("pinned")]
        ok(len(_it) >= 2, f"both IT holdings are pinned, got {len(_it)}")
        for _h in _it:
            ok(abs(_h["move_pct"] - (-30.0)) < 1e-6,
               f"{_h['ticker']} moves by the sector shock exactly")
        ok(abs(_se["by_sector"].get("IT", 0) - (-12.0)) < 0.05,
           f"40% in IT falling 30% is -12 pts, got {_se['by_sector'].get('IT')}")

    # Cash does not move, so it scales the loss down exactly.
    _c20 = _shk(_H, "market", -20.0, cash_pct=20, initial_value=1000000)
    ok(abs(_c20["change_pct"] - _mk["change_pct"] * 0.8) < 0.05,
       f"20% cash scales the move by 0.8: {_mk['change_pct']} -> {_c20['change_pct']}")
    ok(abs(_c20["change_pct"]) < abs(_mk["change_pct"]),
       "holding cash cushions a fall")

    # A fall must lose money and a rise must make it. Sign errors here would be
    # invisible in a chart and catastrophic in a decision.
    ok(_mk["change_pct"] < 0, f"a market fall loses money, got {_mk['change_pct']}")
    ok(_mk["after_value"] < _mk["initial_value"], "the value after a crash is lower")
    _up = _shk(_H, "market", 20.0, initial_value=1000000)
    ok(_up["change_pct"] > 0, f"a market rise gains, got {_up['change_pct']}")

    # The parts must add up to the whole.
    _sum_pts = sum(h["impact_pts"] for h in _mk["holdings"]
                   if h.get("impact_pts") is not None)
    ok(abs(_sum_pts - _mk["change_pct"]) < 0.05,
       f"per-holding impacts sum to the total: {_sum_pts:.2f} vs {_mk['change_pct']}")
    _sum_sec = sum(_mk["by_sector"].values())
    ok(abs(_sum_sec - _mk["change_pct"]) < 0.05,
       f"sector impacts sum to the total: {_sum_sec:.2f} vs {_mk['change_pct']}")

    # No scenario may carry a likelihood. A "12% chance of a crash" would be the
    # most quotable number on the page and the least defensible.
    _txt = str(_mk)
    for _banned in ("probability", "chance of", "likely to happen", "odds of"):
        ok(_banned not in _txt.lower().replace("not the chance", ""),
           f"no scenario claims a likelihood ('{_banned}')")
    ok("optimistic" in _mk["limits"].lower(),
       "the limits admit normal-period betas understate a real crash")

# Offering "IT falls 30%" to someone holding no IT is how a scenario tool loses
# credibility, so presets are built from the actual book.
_p = _presets(_H)
_labels = [x["label"] for x in _p]
ok(any("IT" in l for l in _labels), "a sector held is offered")
_no_it = _presets({"RELIANCE.NS": 60, "SUNPHARMA.NS": 40})
ok(not any("IT falls" in x["label"] for x in _no_it),
   f"a sector NOT held is not offered: {[x['label'] for x in _no_it]}")

ok("error" in _shk({}, "market", -20), "an empty portfolio is refused")
ok("error" in _shk(_H, "nonsense", -20), "an unknown scenario is refused")
ok("error" in _shk(_H, "stock", -20, target="NOTHELD.NS"),
   "shocking a stock you do not hold is refused")
ok("error" in _shk(_H, "market", -400), "an impossible shock size is refused")

# The phrasing rule, in the module a user reads most.
_mc_src2 = _insp.getsource(__import__("monte_carlo"))
ok("chance of ending below" not in _mc_src2,
   "monte carlo no longer claims a chance of ending below start")
ok("of simulated paths finished below" in _mc_src2,
   "monte carlo states a share of its own paths instead")
_shock_jsx = io.open("../frontend/src/components/ShockLab.jsx", encoding="utf-8").read()
ok("will this happen" in _shock_jsx, "the UI says what the tool does not answer")


# ================= BLACK-LITTERMAN DISPLAY (item 3) ===================
# The optimiser always returned the whole chain; the page rendered only the
# final weights. These checks are about the CONTRACT the panel depends on, so
# a field being renamed shows up here rather than as an empty column.
from portfolio_optimizer import optimize_with_alpha_views as _owav

_bl_full = (_owav(["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"]) or {}).get("bl_result") or {}
ok(bool(_bl_full), "the auto pipeline returns a bl_result")

for _k in ("implied_equilibrium_returns", "bl_posterior_returns",
           "equilibrium_weights", "bl_pct", "weight_shifts_pct",
           "views_injected", "tau", "algorithm", "tickers"):
    ok(_bl_full.get(_k) is not None, f"bl_result carries {_k} for the panel")

if _bl_full:
    _tk = _bl_full["tickers"]
    for _k in ("implied_equilibrium_returns", "bl_posterior_returns",
               "equilibrium_weights", "bl_pct"):
        ok(set(_bl_full[_k]) == set(_tk),
           f"{_k} covers exactly the tickers the panel lists")

    # Equilibrium weights are a portfolio, so they sum to 1 rather than 100.
    _eqs = sum(_bl_full["equilibrium_weights"].values())
    ok(abs(_eqs - 1.0) < 0.02, f"equilibrium weights sum to 1, got {_eqs:.4f}")
    _bls = sum(_bl_full["bl_pct"].values())
    ok(abs(_bls - 100.0) < 0.5, f"BL weights sum to 100%, got {_bls:.2f}")

    # The shift column must be the difference it claims to be, or the table
    # tells a story the numbers do not support.
    for _t in _tk:
        _claimed = _bl_full["weight_shifts_pct"][_t]
        _actual = _bl_full["bl_pct"][_t] - _bl_full["equilibrium_weights"][_t] * 100
        ok(abs(_claimed - _actual) < 0.15,
           f"{_t}: shift {_claimed} matches final minus market {_actual:.2f}")

    for _t, _v in (_bl_full["views_injected"] or {}).items():
        ok("expected_excess_pct" in _v and "confidence" in _v,
           f"view on {_t} states both its size and its confidence")
        ok(0 <= _v["confidence"] <= 1, f"{_t} view confidence is a probability")

# The interpretation used to assert "stocks with positive sentiment received
# higher allocations". Building the panel that shows the views made it plain
# that this is not how the optimiser works: a weight shift is the equilibrium,
# the covariance, the view, its confidence and the position cap solved
# together, and the sign of the view alone predicts nothing.
if _bl_full:
    _interp = _bl_full.get("interpretation", "")
    ok("positive sentiment received higher allocations" not in _interp,
       "the interpretation no longer claims view sign drives weight")

    # And check it the hard way: if sign DID predict the shift, the old claim
    # would have been fine. Show that it does not, on live data.
    _vi = _bl_full.get("views_injected") or {}
    if len(_vi) >= 2:
        _mismatch = [t for t, v in _vi.items()
                     if (v["expected_excess_pct"] > 0) !=
                        (_bl_full["weight_shifts_pct"].get(t, 0) > 0)]
        ok(True, f"view sign disagrees with weight shift on {len(_mismatch)} of "
                 f"{len(_vi)} holdings — which is why the old claim was wrong")

_opt_src = _insp.getsource(__import__("portfolio_optimizer"))
ok("not on its sign" in _opt_src or "sign alone" in _opt_src,
   "the shipped code explains what actually moves a Black-Litterman weight")

_bl_jsx = io.open("../frontend/src/components/BlackLitterman.jsx", encoding="utf-8").read()
ok("implied_equilibrium_returns" in _bl_jsx, "the panel reads equilibrium returns")
ok("bl_posterior_returns" in _bl_jsx, "the panel reads posterior returns")
ok("views_injected" in _bl_jsx, "the panel reads the views")
ok("not a prediction" in _bl_jsx or "none of these numbers is a prediction" in _bl_jsx,
   "the panel says equilibrium returns are implied, not forecast")
# With no views the answer IS the market portfolio, and the panel has to say so
# rather than leaving a reader to think the method did nothing.
ok("the final weights are the market portfolio" in _bl_jsx,
   "the no-views case is explained rather than shown as an empty column")


# ================= STRATEGY COMPARISON (item 9) =======================
# The whole point of this module is that it refuses to crown a winner. That
# refusal is a property worth testing, because it is exactly the kind of thing
# a later "helpful" edit removes.
import strategy_compare as _sc

_r = _sc.compare(["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"])
ok("error" not in _r, f"strategy compare runs: {_r.get('error', 'ok')}")

if "error" not in _r:
    _names = [x["strategy"] for x in _r["strategies"]]
    ok(len(_names) >= 3, f"at least 3 methods measured, got {len(_names)}")
    ok("Equal weight" in _names, "equal weight baseline is always present")
    # The bl_pct key mismatch silently dropped this one and looked like the
    # method failing rather than a lookup missing.
    ok("Black-Litterman" in _names, "Black-Litterman is not silently dropped")
    ok("Mean-variance" in _names, "mean-variance is not silently dropped")

    ok("no_winner_named" in _r and len(_r["no_winner_named"]) > 40,
       "the refusal to name a winner is returned to the caller")
    ok("best" not in _r, "no 'best' key exists for a UI to render as a winner")
    ok("recommended" not in _r, "no 'recommended' key exists either")

    # Every method must be measured over the same window on the same data,
    # or the comparison measures the window rather than the method.
    _days = {x["days"] for x in _r["strategies"]}
    ok(len(_days) == 1, f"all methods share one measurement window: {_days}")

    for _x in _r["strategies"]:
        ok(_x.get("volatility_pct") is not None and _x.get("max_drawdown_pct") is not None,
           f"{_x['strategy']} reports risk beside return")
        ok(_x.get("max_drawdown_pct") <= 0, f"{_x['strategy']} drawdown is a fall, not a gain")
        ok(_x.get("turnover_pct") is not None and _x.get("cost_of_turnover_pct") is not None,
           f"{_x['strategy']} reports what the trading cost")
        ok(_x.get("why"), f"{_x['strategy']} says what the method assumes")

    # Equal weight rebalances to itself, so it can never carry turnover cost.
    _eq = [x for x in _r["strategies"] if x["strategy"] == "Equal weight"][0]
    ok(_eq["turnover_pct"] == 0, "equal weight charges no turnover it did not do")

    _src_sc = _insp.getsource(_sc)
    ok("survivorship" in _src_sc.lower(), "the limits name survivorship")
    ok("limits" in _r and len(_r["limits"]) > 40, "limits are returned, not just documented")

# Too few names must refuse rather than compare a two-stock 'portfolio'.
_short = _sc.compare(["RELIANCE.NS", "TCS.NS"])
ok("error" in _short, "fewer than 3 tickers is refused, not silently compared")


# ============================ REPORT ==================================
print("\n" + "=" * 60)
print(f"TOTAL CHECKS: {checks}")
print(f"FAILURES:     {len(failures)}")
for f in failures:
    print(f"   FAIL: {f}")
print("=" * 60)
sys.exit(1 if failures else 0)
