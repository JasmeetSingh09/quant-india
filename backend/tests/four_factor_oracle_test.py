"""
four_factor_oracle_test.py — the four-factor model (V1) against an independent oracle.

Audit of 2026-10-14. Every expected value below is computed HERE, from the
written methodology (docs/PHASE0_V1_METHODOLOGY_2026-09-14.md), in plain Python
(math, statistics). No production calculation function is called to produce an
expected answer; production functions are called only to produce the ACTUAL
answer being checked.

All inputs are SYNTHETIC test fixtures. Providers (Yahoo prices, Yahoo company
information, news, FinBERT) are replaced by stubs, so this proves the software
computes what the methodology says on given inputs. It does not prove the
providers work live, and nothing here touches a production database: storage
checks run on a temporary SQLite file.

Run:  cd backend && python tests/four_factor_oracle_test.py [--report path.json]

Each check is tagged with a section and, where it documents a known defect,
the defect id from docs/AUDIT_FOUR_FACTOR_2026-10-14.md.
"""
import json
import math
import os
import random
import sqlite3
import statistics
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
sys.path.insert(0, os.path.join(HERE, ".."))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="v1_oracle_")
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)

# Heavy providers are replaced before anything imports them.
class _Stub(types.ModuleType):
    """A provider module whose every other attribute is an inert function."""
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


_news = _Stub("news")
_news.get_stock_news = lambda ticker, days_back=14: []
sys.modules["news"] = _news
_sent = _Stub("sentiment")
_sent.score_headline = lambda title: {"label": "neutral", "confidence": 0.0}
sys.modules["sentiment"] = _sent

import numpy as np          # noqa: E402  (only to build provider-shaped frames)
import pandas as pd         # noqa: E402

import alpha_model as A     # noqa: E402
import data_fetcher as DF   # noqa: E402
import metrics as MET       # noqa: E402

RESULTS = []
SECTION = {"name": ""}


def section(name):
    SECTION["name"] = name
    print(f"\n{'=' * 74}\n{name}\n{'=' * 74}")


def check(cid, name, cond, detail="", defect=None):
    status = "PASS" if cond else "FAIL"
    RESULTS.append({"id": cid, "section": SECTION["name"], "name": name,
                    "status": status, "detail": str(detail)[:400], "defect": defect})
    tag = f" [{defect}]" if defect and not cond else ""
    print(f"  [{'ok  ' if cond else 'FAIL'}] {cid} {name}{tag}" + (f"  {detail}" if detail else ""))


def close(a, b, tol=1e-9):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


# ===========================================================================
# Independent oracles (methodology document, not the code)
# ===========================================================================

def oracle_momentum(closes):
    c = [x for x in closes if x is not None and not (isinstance(x, float) and math.isnan(x))]
    n = len(c)
    if n == 0:
        return {"score": 0.0, "confidence": 0.0, "reason": "price data unavailable"}
    if n < 60:
        return {"score": 0.0, "confidence": 0.0, "reason": "price history too short"}
    start = max(0, n - 1 - 252)
    end = n - 1 - 21
    if end <= start:
        return {"score": 0.0, "confidence": 0.0, "reason": "insufficient price history"}
    mom = c[end] / c[start] - 1
    rets = [c[i] / c[i - 1] - 1 for i in range(start + 1, end + 1)]
    vol = statistics.stdev(rets) * math.sqrt(252) if len(rets) > 5 else 0.0
    ra = mom / vol if vol > 1e-6 else 0.0
    return {"score": round(math.tanh(ra / 1.5), 4),
            "confidence": round(0.4 + 0.6 * min(1.0, (end - start) / 252), 3),
            "mom": mom, "vol": vol, "start": start, "end": end}


def oracle_sentiment(articles_with_age, days_back=14):
    """articles_with_age: list of (age_days or None, label, conf)."""
    if not articles_with_age:
        return {"score": 0.0, "confidence": 0.0}
    lam = math.log(2) / 3
    num = den = 0.0
    for age, label, conf in articles_with_age:
        a = days_back * 0.5 if age is None else max(0.0, age)
        w = math.exp(-lam * a)
        v = conf if label == "positive" else -conf if label == "negative" else 0.0
        num += v * w
        den += w
    c = min(1.0, den / (days_back * 0.5))
    return {"score": round(num / den * c, 4), "confidence": round(c, 4)}


def oracle_quality(f_score=None, roe=None, fcf=None, mktcap=None, fx=None,
                   book_value=None, coverage=None, net_income=None, ocf=None):
    parts = []
    if f_score is not None:
        parts.append((0.4, f_score / 9))
    if roe is not None:
        parts.append((0.4, ((roe - 0.12) / 0.08) / 3))
    if fcf is not None and fx is not None:
        fcf = fcf * fx if fx else None
    y = (fcf / mktcap) if (fcf is not None and mktcap) else None
    if y is not None:
        parts.append((0.2, ((y - 0.035) / 0.04) / 3))
    if not parts:
        return {"score": 0.0, "confidence": 0.0}
    wsum = sum(w for w, _ in parts)
    raw = sum(w * v for w, v in parts) / wsum
    pen, flags = 0.0, 0
    if book_value is not None and book_value < 0:
        pen += 0.5; flags += 1
    if coverage is not None and coverage < 1.5:
        pen += 0.25; flags += 1
    if net_income is not None and net_income < 0:
        pen += 0.25; flags += 1
    if ocf is not None and ocf < 0:
        pen += 0.25; flags += 1
    if flags:
        raw = min(raw, 0.0) - pen
    return {"score": round(math.tanh(raw), 4), "confidence": round(0.85 * wsum, 3)}


