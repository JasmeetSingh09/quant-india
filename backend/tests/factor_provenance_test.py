"""
factor_provenance_test.py — the inputs are stored, and storing them changed nothing.

Two obligations, and the second matters more.

The first is that the inputs behind a factor score are persisted and can
reproduce that score. The second is that adding this changed no score at all:
a provenance layer that shifts a number is not a provenance layer, it is an
undocumented model revision.

The reproduction tests are the sharp ones. It is easy to store a value called
`risk_adj` and never check that tanh(risk_adj / 1.5) is the score that was
stored beside it. If those two disagree, the record is decoration.
"""

import math
import os
import sqlite3
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


DB = os.path.join(os.environ.get("TEMP", "/tmp"), "factor_prov_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import factor_provenance as fp        # noqa: E402
import factor_history as fh           # noqa: E402
import alpha_model as am              # noqa: E402

CYCLE = "2026-09-02"

# A realistic result dict, shaped exactly as the factor functions return.
FACTORS = {
    "momentum": {"score": 0.6716, "confidence": 0.95, "mom_12_1_pct": 102.03,
                 "ann_vol_pct": 83.6, "risk_adj": 1.22},
    "quality": {"score": 0.31, "confidence": 0.7, "piotroski": 6,
                "roe": 0.184, "fcf_yield": 0.042, "inputs_used": 3,
                "distress_flags": []},
    "value": {"score": -0.12, "confidence": 0.6, "pe_ratio": 28.4,
              "pb_ratio": 3.1, "sector_pe": 24.0, "sector_pb": 2.8,
              "pe_z_score": -0.44, "pb_z_score": -0.21, "legs_used": 2,
              "valued_on": "P/E and P/B", "peer_count": 3,
              "peers_used": [{"ticker": "A.NS", "pe": 22.0, "pb": 2.5},
                             {"ticker": "B.NS", "pe": 25.0, "pb": 3.0},
                             {"ticker": "C.NS", "pe": 25.0, "pb": 2.9}]},
    # score/confidence below are the values the REAL formula produces from
    # these three articles, computed rather than invented: an arbitrary score
    # would make the reproduction test compare the fixture against itself.
    #   weighted mean = sum(numeric*w)/sum(w) = 0.3339/1.69 = 0.19757
    #   confidence    = min(1, sum(w)/(days_back*0.5)) = 1.69/7 = 0.24143
    #   score         = weighted mean * confidence     = 0.04770
    "sentiment": {"score": 0.0477, "confidence": 0.2414, "n_articles": 3,
                  "undated_articles": 1, "days_back": 14,
                  "articles_used": [
                      {"title": "Firm wins large order", "published_at": "2026-09-01T10:00:00",
                       "label": "positive", "confidence": 0.91, "weight": 0.79},
                      {"title": "Margins under pressure", "published_at": "2026-08-30T09:00:00",
                       "label": "negative", "confidence": 0.77, "weight": 0.50},
                      {"title": "Board meeting scheduled", "published_at": "2026-08-29T12:00:00",
                       "label": "neutral", "confidence": 0.60, "weight": 0.40}]},
}

print("\nA. Every consumed input is persisted")
res = fp.capture("TEST.NS", CYCLE, FACTORS, isin="INE000TEST01")
ok(res.get("error") is None, f"capture raised nothing ({res.get('error')})")
ok(res["complete"] is True, "the observation is marked complete")
got = fp.inputs_for("TEST.NS", CYCLE)
ok(got["available"], "the observation reads back")

for factor, keys in fp.CAPTURE_MAP.items():
    stored = set(got["factors"].get(factor, {}))
    ok(set(keys) <= stored,
       f"{factor}: all {len(keys)} declared inputs stored "
       f"(missing {sorted(set(keys) - stored)})")

ok("window_lookback_days" in got["factors"]["momentum"],
   "the constants that shaped the calculation are stored with it")
ok(got["isin"] == "INE000TEST01", "ISIN is recorded on the observation")

print("\nB. Peer set preserved — the value score cannot be explained without it")
ok(len(got["peers"]) == 3, f"all 3 peers stored ({len(got['peers'])})")
peers = {p["ticker"]: p for p in got["peers"]}
ok(peers["B.NS"]["pe"] == 25.0 and peers["B.NS"]["pb"] == 3.0,
   "each peer's multiples are stored, not just the aggregate")

print("\nC. Article set preserved — sentiment is otherwise unexplainable")
ok(len(got["articles"]) == 3, f"all 3 articles stored ({len(got['articles'])})")
a = {x["title"]: x for x in got["articles"]}
ok(a["Firm wins large order"]["label"] == "positive"
   and abs(a["Firm wins large order"]["confidence"] - 0.91) < 1e-9,
   "FinBERT label and confidence survive the round trip")
ok(a["Margins under pressure"]["published_at"].startswith("2026-08-30"),
   "publication timestamps survive")

print("\nD. Stored inputs REPRODUCE the score")
m = got["factors"]["momentum"]
recomputed = math.tanh(m["risk_adj"]["value"] / am.MOMENTUM_TANH_DIVISOR)
ok(abs(round(recomputed, 4) - FACTORS["momentum"]["score"]) < 5e-4,
   f"momentum: tanh(risk_adj/{am.MOMENTUM_TANH_DIVISOR}) = {recomputed:.4f} "
   f"vs stored {FACTORS['momentum']['score']}")

v = got["factors"]["value"]
ok(abs(v["pe_ratio"]["value"] - 28.4) < 1e-9
   and abs(v["sector_pe"]["value"] - 24.0) < 1e-9,
   "value: both sides of the z-score are stored, so it can be recomputed")

s_art = got["articles"]
num = {"positive": 1, "negative": -1, "neutral": 0}
wsum = sum(x["weight"] for x in s_art)
days_back = got["factors"]["sentiment"]["days_back"]["value"]
weighted_mean = sum(num[x["label"]] * x["confidence"] * x["weight"]
                    for x in s_art) / wsum
# The score is the weighted mean SHRUNK by confidence, and confidence divides
# by days_back — which is why days_back had to become a stored input. Without
# it the article set alone cannot reproduce the score, and this test is what
# established that.
conf = min(1.0, wsum / (days_back * 0.5))
recon = weighted_mean * conf
ok(abs(round(recon, 4) - FACTORS["sentiment"]["score"]) < 1e-3,
   f"sentiment: stored articles + days_back reproduce the score "
   f"({recon:.4f} vs {FACTORS['sentiment']['score']})")
ok(abs(round(conf, 4) - FACTORS["sentiment"]["confidence"]) < 1e-3,
   f"sentiment: confidence is reproducible too ({conf:.4f})")

print("\nE. Missing input is explicit, never a plausible-looking number")
thin = {"quality": {"score": 0.1, "piotroski": None, "roe": None,
                    "fcf_yield": 0.01, "inputs_used": 1, "distress_flags": []}}
fp.capture("THIN.NS", CYCLE, thin)
tg = fp.inputs_for("THIN.NS", CYCLE)
q = tg["factors"]["quality"]
ok(q["roe"]["missing"] is True and q["roe"]["value"] is None,
   "an absent input is stored as missing=True with a null value")
ok(q["fcf_yield"]["missing"] is False, "a present input is not flagged missing")
ok(q["roe"]["value"] != 0, "absent is never recorded as zero")

print("\nF. A factor that could not score does not fake completeness")
none_scored = {"quality": {"score": None, "piotroski": None, "roe": None,
                           "fcf_yield": None, "inputs_used": 0,
                           "distress_flags": []}}
r2 = fp.capture("NOSCORE.NS", CYCLE, none_scored)
ok(r2["complete"] is True,
   "a factor that honestly produced no score does not block completeness")
partial = {"momentum": {"score": 0.5, "mom_12_1_pct": 10.0,
                        "ann_vol_pct": None, "risk_adj": None}}
r3 = fp.capture("PARTIAL.NS", CYCLE, partial)
ok(r3["complete"] is False,
   "a factor that SCORED but lost inputs is not complete")

print("\nG. Duplicates are impossible")
before = fp.coverage()["input_rows"]
fp.capture("TEST.NS", CYCLE, FACTORS, isin="INE000TEST01")
after = fp.coverage()["input_rows"]
ok(before == after,
   f"re-capturing the same (ticker, cycle) adds no rows ({before} -> {after})")
con = sqlite3.connect(DB)
dupes = con.execute(
    "SELECT COUNT(*) FROM (SELECT ticker, cycle_id, factor, input_name, "
    "COUNT(*) c FROM factor_inputs GROUP BY 1,2,3,4 HAVING c > 1) t").fetchone()[0]
ok(dupes == 0, f"no duplicate (ticker, cycle, factor, input) rows ({dupes})")
pdupes = con.execute(
    "SELECT COUNT(*) FROM (SELECT ticker, cycle_id, peer_ticker, COUNT(*) c "
    "FROM factor_input_peers GROUP BY 1,2,3 HAVING c > 1) t").fetchone()[0]
ok(pdupes == 0, "no duplicate peer rows")
con.close()

print("\nH. Provenance categories — Yahoo data is never labelled point-in-time")
cats = {n: m["category"] for n, m in fp.FIELD_CATALOG.items()}
yahoo = [n for n, c in cats.items() if c == fp.OBSERVATION_YAHOO]
ok(len(yahoo) >= 6, f"{len(yahoo)} fields categorised observation_yahoo")
ok(fp.PIT_MARKET not in set(cats.values()),
   "NO stored field claims to be point-in-time market data")
ok(all(m["pit"] is False for m in fp.FIELD_CATALOG.values()),
   "no catalogued field claims pit=True")
ok("not point-in-time" in got["provenance_note"].lower()
   or "NOT point-in-time" in got["provenance_note"],
   "the read-back output states the limitation in words")
for name, meta in fp.FIELD_CATALOG.items():
    missing = [k for k in ("meaning", "source", "kind", "category", "pit",
                           "reproduces", "immutable") if k not in meta]
    if missing:
        ok(False, f"{name} documents all required attributes (missing {missing})")
ok(all(all(k in m for k in ("meaning", "source", "kind", "category", "pit",
                            "reproduces", "immutable"))
       for m in fp.FIELD_CATALOG.values()),
   f"all {len(fp.FIELD_CATALOG)} catalogued fields document every attribute")

print("\nI. Existing observations are not rewritten")
fh._READY = False
fh.record("OLD.NS", "v1", alpha_score=5.0,
          factors={"momentum": {"score": 0.2}}, price=100.0,
          captured_at="2026-08-23")
con = sqlite3.connect(DB)
row = con.execute("SELECT raw_inputs_available FROM factor_history "
                  "WHERE ticker='OLD.NS'").fetchone()
ok(row and row[0] == 0,
   "an observation written without inputs is flagged raw_inputs_available=0")
fh.record("NEW.NS", "v1", alpha_score=5.0,
          factors={"momentum": {"score": 0.2}}, price=100.0,
          captured_at="2026-09-02", raw_inputs_available=True)
row = con.execute("SELECT raw_inputs_available FROM factor_history "
                  "WHERE ticker='NEW.NS'").fetchone()
ok(row and row[0] == 1, "an observation with inputs is flagged 1")

# Sticky: a later partial write must not erase a captured day.
fh.record("NEW.NS", "v1", alpha_score=6.0,
          factors={"quality": {"score": 0.3}}, price=101.0,
          captured_at="2026-09-02", raw_inputs_available=False)
row = con.execute("SELECT raw_inputs_available, momentum FROM factor_history "
                  "WHERE ticker='NEW.NS'").fetchone()
ok(row[0] == 1, "a later write without inputs cannot downgrade the flag")
ok(row[1] is not None, "and the earlier factor score is still merged, not lost")
con.close()

print("\nJ. Capture cannot break a scan")
ok(fp.capture(None, None, None) is not None, "null input returns, never raises")
ok(fp.capture("X.NS", CYCLE, {"momentum": "not-a-dict"}).get("error") is None,
   "a malformed factor payload is survived")


class _Boom(dict):
    def get(self, *a, **k):
        raise RuntimeError("upstream exploded")


r4 = fp.capture("BOOM.NS", CYCLE, _Boom())
ok(isinstance(r4, dict), "an exploding payload still returns a dict")

print("\nK. The catalogue matches what is actually captured")
for factor, keys in fp.CAPTURE_MAP.items():
    for k in keys:
        name = f"{factor}.{k}"
        if name not in fp.FIELD_CATALOG and k not in ("peer_count",):
            ok(False, f"{name} is captured but not documented")
undocumented = [f"{f}.{k}" for f, ks in fp.CAPTURE_MAP.items() for k in ks
                if f"{f}.{k}" not in fp.FIELD_CATALOG]
ok(not undocumented,
   f"every captured input is documented ({undocumented})")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 68)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
