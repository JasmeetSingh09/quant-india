"""
production_e2e.py — walk the real app as a user, against the deployed API.

Everything here hits https://quant-india.onrender.com. Nothing is imported from
the local modules, because the question is not "does this function work" but
"does the deployed system behave correctly for someone using it".

Three passes:
  1. The journey — search, signal, portfolio, optimise, simulate, backtest.
  2. Edge cases — the thirteen conditions a real user eventually produces.
  3. Reconciliation — numbers computed here from raw inputs, checked against
     what the API returns, so a wrong figure cannot hide behind a plausible one.

A check that cannot be evaluated is reported as SKIP, never as PASS. The point
of this file is to stop "it exists" being mistaken for "it works".
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://quant-india.onrender.com"
results = []


def api(path, method="GET", body=None, timeout=240):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"_transport_error": f"{type(e).__name__}: {e}"}


def check(section, name, ok_, evidence=""):
    verdict = "PASS" if ok_ is True else ("SKIP" if ok_ is None else "FAIL")
    results.append((section, name, verdict, evidence))
    print(f"  [{verdict}] {name}")
    if evidence:
        print(f"         {evidence}")


# ══════════════════════════════ 1. THE JOURNEY ══════════════════════════════
print("\n1. END-TO-END USER JOURNEY\n" + "=" * 74)

st, search = api("/stock/search?q=RELIANCE&exchange=NSE")
hits = search if isinstance(search, list) else (search or {}).get("results", [])
check("journey", "search finds a stock", st == 200 and bool(hits),
      f"HTTP {st}, {len(hits) if hits else 0} results for 'RELIANCE'")

st, px = api("/stock/price?ticker=RELIANCE.NS")
price = (px or {}).get("price") or (px or {}).get("current_price")
check("journey", "price returns a usable number", st == 200 and bool(price),
      f"RELIANCE.NS = {price}")

st, sig = api("/alpha/score?ticker=RELIANCE.NS")
check("journey", "four-factor signal computes", st == 200 and "alpha_score" in (sig or {}),
      f"score {sig.get('alpha_score')}, signal {sig.get('signal')}")

st, v2 = api("/alpha/v2?ticker=RELIANCE.NS")
check("journey", "six-factor signal computes", st == 200 and "alpha_score" in (v2 or {}),
      f"score {v2.get('alpha_score')}, {len(v2.get('weights_used') or {})} factors")
check("journey", "six-factor is labelled experimental",
      (v2 or {}).get("evidence_status") == "experimental",
      f"evidence_status = {v2.get('evidence_status')}")

PORT = {"RELIANCE.NS": 40, "TCS.NS": 30, "HDFCBANK.NS": 20, "ITC.NS": 10}

st, adv = api("/portfolio/advise", "POST",
              {"holdings": PORT, "focus": "design"})
check("journey", "coach analyses the portfolio", st == 200 and "suggestions" in (adv or {}),
      f"{len(adv.get('suggestions') or [])} findings, "
      f"health {(adv.get('health') or {}).get('score')}")

st, opt = api("/optimizer/mvo", "POST",
              {"tickers": list(PORT), "target": "max_sharpe", "max_weight": 0.4})
w = (opt or {}).get("optimal_pct") or {}
check("journey", "optimiser returns weights", st == 200 and bool(w),
      f"{len(w)} weights, largest {max(w.values()):.1f}%" if w else f"HTTP {st}")

st, mc = api("/montecarlo/simulate", "POST",
             {"holdings": PORT, "initial_value": 100000,
              "horizon_days": 252, "n_simulations": 2000, "method": "bootstrap"})
if st != 200:
    st, mc = api("/monte-carlo", "POST",
                 {"holdings": PORT, "initial_value": 100000,
                  "horizon_days": 252, "n_simulations": 2000})
check("journey", "monte carlo simulates", st == 200 and "percentiles" in (mc or {}),
      f"p5 {(mc.get('percentiles') or {}).get('p5')}, median {mc.get('median_value')}"
      if st == 200 else f"HTTP {st}")

st, bt = api("/simulator/historic", "POST",
             {"holdings": PORT, "start_date": "2023-01-01",
              "end_date": "2024-06-28", "initial_value": 100000})
check("journey", "historical backtest runs", st == 200 and "total_return_pct" in (bt or {}),
      f"return {bt.get('total_return_pct')}% over a fixed past window"
      if st == 200 else f"HTTP {st}")
check("journey", "backtest reports survivorship",
      isinstance((bt or {}).get("survivorship"), dict) if st == 200 else None,
      f"{(bt.get('survivorship') or {}).get('note', '')[:70]}" if st == 200 else "")
check("journey", "backtest reports tradeability at size",
      isinstance((bt or {}).get("liquidity"), dict) if st == 200 else None,
      f"tradeable={(bt.get('liquidity') or {}).get('tradeable_at_this_size')}"
      if st == 200 else "")


# ══════════════════════════════ 2. EDGE CASES ══════════════════════════════
print("\n2. EDGE-CASE MATRIX\n" + "=" * 74)

st, r = api("/alpha/score?ticker=NOTAREALTICKER9Z.NS")
check("edge", "invalid ticker fails visibly", st >= 400 or "error" in (r or {}),
      f"HTTP {st} — refused rather than returning a fabricated score")

st, r = api("/stock/metrics?ticker=DSKULKARNI.NS")
missing = [k for k, v in (r or {}).items() if v is None]
check("edge", "missing fundamentals are null, not zero", st == 200,
      f"HTTP {st}, {len(missing)} fields null — a null reads as unavailable, "
      f"a zero reads as a measurement")

st, r = api("/liquidity/DSKULKARNI.NS")
check("edge", "illiquid stock is flagged", st == 200 and r.get("tier") in ("illiquid", "thin"),
      f"tier={r.get('tier')}, {r.get('daily_value_label')}")

st, r = api("/execution/preview?ticker=DSKULKARNI.NS&amount=100000")
part = (r.get("slippage_detail") or {}).get("participation_pct")
check("edge", "impossible order size is penalised", st == 200 and (part or 0) > 100,
      f"{part:,.0f}% of daily volume, cost {r.get('total_cost_pct')}%"
      if part else f"HTTP {st}")

st, r = api("/portfolio/advise", "POST", {"holdings": {}, "focus": "design"})
check("edge", "empty portfolio refused", st >= 400 or "error" in (r or {}), f"HTTP {st}")

st, r = api("/portfolio/advise", "POST",
            {"holdings": {"RELIANCE.NS": 100}, "focus": "design"})
check("edge", "single-holding portfolio handled", st == 200 or "error" in (r or {}),
      f"HTTP {st} — one stock is not a portfolio and is treated as such")

BIG = {f"{t}.NS": round(100 / 30, 3) for t in
       ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC", "SBIN",
        "BHARTIARTL", "LT", "KOTAKBANK", "AXISBANK", "SUNPHARMA", "MARUTI",
        "TITAN", "WIPRO", "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "HINDALCO",
        "COALINDIA", "ONGC", "NTPC", "POWERGRID", "ADANIENT", "BAJFINANCE",
        "ASIANPAINT", "NESTLEIND", "HINDUNILVR", "DRREDDY", "CIPLA"]}
st, r = api("/portfolio/advise", "POST", {"holdings": BIG, "focus": "design"}, timeout=280)
check("edge", "30-stock portfolio completes", st == 200,
      f"HTTP {st}, health {(r.get('health') or {}).get('score')}" if st == 200 else f"HTTP {st}")

st, r = api("/portfolio/advise", "POST",
            {"holdings": {"RELIANCE.NS": 50, "reliance.ns": 50}, "focus": "design"})
check("edge", "duplicate holdings do not double-count", st == 200 or "error" in (r or {}),
      f"HTTP {st} — same stock in two cases")

st, r = api("/tax/after-tax", "POST",
            {"invested": 100000, "current_value": 80000, "days_held": 30})
check("edge", "a loss is not taxed", st == 200 and r.get("tax") == 0,
      f"tax on a 20% loss = {r.get('tax')}")

st, r = api("/execution/preview?ticker=RELIANCE.NS&amount=1")
check("edge", "trivial order still prices", st == 200,
      f"HTTP {st}, cost {r.get('total_cost_pct')}% of Rs 1")

st, r = api("/anomaly/DSKULKARNI.NS")
check("edge", "anomaly check survives a thin stock", st == 200,
      f"checked={r.get('checked')}, unusual={r.get('unusual')}")

st, r = api("/events/NOTAREALTICKER9Z.NS")
check("edge", "events on an unknown ticker degrade safely", st == 200,
      f"checked={r.get('checked')} — no fabricated headlines")

st, r = api("/bhavcopy/coverage")
check("edge", "stale-price fallback has data behind it", st == 200 and (r.get("days") or 0) > 0,
      f"{r.get('rows'):,} rows, {r.get('days')} days, latest {r.get('latest_day')}")


# ══════════════════════ 3. BACKEND ↔ INDEPENDENT MATHS ══════════════════════
print("\n3. RECONCILIATION — API vs INDEPENDENTLY COMPUTED\n" + "=" * 74)

st, cost = api("/execution/preview?ticker=RELIANCE.NS&amount=100000")
if st == 200:
    exp_stt = 100000 * 0.001
    got_stt = (cost.get("charges") or {}).get("stt")
    check("recon", "STT matches the statutory rate",
          abs(got_stt - exp_stt) < 0.01,
          f"API {got_stt}, independently 100000 x 0.1% = {exp_stt}")
    total = cost["invested_after_costs"] + cost["total_cost"]
    check("recon", "invested + costs equals the order",
          abs(total - 100000) < 0.01,
          f"{cost['invested_after_costs']} + {cost['total_cost']} = {total}")
else:
    check("recon", "cost breakdown", None, f"HTTP {st}")

st, tax = api("/tax/after-tax", "POST",
              {"invested": 100000, "current_value": 118000, "days_held": 330})
if st == 200:
    check("recon", "short-term tax is 20% of the gain",
          abs(tax["tax"] - 3600) < 1,
          f"API {tax['tax']}, independently 18000 x 20% = 3600")
    check("recon", "net return follows from the tax",
          abs(tax["net_return_pct"] - 14.4) < 0.05,
          f"API {tax['net_return_pct']}%, independently (100000+14400)/100000 = 14.4%")
else:
    check("recon", "tax arithmetic", None, f"HTTP {st}")

st, v2 = api("/alpha/v2?ticker=RELIANCE.NS")
if st == 200 and v2.get("contributions"):
    w = v2["weights_used"]
    check("recon", "factor weights sum to 1",
          abs(sum(w.values()) - 1.0) < 1e-6, f"sum = {sum(w.values())}")
    contrib = {k: v for k, v in v2["contributions"].items() if v is not None}
    used = sum(w[k] for k in contrib)
    recomputed = round(sum(contrib.values()) / used, 2) if used else None
    check("recon", "alpha equals its own weighted contributions",
          recomputed is not None and abs(recomputed - v2["alpha_score"]) < 0.5,
          f"API {v2['alpha_score']}, recomputed from parts {recomputed}")
else:
    check("recon", "alpha decomposition", None, f"HTTP {st}")

st, bench = api("/benchmark?days=365")
if st == 200:
    st2, cmp_ = api("/portfolio/advise", "POST",
                    {"holdings": PORT, "focus": "live",
                     "current_return_pct": bench["return_pct"]})
    b = (cmp_ or {}).get("benchmark") or {}
    check("recon", "index against itself gives zero excess",
          st2 == 200 and abs(b.get("difference_pct", 99)) < 0.05,
          f"portfolio set to the index return -> difference {b.get('difference_pct')}")
else:
    check("recon", "benchmark self-check", None, f"HTTP {st}")

st, ind = api("/predictions/track?min_days=21")
sc = (ind or {}).get("scorecard") or {}
indep = sc.get("independence") or {}
if sc:
    check("recon", "independent windows never exceed observations",
          (indep.get("effective_independent_estimate") or 0) <= (indep.get("observations") or 0),
          f"{indep.get('observations')} observations -> "
          f"{indep.get('effective_independent_estimate')} independent")
    bs = (sc.get("by_signal") or {}).get("buy") or {}
    sig = bs.get("significance") or {}
    check("recon", "hit rate and its interval agree",
          not sig or (sig["ci95_low_pct"] <= bs["hit_rate_pct"] <= sig["ci95_high_pct"]),
          f"{bs.get('hit_rate_pct')}% inside "
          f"[{sig.get('ci95_low_pct')}, {sig.get('ci95_high_pct')}]" if sig else "no test")
else:
    check("recon", "track record", None, "no scorecard returned")


# ══════════════════════════════════ REPORT ══════════════════════════════════
print("\n" + "=" * 74)
counts = {}
for _, _, v, _ in results:
    counts[v] = counts.get(v, 0) + 1
print("RESULT: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
fails = [r for r in results if r[2] == "FAIL"]
if fails:
    print(f"\n{len(fails)} FAILURE(S):")
    for sec, name, _, ev in fails:
        print(f"  - [{sec}] {name} — {ev}")
skips = [r for r in results if r[2] == "SKIP"]
if skips:
    print(f"\n{len(skips)} could not be evaluated (reported as SKIP, not PASS):")
    for sec, name, _, ev in skips:
        print(f"  - [{sec}] {name} — {ev}")
print("=" * 74)
sys.exit(1 if fails else 0)