def oracle_value(pe, pb, peers):
    """peers: list of (pe, pb); only the first three are consulted."""
    flags = []
    if pe is not None and pe <= 0:
        flags.append("pe"); pe = None
    if pb is not None and pb <= 0:
        flags.append("pb"); pb = None
    if not pe and not pb:
        if flags:
            return {"score": -0.5, "confidence": 0.6}
        return {"score": 0.0, "confidence": 0.0}
    peer_pes = [p for p, _ in peers[:3] if p]
    peer_pbs = [b for _, b in peers[:3] if b]
    if len(peer_pes) < 2:
        pe_m, pe_s = 22.0, 8.0
    else:
        pe_m, pe_s = statistics.fmean(peer_pes), max(statistics.pstdev(peer_pes), 1)
    if len(peer_pbs) < 2:
        pb_m, pb_s = 3.2, 1.5
    else:
        pb_m, pb_s = statistics.fmean(peer_pbs), max(statistics.pstdev(peer_pbs), 0.5)
    pe_z = ((pe or pe_m) - pe_m) / pe_s
    pb_z = ((pb or pb_m) - pb_m) / pb_s
    score = math.tanh((-0.6 * pe_z - 0.4 * pb_z) / 2)
    legs = (1 if pe else 0) + (1 if pb else 0)
    conf = min(1.0, 0.5 + 0.1 * len(peer_pes))
    if legs < 2:
        conf = round(conf * 0.5, 3)
    return {"score": round(score, 4), "confidence": conf}


W = {"sentiment": 0.25, "momentum": 0.35, "quality": 0.25, "value": 0.15}


def oracle_label(a):
    if a > 40:
        return "STRONG BUY"
    if a > 15:
        return "BUY"
    if a < -40:
        return "STRONG SELL"
    if a < -15:
        return "SELL"
    return "NEUTRAL"


def oracle_composite(f):
    a = round(100 * sum(W[k] * f[k][0] for k in W), 2)
    c = round(sum(W[k] * f[k][1] for k in W), 3)
    return a, c, oracle_label(a)


# ===========================================================================
# Provider stubs
# ===========================================================================

def frame(closes, start="2025-01-01", dates=None):
    idx = pd.DatetimeIndex(dates) if dates is not None else pd.bdate_range(start, periods=len(closes))
    cols = pd.MultiIndex.from_tuples([("Close", "X.NS")], names=["Price", "Ticker"])
    return pd.DataFrame({("Close", "X.NS"): closes}, index=idx, columns=cols)


def set_prices(df_or_exc):
    def _dl(*a, **k):
        if isinstance(df_or_exc, Exception):
            raise df_or_exc
        return df_or_exc
    A.yf.download = _dl


def walk(n, seed, drift=0.0004, vol=0.018, p0=100.0):
    r = random.Random(seed)
    out = [p0]
    for _ in range(n - 1):
        out.append(out[-1] * (1 + drift + r.gauss(0, vol)))
    return out


# ===========================================================================
section("1. MOMENTUM — 12-1 return / annualised volatility, tanh(x/1.5)")
# ===========================================================================

def run_mom(closes, **kw):
    set_prices(frame(closes, **kw))
    return A._compute_momentum_factor("X.NS")


cases = [
    ("M01", "normal 300 closes", walk(300, 1)),
    ("M02", "exactly 60 closes (minimum valid)", walk(60, 2)),
    ("M03", "253 closes: window starts at index 0", walk(253, 3)),
    ("M04", "274 closes: window starts at index 21", walk(274, 4)),
    ("M05", "steady decline (negative sign)", walk(300, 5, drift=-0.003)),
    ("M06", "extreme rally x50 (bounded below 1)", walk(300, 6, drift=0.015, vol=0.01)),
    ("M07", "very high volatility", walk(300, 7, vol=0.08)),
]
for cid, name, cl in cases:
    exp, act = oracle_momentum(cl), run_mom(cl)
    ok = close(act["score"], exp["score"], 1e-4) and close(act["confidence"], exp["confidence"], 1e-9)
    check(cid, name + " — score and confidence match oracle", ok,
          f"actual {act['score']}/{act['confidence']} expected {exp['score']}/{exp['confidence']}")
    if "mom" in exp:
        check(cid + "b", name + " — raw 12-1 return and volatility match",
              close(act["mom_12_1_pct"], round(exp["mom"] * 100, 2), 0.011)
              and close(act["ann_vol_pct"], round(exp["vol"] * 100, 2), 0.011),
              f"mom {act['mom_12_1_pct']} vs {exp['mom']*100:.2f}, vol {act['ann_vol_pct']} vs {exp['vol']*100:.2f}")
    check(cid + "c", name + " — score within [-1, 1]", -1 <= act["score"] <= 1)

cl = walk(300, 8)
act = run_mom(cl)
idx = pd.bdate_range("2025-01-01", periods=300)
check("M08", "window dates are 252 and 21 trading days back",
      act["window_from"] == str(idx[300 - 1 - 252])[:10] and act["window_to"] == str(idx[300 - 1 - 21])[:10],
      f"{act['window_from']} -> {act['window_to']}")
check("M09", "skipped month return is reported, not scored",
      close(act["skipped_month_return_pct"], round((cl[-1] / cl[300 - 1 - 21] - 1) * 100, 2), 0.011))

r = run_mom(walk(59, 9))
check("M10", "59 closes: refused as short history (score 0, confidence 0)",
      r["score"] == 0.0 and r["confidence"] == 0.0 and r.get("reason") == "price history too short", r.get("reason"))
set_prices(frame([]))
r = A._compute_momentum_factor("X.NS")
check("M11", "no closes: refused as unavailable", r["confidence"] == 0.0 and r.get("reason") == "price data unavailable",
      r.get("reason"))
set_prices(TimeoutError("provider timeout"))
r = A._compute_momentum_factor("X.NS")
check("M12", "provider timeout: refused, never raises", r["confidence"] == 0.0 and r["score"] == 0.0, r.get("reason"))
set_prices(ValueError("HTTP 429"))
r = A._compute_momentum_factor("X.NS")
check("M13", "HTTP 429 from provider: refused, never raises", r["confidence"] == 0.0, r.get("reason"))

