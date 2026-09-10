"""
step5_portfolio_lab_audit.py — Step 5, Portfolio Lab, against production.

Read-only. Every endpoint called here computes and returns; none of them writes.
Requests are sequential with a pause between them, because the API shares a
throttled data connection with live users.

    python docs/step5_portfolio_lab_audit.py

Writes step5_results.json beside this file. Exits 1 when any check fails —
which, at the time of writing, is expected: the failures are real findings.

This is the SECOND version of this harness
------------------------------------------
The first (2026-09-09) got five things wrong. They stay on record because each
is a way an audit can report a result it never measured:

  - It FAILED suggest-fix for returning no suggestions. The suggestions are under
    `steps`; it searched for `suggestions`, `fixes` and `actions`.
  - It FAILED suggest-fix for hiding the return side. The response reports
    `median_pct`; it searched for the literal word "return".
  - Its downside-coherence check on /portfolio/scenarios NEVER RAN. It looked for
    keys `p5` and `median`; they are `p5_value` and `median_value`. It logged a
    note and asserted nothing.
  - Three garbage-input checks PASSED FOR THE WRONG REASON. Each sent ONE holding
    and was rejected for the count, never for the garbage.
  - Its concentration check on /portfolio/what-if searched the response for "95",
    which appears in the echoed weights whether or not anything warns.

Two false failures, four vacuous passes, one silent absence. Every check below
asserts on the response shapes the endpoints actually return.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://quant-india.onrender.com"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "step5_results.json")
INIT = 100000

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL, NOTES = [], [], []
_BAD_JSON = re.compile(r'(?<!")\b(NaN|-?Infinity)\b(?!")')


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


def note(key, value):
    NOTES.append([key, value])
    print(f"  note  {key}: {json.dumps(value, ensure_ascii=False)[:200]}", flush=True)


def banner(title):
    print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74, flush=True)


def pct(value, initial=INIT):
    return round((float(value) / initial - 1) * 100, 2)


def post(path, payload, timeout=280):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    status, raw = 0, ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
    except Exception as e:
        raw = f"{type(e).__name__}: {e}"
    time.sleep(0.3)
    parsed = None
    if status and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
    return status, parsed, raw


def call(label, path, payload):
    st, j, raw = post(path, payload)
    print(f"\n--- {label}  {path}  HTTP {st}", flush=True)
    bad = _BAD_JSON.search(raw)
    check(f"{label}: JSON a browser can parse (no bare NaN/Infinity)",
          st != 0 and not bad, bad.group(0) if bad else ("" if st else raw[:80]))
    return st, j, raw


REAL3 = {"RELIANCE.NS": 40000, "TCS.NS": 30000, "HDFCBANK.NS": 30000}
CONC = {"RELIANCE.NS": 95000, "TCS.NS": 5000}

# --------------------------------------------------------------------------
banner("1. THE GUIDED FLOW — FIVE ANSWERS INTO A PORTFOLIO")

downside_by_limit = {}
for lim in (5, 20, 60):
    st, j, _ = call(f"build max_loss={lim}%", "/portfolio/build",
                    {"amount": INIT, "horizon_months": 12, "max_loss_pct": lim,
                     "n_stocks": 5, "risk": "balanced"})
    if st != 200 or not isinstance(j, dict):
        check(f"build max_loss={lim}%: returns a portfolio", False, f"HTTP {st}")
        continue
    if lim == 20:
        h = j.get("holdings") or {}
        if isinstance(h, list):
            h = {p.get("ticker"): p.get("value") or p.get("amount") for p in h}
        vals = [float(v) for v in h.values() if isinstance(v, (int, float))]
        tot = sum(vals)
        check("build: returns positions", bool(vals), f"{len(vals)} names")
        check("build: every position is positive", bool(vals) and all(v > 0 for v in vals))
        check("build: positions sum to the amount asked for",
              bool(vals) and abs(tot - INIT) / INIT < 0.05, f"sum={tot:,.0f}")
        check("build: no single position above 60%",
              bool(vals) and tot > 0 and max(vals) / tot <= 0.60,
              f"largest={max(vals) / tot:.0%}" if vals and tot else "")
    dp, meets = j.get("downside_pct"), j.get("meets_loss_limit")
    ok = isinstance(dp, (int, float)) and isinstance(meets, bool) and meets == (abs(dp) <= lim)
    check(f"build max_loss={lim}%: meets_loss_limit agrees with its own downside",
          ok, f"downside={dp}%, meets_loss_limit={meets}")
    downside_by_limit[str(lim)] = dp
note("build_downside_by_stated_loss_limit", downside_by_limit)

# --------------------------------------------------------------------------
banner("2. DOWNSIDE — THE NUMBERS MUST AGREE WITH EACH OTHER")

st, sc, _ = call("scenarios", "/portfolio/scenarios",
                 {"holdings": REAL3, "initial_value": INIT, "horizon_months": 12,
                  "max_loss_pct": 20})
scen, base = [], {}
if st == 200 and isinstance(sc, dict):
    base = sc.get("base") or {}
    scen = sc.get("scenarios") or []
    blocks = [("base", base)] + [(s.get("name", "?"), s.get("after") or {}) for s in scen]
    incoherent = []
    for name, b in blocks:
        try:
            med, p5 = float(b["median_value"]), float(b["p5_value"])
            if not (p5 <= med and abs(b["return_pct"] - pct(med)) <= 0.02
                    and abs(b["downside_pct"] - pct(p5)) <= 0.02):
                incoherent.append(name)
        except Exception:
            incoherent.append(f"{name} (fields missing)")
    check(f"scenarios: all {len(blocks)} outcome blocks are internally coherent",
          len(blocks) > 1 and not incoherent,
          "worst-5% <= median; both percentages match their rupee values"
          if not incoherent else str(incoherent))
    bad_delta = []
    for s in scen:
        a = s.get("after") or {}
        try:
            if (abs(s["delta_return_pct"] - (a["return_pct"] - base["return_pct"])) > 0.02
                    or abs(s["delta_downside_pct"]
                           - (a["downside_pct"] - base["downside_pct"])) > 0.02):
                bad_delta.append(s.get("name"))
        except Exception:
            bad_delta.append(f"{s.get('name')} (fields missing)")
    check(f"scenarios: every delta equals after minus base ({len(scen)} scenarios)",
          bool(scen) and not bad_delta, str(bad_delta) if bad_delta else "")
    note("scenarios_how_to_read", sc.get("how_to_read"))
    note("scenarios_disclaimer", sc.get("disclaimer"))

st, sh, _ = call("shock -20% market", "/portfolio/shock",
                 {"holdings": REAL3, "kind": "market", "magnitude_pct": -20.0,
                  "initial_value": INIT})
if st == 200 and isinstance(sh, dict):
    cp = sh.get("change_pct")
    check("shock: a -20% market shock is not reported as a gain",
          isinstance(cp, (int, float)) and cp <= 0, f"change_pct={cp}")

# --------------------------------------------------------------------------
banner("3. SUGGESTIONS — HONEST ABOUT WHAT THEY ARE")

st, sf, _ = call("suggest-fix 95/5", "/portfolio/suggest-fix",
                 {"holdings": CONC, "initial_value": INIT, "horizon_months": 12,
                  "max_loss_pct": 20})
sf_text = ""
if st == 200 and isinstance(sf, dict):
    steps = sf.get("steps") or []
    sf_text = json.dumps(steps, ensure_ascii=False).lower()
    check("suggest-fix: returns concrete steps for a 95/5 portfolio",
          bool(steps), f"{len(steps)} steps")
    health = (sf.get("before") or {}).get("health") or {}
    check("suggest-fix: calls a 95/5 portfolio concentrated",
          "concentrat" in json.dumps(health, ensure_ascii=False).lower(),
          str(health.get("band_note"))[:70])
    risk = (sf.get("before") or {}).get("risk") or {}
    check("suggest-fix: reports both the typical outcome and the downside",
          all(k in risk for k in ("median_pct", "downside_pct")), str(sorted(risk)))
    check("suggest-fix: says re-weighting cannot fix a two-stock portfolio",
          any(s.get("action") == "cap_infeasible" for s in steps))

held = set(REAL3)
named = []
for s in scen:
    added = sorted(set(s.get("weights") or {}) - held)
    if not added:
        continue
    named.append([s.get("name"), [t.replace(".NS", "") for t in added]])
    dr, dd = s.get("delta_return_pct") or 0, s.get("delta_downside_pct") or 0
    if dr > 0 and dd > 0:
        text = f"{s.get('name', '')} {s.get('why', '')}".lower()
        says_alpha = any(w in text for w in ("alpha", "score", "model rates", "high-scoring"))
        says_caveat = any(w in text for w in ("track record", "not proven", "no proven",
                                              "not demonstrated", "no significant",
                                              "forecast", "prediction"))
        check(f"scenarios: '{s.get('name')}' discloses why adding "
              f"{', '.join(t.replace('.NS', '') for t in added)} improves BOTH axes",
              says_alpha and says_caveat,
              f"return {dr:+}, downside {dd:+}; names the alpha selection={says_alpha}, "
              f"carries a track-record caveat={says_caveat}")
note("scenarios_that_add_stocks_not_held", named)
if named and sf_text:
    check("suggest-fix and scenarios agree on whether naming a stock is a forecast",
          "forecast" not in sf_text,
          "suggest-fix: 'that would be a forecast' — scenarios names stocks anyway")

# --------------------------------------------------------------------------
banner("4. FIT — ARITHMETIC, NOT A GUESS DRESSED AS ONE")

st, fg, _ = call("fit INFY", "/portfolio/fit",
                 {"ticker": "INFY.NS", "holdings": REAL3, "add_pct": 10.0})
if st == 200 and isinstance(fg, dict):
    comps = fg.get("components") or {}
    check("fit: a priceable stock is judged on correlation, not only weights",
          "correlation" in comps, str(sorted(comps)))

st, fu, _ = call("fit SMALL250", "/portfolio/fit",
                 {"ticker": "SMALL250.NS", "holdings": REAL3, "add_pct": 10.0})
if isinstance(fu, dict):
    comps = fu.get("components") or {}
    claims_overlap = "overlap" in str(fu.get("verdict", "")).lower()
    check("fit: never claims overlap without having measured correlation",
          st != 200 or "correlation" in comps or not claims_overlap,
          f"HTTP {st}, components={sorted(comps)}, verdict={str(fu.get('verdict'))[:70]!r}")

# --------------------------------------------------------------------------
banner("5. BAD INPUT — REFUSED, OR THE ANSWER SAYS WHAT IT DID")

W = "/portfolio/what-if"


def whatif(holdings):
    return post(W, {"holdings": holdings, "initial_value": INIT, "horizon_months": 12})


st, _, raw = whatif({})
check("what-if refuses an empty portfolio", st == 400, f"HTTP {st} {raw[:60]}")
st, _, raw = whatif({"ZZZQQQ123.NS": 50000, "QQQZZZ456.NS": 50000})
check("what-if refuses two nonexistent tickers", st == 400, f"HTTP {st} {raw[:60]}")
st, _, raw = whatif({"RELIANCE.NS": 50000, "SMALL250.NS": 50000})
check("what-if refuses a security the scan cannot price (SMALL250)",
      st == 400, f"HTTP {st} {raw[:60]}")

DISCLOSE = ("dropped", "excluded", "skipped", "unpriced", "no price", "no data",
            "could not price", "ignored", "not found", "warning", "unknown ticker")


def shown_is_simulated(label, holdings, bad, reference):
    st, j, raw = whatif(holdings)
    _, jr, _ = whatif(reference)
    if st != 200:
        check(f"what-if: {label} — shown portfolio is the simulated one", True,
              f"refused, HTTP {st}")
        return
    j, jr = j or {}, jr or {}
    shown = j.get("weights") or {}
    ret = (j.get("base") or {}).get("return_pct")
    ref = (jr.get("base") or {}).get("return_pct")
    dropped = (bad in shown and isinstance(ret, (int, float))
               and isinstance(ref, (int, float)) and abs(ret - ref) <= 0.05)
    disclosed = any(w in raw.lower() for w in DISCLOSE)
    check(f"what-if: {label} — shown portfolio is the simulated one",
          not dropped or disclosed,
          f"shows {bad.replace('.NS', '')} at {shown.get(bad)}%, yet return {ret}% equals "
          f"the portfolio without it ({ref}%); disclosed={disclosed}")


shown_is_simulated("a nonexistent ticker beside a real one",
                   {"RELIANCE.NS": 50000, "ZZZQQQ123.NS": 50000}, "ZZZQQQ123.NS",
                   {"RELIANCE.NS": 100000, "TCS.NS": 1})
shown_is_simulated("a typo (RELIANC.NS) beside a real one",
                   {"RELIANC.NS": 50000, "TCS.NS": 50000}, "RELIANC.NS",
                   {"TCS.NS": 100000, "RELIANCE.NS": 1})

st, j, raw = whatif({"RELIANCE.NS": -50000, "TCS.NS": 150000})
shown = sorted((j or {}).get("weights") or {})
check("what-if: a negative holding is not displayed while being ignored",
      st != 200 or "RELIANCE.NS" not in shown,
      f"weights shown {shown} — display matches simulation")
check("what-if: a negative holding is refused or explained",
      st != 200 or any(w in raw.lower() for w in ("negative", "long-only", "short",
                                                    "must be positive", "ignored",
                                                    "dropped")),
      f"HTTP {st}; nothing says RELIANCE was discarded")

st, j, _ = whatif(CONC)
outside_weights = {k: v for k, v in (j or {}).items() if k != "weights"}
note("what_if_untweaked_95_5_mentions_concentration_outside_weights",
     "concentrat" in json.dumps(outside_weights, ensure_ascii=False).lower())

# --------------------------------------------------------------------------
banner("6. THE OPTIMISER ADMITS ITS OWN FRAGILITY")

# A draft of this section only checked that the stability keys existed. It
# passed, with the least-stable weight moving sd=0.0% across 20 trials. Zero
# movement is either robustness or weights pinned against their bounds, and the
# keys cannot tell those apart. The two cases below can.
#
# With n weights summing to 100, if n-1 of them sit on a bound (the cap, or 0)
# the last is forced to the remainder, and no perturbation of expected returns
# can move any of them. That is the constraint talking, not the covariance.
STAB = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"]
for mw in (1.0, 0.4):
    st, stb, _ = call(f"optimizer stability max_weight={mw}", "/optimizer/stability",
                      {"tickers": STAB, "target": "max_sharpe", "max_weight": mw,
                       "trials": 20, "period_months": 24})
    if st != 200 or not isinstance(stb, dict):
        continue
    w = stb.get("baseline_pct") or {}
    sd = stb.get("weight_sd_pct") or {}
    verdict = str(stb.get("verdict", ""))
    cap = mw * 100
    at_bound = [t for t, v in w.items() if abs(v - cap) < 0.01 or abs(v) < 0.01]
    frozen = bool(sd) and all(abs(x) < 0.01 for x in sd.values())
    pinned = frozen and len(w) > 0 and len(at_bound) >= len(w) - 1
    if mw == 1.0:
        check("stability: an unconstrained 100% corner is flagged, not praised",
              stb.get("corner_solution") is True
              and not verdict.lower().startswith("stable"), verdict[:70])
    check(f"stability max_weight={mw}: weights pinned at their bounds are not called stable",
          not (pinned and verdict.lower().startswith("stable")),
          f"weights {w}; {len(at_bound)} of {len(w)} on a bound, all sd 0; "
          f"corner_solution={stb.get('corner_solution')}; verdict={verdict[:55]!r}")

# --------------------------------------------------------------------------
print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "base": BASE, "passed": PASS, "failed": FAIL, "notes": NOTES},
              fh, indent=1, ensure_ascii=False)
print(f"written: {OUT}")
sys.exit(1 if FAIL else 0)
