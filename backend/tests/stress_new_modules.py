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


# ============================ REPORT ==================================
print("\n" + "=" * 60)
print(f"TOTAL CHECKS: {checks}")
print(f"FAILURES:     {len(failures)}")
for f in failures:
    print(f"   FAIL: {f}")
print("=" * 60)
sys.exit(1 if failures else 0)