cl = walk(300, 10)
gapped = list(cl)
for i in (5, 50, 120, 299 - 30):
    gapped[i] = float("nan")
exp, act = oracle_momentum(gapped), run_mom(gapped)
check("M14", "missing observations (NaN) are dropped, not zero-filled",
      close(act["score"], exp["score"], 1e-4), f"{act['score']} vs {exp['score']}")

flat = [100.0] * 300
act = run_mom(flat)
check("M15", "flat prices: zero volatility gives score 0 at positive confidence (measured, not refused)",
      act["score"] == 0.0 and act["confidence"] == oracle_momentum(flat)["confidence"] and "reason" not in act,
      f"confidence {act['confidence']} (a full window is 231 of 252 days, so the ceiling is 0.95)")

r1, r2 = run_mom(walk(300, 11)), run_mom(walk(300, 11))
check("M16", "identical inputs give identical outputs", r1 == r2)

# Out-of-order and duplicate rows. The provider returns a sorted, de-duplicated
# index; the function does not re-sort, so this records behaviour on bad input.
cl = walk(300, 12)
dates = list(pd.bdate_range("2025-01-01", periods=300))
pairs = list(zip(dates, cl))
random.Random(1).shuffle(pairs)
sh = frame([p for _, p in pairs], dates=[d for d, _ in pairs])
set_prices(sh)
act = A._compute_momentum_factor("X.NS")
exp = oracle_momentum(cl)
check("M17", "out-of-order rows give the sorted answer (no defensive sort)",
      close(act["score"], exp["score"], 1e-4), f"{act['score']} vs sorted {exp['score']}", defect="D-08")
dup = frame(cl + cl[-5:], dates=dates + dates[-5:])
set_prices(dup)
act = A._compute_momentum_factor("X.NS")
check("M18", "duplicated dates are not double counted",
      close(act["score"], exp["score"], 1e-4), f"{act['score']} vs {exp['score']}", defect="D-08")

# The point-in-time research copy must use the same arithmetic as the live score.
import pit_validation as PV  # noqa: E402
cl = walk(300, 13)
C = np.array([cl], dtype=np.float64)
pit = float(PV._momentum_scores(C, 299)[0])
live = oracle_momentum(cl)["score"]
check("M19", "PIT backtest momentum equals live momentum (docstring: 'identical arithmetic')",
      abs(pit - live) < 1e-4, f"pit {pit:.6f} vs live {live:.6f} (pit uses population std, live sample std)",
      defect="D-07")
check("M20", "PIT and live momentum share window constants",
      PV.MOM_LOOKBACK == A.MOMENTUM_LOOKBACK_DAYS and PV.MOM_SKIP == A.MOMENTUM_SKIP_DAYS
      and PV.MOM_TANH_DIV == A.MOMENTUM_TANH_DIVISOR)


# ===========================================================================
section("2. SENTIMENT — decay-weighted FinBERT, shrunk by confidence")
# ===========================================================================

def run_sent(arts, labels):
    _news.get_stock_news = lambda ticker, days_back=14: arts
    _sent.score_headline = lambda t: {"label": labels[t][0], "confidence": labels[t][1]}
    return A._compute_sentiment_factor("X.NS")


def iso(age_days):
    return (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")


labels = {"a": ("positive", 0.9), "b": ("negative", 0.7), "c": ("neutral", 0.95),
          "d": ("positive", 0.6), "e": ("negative", 0.99)}
arts = [{"title": "a", "published_at": iso(0.5)}, {"title": "b", "published_at": iso(2)},
        {"title": "c", "published_at": iso(4)}, {"title": "d", "published_at": iso(9)},
        {"title": "e", "published_at": iso(13)}]
exp = oracle_sentiment([(0.5, *labels["a"]), (2, *labels["b"]), (4, *labels["c"]), (9, *labels["d"]), (13, *labels["e"])])
act = run_sent(arts, labels)
check("S01", "mixed headlines match oracle", close(act["score"], exp["score"], 2e-4)
      and close(act["confidence"], exp["confidence"], 2e-4), f"{act['score']}/{act['confidence']} vs {exp}")
check("S02", "every headline used is recorded", act.get("n_articles") == 5 and len(act.get("articles_used", [])) == 5)

act = run_sent([], labels)
check("S03", "no news: refused (0, 0) with a reason", act["score"] == 0 and act["confidence"] == 0 and act.get("reason"))

act = run_sent([{"title": "a", "published_at": None}], labels)
exp = oracle_sentiment([(None, *labels["a"])])
check("S04", "undated headline counts as 7 days old", close(act["score"], exp["score"], 1e-4)
      and act.get("undated_articles") == 1, f"{act['score']} vs {exp['score']}")

act = run_sent([{"title": "a", "published_at": "garbage-date-xyz"}], labels)
check("S05", "unparseable date treated as undated, headline kept", close(act["score"], exp["score"], 1e-4)
      and act.get("undated_articles") == 1, act.get("score"))

act = run_sent([{"title": "a", "published_at": iso(-2)}], labels)
exp = oracle_sentiment([(0, *labels["a"])])
check("S06", "future-dated headline is clamped to age 0", close(act["score"], exp["score"], 1e-4), act["score"])

t = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).replace(microsecond=0)
ist = (t + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S+05:30")
act = run_sent([{"title": "a", "published_at": ist}], labels)
exp = oracle_sentiment([(1, *labels["a"])])
check("S07", "timezone-aware date converted to UTC", close(act["score"], exp["score"], 2e-4), f"{act['score']} vs {exp['score']}")

act = run_sent([{"title": "a", "publishedAt": iso(1)}], labels)
check("S08", "alternative field name publishedAt is read", close(act["score"], exp["score"], 2e-4), act["score"])

act = run_sent([{"title": "c", "published_at": iso(0)}] * 4, labels)
check("S09", "all neutral: score 0 at positive confidence", act["score"] == 0.0 and act["confidence"] > 0)

many = [{"title": "a", "published_at": iso(0)}] * 20
act = run_sent(many, labels)
check("S10", "confidence capped at 1 and score bounded", act["confidence"] == 1.0 and -1 <= act["score"] <= 1,
      f"{act['score']}/{act['confidence']}")

act = run_sent([{"title": "a", "published_at": iso(1)}, {"published_at": iso(1)}], labels)
check("S11", "one malformed article (no title) does not discard the others",
      act["confidence"] > 0, act.get("reason"), defect="D-09")


# ===========================================================================
section("3. QUALITY — Piotroski/9, ROE z/3, FCF-yield z/3, distress penalties")
# ===========================================================================

def run_q(f_score=None, info=None, der=None, cov=None, fx=None):
    MET.piotroski_score = (lambda t: {"f_score": f_score}) if f_score is not None else (lambda t: {"error": "x"})
    A._ticker_info = lambda t: dict(info or {})
    DF._derived_fundamentals = lambda t, i=None: dict(der or {})
    A._interest_coverage = lambda t: cov
    DF.fx_rate = lambda a, b: fx
    return A._compute_quality_factor("X.NS")


qcases = [
    ("Q01", "all three parts present", dict(f_score=7, info={"returnOnEquity": 0.18, "freeCashflow": 5e9, "marketCap": 1e11}),
     dict(f_score=7, roe=0.18, fcf=5e9, mktcap=1e11)),
    ("Q02", "Piotroski only", dict(f_score=5, info={}), dict(f_score=5)),
    ("Q03", "ROE from the statements when the summary lacks it",
     dict(f_score=6, info={"marketCap": 2e10}, der={"roe": 0.25, "free_cashflow": 1e9}),
     dict(f_score=6, roe=0.25, fcf=1e9, mktcap=2e10)),
    ("Q04", "market cap missing: FCF yield dropped, not zero",
     dict(f_score=6, info={"returnOnEquity": 0.1, "freeCashflow": 1e9}), dict(f_score=6, roe=0.1)),
    ("Q05", "negative book value: capped at 0 then -0.5",
     dict(f_score=8, info={"returnOnEquity": 0.3, "bookValue": -3.3, "marketCap": 1e10}),
     dict(f_score=8, roe=0.3, book_value=-3.3)),
    ("Q06", "loss-making and negative operating cash flow",
     dict(f_score=4, info={"returnOnEquity": -0.05, "netIncomeToCommon": -1e8, "operatingCashflow": -2e8}),
     dict(f_score=4, roe=-0.05, net_income=-1e8, ocf=-2e8)),
    ("Q07", "interest cover 1.2x is penalised", dict(f_score=6, info={"returnOnEquity": 0.12}, cov=1.2),
     dict(f_score=6, roe=0.12, coverage=1.2)),
    ("Q08", "interest cover exactly 1.5x is not (strict)", dict(f_score=6, info={"returnOnEquity": 0.12}, cov=1.5),
     dict(f_score=6, roe=0.12, coverage=1.5)),
    ("Q09", "accounts in USD converted at the FX rate",
     dict(f_score=7, info={"returnOnEquity": 0.3, "freeCashflow": 3e9, "marketCap": 6e12,
                           "financialCurrency": "USD", "currency": "INR"}, fx=83.0),
     dict(f_score=7, roe=0.3, fcf=3e9, mktcap=6e12, fx=83.0)),
    ("Q10", "accounts in USD with no FX rate: FCF dropped",
     dict(f_score=7, info={"returnOnEquity": 0.3, "freeCashflow": 3e9, "marketCap": 6e12,
                           "financialCurrency": "USD", "currency": "INR"}, fx=None),
     dict(f_score=7, roe=0.3)),
    ("Q11", "Piotroski failed: ROE alone", dict(f_score=None, info={"returnOnEquity": 0.2}), dict(roe=0.2)),
    ("Q12", "nothing available: refused", dict(f_score=None, info={}), dict()),
    ("Q13", "extreme ROE 300% stays bounded", dict(f_score=9, info={"returnOnEquity": 3.0}), dict(f_score=9, roe=3.0)),
    ("Q14", "net income exactly 0 is not loss-making", dict(f_score=5, info={"returnOnEquity": 0.0, "netIncomeToCommon": 0}),
     dict(f_score=5, roe=0.0, net_income=0)),
    ("Q15", "Piotroski 0 counts as measured (not missing)", dict(f_score=0, info={}), dict(f_score=0)),
]
for cid, name, kw, okw in qcases:
    act, exp = run_q(**kw), oracle_quality(**okw)
    check(cid, name, close(act["score"], exp["score"], 1e-4) and close(act["confidence"], exp["confidence"], 1e-9),
          f"actual {act['score']}/{act['confidence']} expected {exp['score']}/{exp['confidence']}")
    check(cid + "b", name + " — within [-1, 1]", -1 <= act["score"] <= 1)
act = run_q(f_score=None, info={})
check("Q16", "refusal carries a reason", act.get("reason") == "no quality inputs available", act.get("reason"))
MET.piotroski_score = lambda t: (_ for _ in ()).throw(RuntimeError("provider down"))
A._ticker_info = lambda t: {"returnOnEquity": 0.2}
act = A._compute_quality_factor("X.NS")
check("Q17", "an exception inside a helper degrades to a refusal, never raises",
      act["confidence"] == 0.0 and "reason" in act, act.get("reason"))


# ===========================================================================
section("4. VALUE — P/E and P/B z-scores against up to 3 sector peers")
# ===========================================================================

def run_v(pe, pb, peers):
    infos = {"X.NS": {"trailingPE": pe, "priceToBook": pb}}
    names = []
    for i, (ppe, ppb) in enumerate(peers):
        infos[f"P{i}.NS"] = {"trailingPE": ppe, "priceToBook": ppb}
        names.append(f"P{i}.NS")
    A._ticker_info = lambda t: dict(infos.get(t, {}))
    return A._compute_value_factor("X.NS", names or ["NONE.NS"])


vcases = [
    ("V01", "three peers, both multiples", 18.0, 2.5, [(25, 4.0), (30, 5.0), (20, 3.0)]),
    ("V02", "one peer: market averages for both", 30.0, 6.0, [(25, 4.0)]),
    ("V03", "two peer P/Es, one peer P/B", 15.0, 1.0, [(25, 4.0), (30, None), (None, None)]),
    ("V04", "negative P/E: P/B only, confidence halved", -12.0, 2.0, [(25, 4.0), (30, 5.0), (20, 3.0)]),
    ("V05", "both multiples negative: -0.5 at 0.6", -5.0, -4.09, [(25, 4.0), (30, 5.0)]),
    ("V06", "both missing: refused", None, None, [(25, 4.0), (30, 5.0)]),
    ("V07", "identical peers: spread floored (1 and 0.5)", 30.0, 4.0, [(20, 3.0), (20, 3.0), (20, 3.0)]),
    ("V08", "five peers: only the first three used", 22.0, 3.0, [(10, 1), (12, 1.2), (14, 1.4), (90, 20), (95, 25)]),
    ("V09", "P/E absent (not negative): one leg, no distress", None, 2.0, [(25, 4.0), (30, 5.0), (20, 3.0)]),
    ("V10", "P/E exactly 0 is treated as non-positive", 0.0, 2.0, [(25, 4.0), (30, 5.0), (20, 3.0)]),
    ("V11", "extreme P/E 900", 900.0, 3.0, [(25, 4.0), (30, 5.0), (20, 3.0)]),
]
for cid, name, pe, pb, peers in vcases:
    act, exp = run_v(pe, pb, peers), oracle_value(pe, pb, peers)
    check(cid, name, close(act["score"], exp["score"], 1e-4) and close(act["confidence"], exp["confidence"], 1e-9),
          f"actual {act['score']}/{act['confidence']} expected {exp['score']}/{exp['confidence']}")
    check(cid + "b", name + " — within [-1, 1]", -1 <= act["score"] <= 1)

act = run_v(-12.0, 4.0, [(25, 4.0), (30, 5.0), (20, 3.0)])
check("V12", "negative P/E is flagged as distress", act.get("distress_flags") == ["negative earnings"])
check("V13", "a one-leg, distressed score says so in its interpretation (score in the middle band)",
      "Valued on one measure only" in (act.get("interpretation") or ""),
      f"score {act['score']}: '{act.get('interpretation')}'", defect="D-04")
act = run_v(None, None, [(25, 4.0)])
check("V14", "refusal carries a reason", act.get("reason") == "no valuation data")


# ===========================================================================
section("5. COMPOSITE — 100 x (0.25 S + 0.35 M + 0.25 Q + 0.15 V), labels, refusal")
# ===========================================================================

def run_c(f, mcap=1e11, ticker="SYN.NS", **kw):
    A._SCORE_CACHE.clear()
    A._compute_sentiment_factor = lambda t: dict(score=f["sentiment"][0], confidence=f["sentiment"][1])
    A._compute_momentum_factor = lambda t, p=None: dict(score=f["momentum"][0], confidence=f["momentum"][1],
                                                        **({"reason": f["momentum"][2]} if len(f["momentum"]) > 2 else {}))
    A._compute_quality_factor = lambda t: dict(score=f["quality"][0], confidence=f["quality"][1])
    A._compute_value_factor = lambda t, p=None: dict(score=f["value"][0], confidence=f["value"][1])
    A._ticker_info = lambda t: ({"marketCap": mcap} if mcap else {})
    return A.compute_alpha_score(ticker, **kw)


def F(s, m, q, v, cs=1.0, cm=1.0, cq=0.85, cv=0.8):
    return {"sentiment": (s, cs), "momentum": (m, cm), "quality": (q, cq), "value": (v, cv)}


synthetic = [
    ("C01", "favourable on every factor", F(0.8, 0.9, 0.7, 0.6)),
    ("C02", "unfavourable on every factor", F(-0.8, -0.9, -0.7, -0.6)),
    ("C03", "mixed: strong momentum, poor value", F(0.0, 0.95, 0.1, -0.9)),
    ("C04", "mixed: cheap and weak", F(-0.2, -0.4, -0.6, 0.95)),
    ("C05", "all +1 (maximum)", F(1, 1, 1, 1)),
    ("C06", "all -1 (minimum)", F(-1, -1, -1, -1)),
    ("C07", "all neutral", F(0, 0, 0, 0)),
    ("C08", "sentiment missing (refused)", F(0.0, 0.5, 0.5, 0.5, cs=0.0)),
    ("C09", "momentum and sentiment missing", F(0.0, 0.0, 0.6, 0.6, cs=0.0, cm=0.0)),
    ("C10", "only value measured", F(0.0, 0.0, 0.0, 0.9, cs=0, cm=0, cq=0)),
    ("C11", "distress value judgement (-0.5 at 0.6)", F(0.1, 0.2, -0.3, -0.5, cv=0.6)),
    ("C12", "lands exactly on +15", F(0.0, 0.0, 0.6, 0.0)),
    ("C13", "just above +15", F(0.0, 0.0, 0.6004, 0.0)),
    ("C14", "lands exactly on +40", F(0.0, 0.0, 1.0, 1.0)),
    ("C15", "just above +40", F(0.0, 0.0006, 1.0, 1.0)),
    ("C16", "lands exactly on -15", F(0.0, 0.0, -0.6, 0.0)),
    ("C17", "just below -15", F(0.0, 0.0, -0.6004, 0.0)),
    ("C18", "lands exactly on -40", F(0.0, 0.0, -1.0, -1.0)),
    ("C19", "just below -40", F(0.0, -0.0006, -1.0, -1.0)),
    ("C20", "extreme mixed", F(1.0, -1.0, 1.0, -1.0)),
    ("C21", "tiny values (rounding)", F(0.00004, -0.00003, 0.00002, 0.00001)),
    ("C22", "low confidence everywhere", F(0.3, 0.3, 0.3, 0.3, cs=0.1, cm=0.4, cq=0.34, cv=0.25)),
]
for cid, name, f in synthetic:
    act = run_c(f)
    a, c, lab = oracle_composite(f)
    contrib_ok = all(close(act["contributions"][k], round(W[k] * f[k][0] * 100, 2), 1e-9) for k in W)
    check(cid, name + " — score, coverage, label", close(act["alpha_score"], a, 1e-9)
          and close(act["confidence"], c, 1e-9) and act["signal"] == lab,
          f"actual {act['alpha_score']}/{act['confidence']}/{act['signal']} expected {a}/{c}/{lab}")
    check(cid + "b", name + " — contributions", contrib_ok)

r1, r2 = run_c(F(0.2, 0.3, 0.1, -0.1), ticker="AAA.NS"), run_c(F(0.2, 0.3, 0.1, -0.1), ticker="BBB.NS")
check("C23", "two companies with identical inputs score identically",
      r1["alpha_score"] == r2["alpha_score"] and r1["signal"] == r2["signal"])
r = run_c(F(0, 0, 0.5, 0.5, cm=0.0), mcap=None)
check("C24", "no momentum and no market cap: refused", "error" in r, r.get("error"))
r = run_c({"sentiment": (0, 0), "momentum": (0, 0, "price history too short"), "quality": (0.5, 0.85),
           "value": (0.5, 0.8)}, mcap=None)
check("C25", "short history and no market cap: refusal says the company exists",
      "fewer than 60" in (r.get("error") or ""), r.get("error"))
r = run_c(F(0, 0, 0.5, 0.5, cm=0.0), mcap=5e9)
check("C26", "no momentum but a market cap: scored, momentum contributes 0",
      "error" not in r and r["contributions"]["momentum"] == 0.0)
r = run_c(F(0.1, 0.1, 0.1, 0.1), ticker="  tcs ")
check("C27", "bare lower-case symbol normalised to .NS", r.get("ticker") == "TCS.NS", r.get("ticker"))
r = run_c(F(0.1, 0.1, 0.1, 0.1), ticker="RELIANCE.BO")
check("C28", "non-NSE suffix refused", "error" in r)
r = run_c(F(0.1, 0.1, 0.1, 0.1), ticker="")
check("C29", "empty ticker refused", "error" in r)
r = run_c(F(0.2, 0.3, 0.1, -0.1), weights={"sentiment": 0, "momentum": 1, "quality": 0, "value": 0})
check("C30", "custom weights are applied and not cached", close(r["alpha_score"], 30.0) and len(A._SCORE_CACHE) == 0)
r = run_c(F(float("nan"), 0.3, 0.1, -0.1))
check("C31", "a NaN factor score is not turned into a confident label",
      r.get("alpha_score") is None and r.get("signal") == "NEUTRAL" or "error" in r,
      f"alpha {r.get('alpha_score')} signal {r.get('signal')} — specification does not define this case")
r = run_c(F(0.2, 0.3, 0.1, -0.1))
check("C32", "result carries model version, coverage meaning and timestamp",
      r.get("model_version") == A.MODEL_VERSION and r.get("confidence_means") == "data_completeness"
      and r.get("computed_at"))
check("C33", "weights total 1.0", close(sum(A.FACTOR_WEIGHTS.values()), 1.0, 1e-12))
check("C34", "weights match the documented methodology", A.FACTOR_WEIGHTS == W)


# ===========================================================================
section("6. STORAGE — scan table, factor history, tiers (temporary SQLite)")
# ===========================================================================
import universe_scan as U      # noqa: E402
import factor_history as FH    # noqa: E402

DB = os.path.join(TMP, "quant_platform.db")
U._init_db()
try:
    c = sqlite3.connect(DB)
    c.execute("ALTER TABLE alpha_scan2 ADD COLUMN model_version TEXT")
    c.commit(); c.close()
except Exception:
    pass
import factor_provenance as FP  # noqa: E402
FP.capture = lambda *a, **k: {"complete": True}
DF.get_current_price = lambda t: {"price": 100.0}

res = {"alpha_score": 12.5, "signal": "NEUTRAL", "confidence": 0.7, "market_cap": 5e11,
       "factors": {"momentum": {"score": 0.0, "confidence": 0.0, "reason": "price history too short"},
                   "quality": {"score": 0.3, "confidence": 0.85}, "value": {"score": 0.2, "confidence": 0.8},
                   "sentiment": {"score": 0.1, "confidence": 0.5}}}
U._save_result("SYN.NS", "2099-01-01", res)
U._save_result("SYN.NS", "2099-01-01", res)
c = sqlite3.connect(DB)
n = c.execute("SELECT COUNT(*) FROM alpha_scan2 WHERE ticker='SYN.NS' AND cycle='2099-01-01'").fetchone()[0]
check("D01", "re-saving the same stock and cycle keeps one row", n == 1, n)
row = c.execute("SELECT momentum, quality, value, sentiment, alpha_score FROM alpha_scan2 WHERE ticker='SYN.NS'").fetchone()
check("D02", "scan table stores the factor scores exactly", row == (0.0, 0.3, 0.2, 0.1, 12.5), row)
fh = c.execute("SELECT momentum, quality, value, sentiment, alpha_score, cycle_id FROM factor_history "
               "WHERE ticker='SYN.NS' AND model='v1'").fetchall()
check("D03", "history keeps one row per stock per day", len(fh) == 1, len(fh))
check("D04", "a refused factor is stored as NULL in history, not 0", fh and fh[0][0] is None, fh)
check("D05", "history matches the scan table", fh and fh[0][1:5] == (0.3, 0.2, 0.1, 12.5))
FH.record("SYN.NS", "v1", alpha_score=None, factors={"quality": {"score": 0.31, "confidence": 0.85}},
          captured_at=c.execute("SELECT captured_at FROM factor_history WHERE ticker='SYN.NS'").fetchone()[0])
fh2 = c.execute("SELECT alpha_score, quality, value FROM factor_history WHERE ticker='SYN.NS'").fetchone()
check("D06", "a partial later write does not erase the fuller record", fh2 == (12.5, 0.31, 0.2), fh2)
check("D07", "history rejects an unknown model name", FH.record("SYN.NS", "v9", alpha_score=1.0) is False)
U._save_result("BAD.NS", "2099-01-01", {"error": "No market data found"})
n = c.execute("SELECT COUNT(*) FROM factor_history WHERE ticker='BAD.NS'").fetchone()[0]
check("D08", "an error result is stored in the scan table but never in history", n == 0)

# Tiers: rank by stored market cap, serve only the last complete cycle.
c.execute("DELETE FROM alpha_scan2")
rr = random.Random(5)
rows = []
for i in range(300):
    rows.append((f"T{i:03d}.NS", round(rr.uniform(-60, 60), 2), "x", 0.2 if i % 50 == 0 else 0.7,
                 1e12 - i * 1e9, 0.1, 0.2, 0.3, 0.4, None, "2099-01-02", "now", U.MODEL_VERSION))
rows.append(("ERR.NS", 99.0, "x", 0.9, 9e13, 0, 0, 0, 0, "boom", "2099-01-02", "now", U.MODEL_VERSION))
rows.append(("OLD.NS", 99.0, "x", 0.9, 9e13, 0, 0, 0, 0, None, "2099-01-01", "now", U.MODEL_VERSION))
c.executemany("INSERT INTO alpha_scan2 (ticker, alpha_score, signal, confidence, market_cap, momentum, quality,"
              " value, sentiment, error, cycle, scanned_at, model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
c.execute("DELETE FROM alpha_scan_state")
c.execute("INSERT INTO alpha_scan_state (id, cycle, status, last_complete_cycle) VALUES (1,'2099-01-03','running','2099-01-02')")
c.commit()
import liquidity as LQ  # noqa: E402
LQ.annotate = lambda recs: None
top = U.top_by_tier(n=10)
eligible = sorted([r for r in rows[:300] if r[3] >= 0.3], key=lambda r: -r[4])
large = {r[0] for r in eligible[:100]}
mid = {r[0] for r in eligible[100:250]}
got_large = {r["ticker"] for r in top["large_cap"]["buys"] + top["large_cap"]["avoids"]}
check("D09", "serves the last complete cycle only", top["serving_cycle"] == "2099-01-02"
      and all(r["ticker"] != "OLD.NS" for t in ("large_cap", "mid_cap", "small_cap") for r in top[t]["buys"]))
check("D10", "errored rows and rows under the confidence floor are excluded",
      top["universe_scored"] == len(eligible) and "ERR.NS" not in got_large, top["universe_scored"])
check("D11", "large tier is market-cap ranks 1-100 of the eligible set", got_large <= large
      and top["large_cap"]["scored"] == 100 and top["mid_cap"]["scored"] == len(mid))
exp_buys = [r[0] for r in sorted([r for r in eligible[:100]], key=lambda r: -r[1])[:10]]
check("D12", "top buys are the ten highest scores in the tier, in order",
      [r["ticker"] for r in top["large_cap"]["buys"]] == exp_buys)
check("D13", "buys and avoids never overlap",
      not ({r["ticker"] for r in top["large_cap"]["buys"]} & {r["ticker"] for r in top["large_cap"]["avoids"]}))
b0 = top["large_cap"]["buys"][0]
check("D14", "tier contributions are weight x stored score x 100",
      b0["contributions"] == {"momentum": 3.5, "quality": 5.0, "value": 4.5, "sentiment": 10.0}, b0["contributions"])

# D-05: a factor refused at scan time is NULL in history; the tiers must say so.
c.execute("INSERT INTO factor_history (ticker, captured_at, model, alpha_score, momentum, quality, value,"
          " sentiment, cycle_id) VALUES (?,?,?,?,?,?,?,?,?)",
          (b0["ticker"], "2099-01-02", "v1", b0["alpha_score"], None, 0.2, 0.3, None, "2099-01-02"))
c.commit()
top2 = U.top_by_tier(n=10)
b0b = next(r for r in top2["large_cap"]["buys"] if r["ticker"] == b0["ticker"])
others = [r for r in top2["large_cap"]["buys"] if r["ticker"] != b0["ticker"]]
check("D15", "tiers flag factors that were not measured (NULL in history), and only those",
      b0b.get("not_measured") == ["momentum", "sentiment"] and all(r.get("not_measured") == [] for r in others),
      b0b.get("not_measured"), defect="D-05")
check("D16", "flagging changes no score or ranking",
      [r["ticker"] for r in top2["large_cap"]["buys"]] == exp_buys and b0b["contributions"] == b0["contributions"])
c.close()

# D-02: one failing batch must not lose every headline.
_real_get_conn = FP.get_conn


class _FailBatch:
    def __init__(self, inner):
        self._c = inner

    def executemany(self, *a, **k):
        raise RuntimeError("simulated batch failure")

    def __getattr__(self, n):
        return getattr(self._c, n)


FP.get_conn = lambda: _FailBatch(_real_get_conn())
arts = [{"title": f"headline {i}", "published_at": "2099-01-01T00:00:00", "label": "neutral",
         "confidence": 0.9, "weight": 1.0} for i in range(3)]
try:
    FP._init()
except Exception:
    pass
n_written = FP._write_articles("ART.NS", "2099-01-05", {"sentiment": {"articles_used": arts}}, "now")
FP.get_conn = _real_get_conn
c = sqlite3.connect(DB)
n_rows = c.execute("SELECT COUNT(*) FROM factor_input_articles WHERE ticker='ART.NS'").fetchone()[0]
c.close()
check("D17", "a failed headline batch is retried row by row, not dropped",
      n_written == 3 and n_rows == 3, f"returned {n_written}, stored {n_rows}", defect="D-02")


# ===========================================================================
section("7. UNIVERSE AND SECTOR MAP")
# ===========================================================================
from collections import Counter  # noqa: E402
U._bhavcopy_symbols = lambda: [t for v in DF.NSE_SECTORS.values() for t in v] + [f"Z{i:04d}.NS" for i in range(600)]
uni = U._universe()
dups = [t for t, k in Counter(uni).items() if k > 1]
check("U01", "the scan universe lists each stock once", not dups, f"duplicates: {dups}", defect="D-03")
multi = {t: [s for s, v in DF.NSE_SECTORS.items() if t in v] for t, k in
         Counter(t for v in DF.NSE_SECTORS.values() for t in v).items() if k > 1}
check("U02", "each mapped stock belongs to one sector", not multi, multi, defect="D-01")
check("U03", "Kalyan Jewellers is valued against jewellery/consumer peers, not steel",
      "TITAN.NS" in DF.get_sector_peers("KALYANKJIL.NS"), DF.get_sector_peers("KALYANKJIL.NS")[:3], defect="D-01")
check("U04", "Edelweiss (financial services) is not valued against steel makers",
      "TATASTEEL.NS" not in DF.get_sector_peers("EDELWEISS.NS")[:3], DF.get_sector_peers("EDELWEISS.NS")[:3],
      defect="D-01")


# ===========================================================================
section("8. API — FastAPI test client, stubbed model, temporary SQLite")
# ===========================================================================
try:
    import main as M  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402
    client = TestClient(M.app)
    M.compute_alpha_score = lambda t: run_c(F(0.2, 0.3, 0.1, -0.1), ticker=t)
    r = client.get("/alpha/score", params={"ticker": "SYN"})
    body = r.json()
    a, cc, lab = oracle_composite(F(0.2, 0.3, 0.1, -0.1))
    check("A01", "GET /alpha/score: 200 and the oracle's score", r.status_code == 200
          and body.get("alpha_score") == a and body.get("signal") == lab and body.get("ticker") == "SYN.NS",
          f"{r.status_code} {body.get('alpha_score')} vs {a}")
    check("A02", "response carries the four factors and contributions",
          set(body.get("factors", {})) == set(W) and set(body.get("contributions", {})) == set(W))
    r = client.get("/alpha/score")
    check("A03", "missing ticker: 422", r.status_code == 422, r.status_code)
    M.compute_alpha_score = lambda t: {"error": "No market data found for 'ZZZ.NS'."}
    r = client.get("/alpha/score", params={"ticker": "ZZZ"})
    check("A04", "unknown company: 400 with the reason, no score", r.status_code == 400
          and "No market data" in r.json().get("detail", ""), r.status_code)
    M.compute_alpha_score = lambda t: run_c(F(0.1, 0.1, 0.1, 0.1), ticker=t)
    r = client.get("/alpha/score", params={"ticker": "X.BO"})
    check("A05", "non-NSE symbol: 400", r.status_code == 400, r.status_code)
    import swr_cache  # noqa: E402
    swr_cache.cached = lambda key, ttl, fn: fn()
    M_top = client.get("/alpha/universe/top", params={"n": 10})
    tb = M_top.json()
    check("A06", "GET /alpha/universe/top matches the stored tiers",
          M_top.status_code == 200 and [x["ticker"] for x in tb["large_cap"]["buys"]] == exp_buys)
    r = client.get("/alpha/universe/top", params={"n": 0})
    check("A07", "n below 1 rejected: 422", r.status_code == 422, r.status_code)
    r = client.get("/factors/history", params={"ticker": "syn.ns"})
    h = r.json().get("history", [])
    check("A08", "GET /factors/history returns the stored row, NULL kept as null",
          r.status_code == 200 and len(h) == 1 and h[0].get("momentum") is None, h[:1])
    r = client.get("/factors/history", params={"ticker": "NOPE.NS"})
    check("A09", "unknown company history: empty list, not an error or a fabricated row",
          r.status_code == 200 and r.json().get("history") == [])
except Exception as e:
    check("A00", "API client could start", False, f"{type(e).__name__}: {e}")


# ===========================================================================
passed = sum(1 for r in RESULTS if r["status"] == "PASS")
failed = [r for r in RESULTS if r["status"] == "FAIL"]
print("\n" + "=" * 74)
print(f"passed {passed}, failed {len(failed)}")
for r in failed:
    print(f"  FAILED: {r['id']} {r['name']}" + (f"  [{r['defect']}]" if r["defect"] else ""))
if "--report" in sys.argv:
    path = sys.argv[sys.argv.index("--report") + 1]
    with open(path, "w", encoding="utf-8") as fh_out:
        json.dump({"suite": "four_factor_oracle_test", "generated_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"),
                   "synthetic_inputs": True, "passed": passed, "failed": len(failed),
                   "checks": RESULTS}, fh_out, indent=1)
sys.exit(1 if failed else 0)
