"""
false_zero_recording_test.py — a refusal is not an observation of zero.

Reproduces the 2026-09-03 finding exactly: of 2,665 research-grade rows, 101
momentum scores and 185 value scores were 0.0 not because the factor measured
zero but because it could not measure at all. Every one of the four factor
functions answers a failure with

    {"score": 0.0, "confidence": 0.0, "reason": "..."}

and factor_history stored that 0.0 verbatim, where it is indistinguishable from
a stock whose momentum genuinely is flat. A regression on that table would read
286 fabricated zeros per cycle as real measurements.

The fixture uses the production counts so the test fails the way production
failed, not the way a toy example would. It also carries the one return that
looks like a refusal and is not — value's deliberate -0.5 at confidence 0.6 for
an unusable valuation — because a fix that nulls that one has broken a genuine
judgement to tidy up a bug.
"""

import os
import sqlite3
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


DB = os.path.join(os.environ.get("TEMP", "/tmp"), "false_zero_test.db")
CYCLE = "2026-09-04"
HISTORIC = "2026-09-03"

# The exact shape of every failure return in alpha_model, copied from source.
REFUSALS = {
    "momentum_no_price": {"score": 0.0, "confidence": 0.0,
                          "reason": "price data unavailable"},
    "momentum_short": {"score": 0.0, "confidence": 0.0,
                       "reason": "insufficient price history"},
    "momentum_raised": {"score": 0.0, "confidence": 0.0,
                        "reason": "ZeroDivisionError: float division by zero"},
    "value_raised": {"score": 0.0, "confidence": 0.0,
                     "reason": "KeyError: 'trailingPE'"},
    "value_no_data": {"score": 0.0, "confidence": 0.0,
                      "reason": "no valuation data"},
    "quality_no_inputs": {"score": 0.0, "confidence": 0.0,
                          "reason": "no quality inputs available"},
    "sentiment_no_news": {"score": 0.0, "confidence": 0.0,
                          "reason": "no news found", "n_articles": 0},
    "sentiment_unscorable": {"score": 0.0, "confidence": 0.0,
                             "reason": "no scorable headlines", "n_articles": 3},
}

# Real computations. The first is the one that matters most: a stock whose
# momentum genuinely measured zero.
GENUINE_ZERO_MOM = {"score": 0.0, "confidence": 0.87, "mom_12_1_pct": 0.0,
                    "ann_vol_pct": 31.2, "risk_adj": 0.0}
GENUINE_MOM = {"score": 0.2913, "confidence": 0.87, "mom_12_1_pct": 14.2,
               "ann_vol_pct": 31.2, "risk_adj": 0.455}
GENUINE_VALUE = {"score": 0.11, "confidence": 0.8, "pe_ratio": 18.0,
                 "pb_ratio": 2.4, "sector_pe": 22.0, "sector_pb": 3.2,
                 "pe_z_score": -0.5, "pb_z_score": -0.53, "legs_used": 2,
                 "valued_on": "P/E and P/B", "peer_count": 5}
GENUINE_QUALITY = {"score": 0.42, "confidence": 0.71, "piotroski": 7,
                   "roe": 18.4, "fcf_yield": 4.1,
                   "inputs_used": ["piotroski", "roe", "fcf_yield"],
                   "distress_flags": []}
GENUINE_SENTIMENT = {"score": 0.13, "confidence": 0.52, "n_articles": 9,
                     "undated_articles": 1, "days_back": 14}

# The trap: reason present, score deliberately non-zero, confidence non-zero.
DISTRESSED_VALUE = {"score": -0.5, "confidence": 0.6,
                    "reason": "unusable valuation: negative book value"}

N_MOM_REFUSED, N_VAL_REFUSED, N_SENT_REFUSED, N_TOTAL = 101, 185, 13, 2665


def fresh_db():
    if os.path.exists(DB):
        os.remove(DB)
    c = sqlite3.connect(DB)
    c.close()


def load_module():
    fake = types.ModuleType("db")
    fake.get_conn = lambda: sqlite3.connect(DB)
    fake.IS_POSTGRES = False
    sys.modules["db"] = fake
    # record() reaches for a live price when none is passed. Nothing in this
    # test is about prices, and a network call would make it flaky.
    df = types.ModuleType("data_fetcher")
    df.get_current_price = lambda t: {"price": 100.0}
    sys.modules["data_fetcher"] = df
    for m in ("factor_history", "model_config"):
        sys.modules.pop(m, None)
    import factor_history
    return factor_history


def rows_for(cycle):
    c = sqlite3.connect(DB)
    try:
        return c.execute(
            "SELECT ticker, alpha_score, momentum, quality, value, sentiment "
            "FROM factor_history WHERE cycle_id=? ORDER BY ticker", (cycle,)
        ).fetchall()
    finally:
        c.close()


fresh_db()
fh = load_module()

# ---------------------------------------------------------------------------
print("\n1. The production failure reproduces: 2,665 observations, 286 refusals")

# A historical cycle as the OLD code left it: false zeros already on disk.
# Written with raw SQL on purpose — routing them through the fixed record()
# would produce post-fix rows and prove nothing about what happens to the
# 286 zeros already in production.
fh.record("SEED.NS", "v1", factors={}, price=1.0,
          captured_at=HISTORIC, cycle_id=HISTORIC)          # forces _init()
_c = sqlite3.connect(DB)
for i in range(50):
    _c.execute("INSERT INTO factor_history (ticker, captured_at, model, "
               "alpha_score, momentum, quality, value, sentiment, price, "
               "cycle_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (f"OLD{i:04d}.NS", HISTORIC, "v1", 1.5, 0.0, 0.42, 0.0, 0.13,
                100.0, HISTORIC))
_c.execute("DELETE FROM factor_history WHERE ticker='SEED.NS'")
_c.commit()
_c.close()
historic_before = rows_for(HISTORIC)

alpha_in = {}
for i in range(N_TOTAL):
    tk = f"S{i:05d}.NS"
    mom = (REFUSALS["momentum_no_price"] if i < N_MOM_REFUSED
           else GENUINE_ZERO_MOM if i < N_MOM_REFUSED + 40 else GENUINE_MOM)
    val = (REFUSALS["value_raised"] if i < N_VAL_REFUSED
           else DISTRESSED_VALUE if i < N_VAL_REFUSED + 25 else GENUINE_VALUE)
    sen = (REFUSALS["sentiment_no_news"] if i < N_SENT_REFUSED
           else GENUINE_SENTIMENT)
    a = round(-9.99 + i * 0.01, 2)
    alpha_in[tk] = a
    fh.record(tk, "v1", alpha_score=a,
              factors={"momentum": mom, "quality": GENUINE_QUALITY,
                       "value": val, "sentiment": sen},
              price=100.0, captured_at=CYCLE, cycle_id=CYCLE)

rows = rows_for(CYCLE)
ok(len(rows) == N_TOTAL, f"{len(rows)} observations written (expected {N_TOTAL})")

mom_null = sum(1 for r in rows if r[2] is None)
val_null = sum(1 for r in rows if r[4] is None)
sen_null = sum(1 for r in rows if r[5] is None)
mom_zero = sum(1 for r in rows if r[2] == 0.0)
val_zero = sum(1 for r in rows if r[4] == 0.0)

print(f"       momentum NULL={mom_null} zero={mom_zero} | "
      f"value NULL={val_null} zero={val_zero} | sentiment NULL={sen_null}")

# ---------------------------------------------------------------------------
print("\n2. An unavailable factor is recorded as NULL, not as a measurement")
ok(mom_null == N_MOM_REFUSED,
   f"{mom_null} momentum refusals stored NULL (expected {N_MOM_REFUSED})")
ok(val_null == N_VAL_REFUSED,
   f"{val_null} value refusals stored NULL (expected {N_VAL_REFUSED})")
ok(sen_null == N_SENT_REFUSED,
   f"{sen_null} sentiment refusals stored NULL (expected {N_SENT_REFUSED})")

# ---------------------------------------------------------------------------
print("\n3. A genuine mathematical zero is still recorded as 0.0")
ok(mom_zero == 40,
   f"{mom_zero} genuinely flat momentum readings kept 0.0 (expected 40)")
ok(mom_null + mom_zero + sum(1 for r in rows if r[2] not in (None, 0.0)) == N_TOTAL,
   "every row is accounted for as NULL, zero, or a real value")

print("\n4. A reason with a real score is NOT nulled")
ok(val_zero == 0, f"no value row was left at a false 0.0 ({val_zero})")
ok(sum(1 for r in rows if r[4] == -0.5) == 25,
   "the distressed -0.5 at confidence 0.6 survives untouched "
   f"({sum(1 for r in rows if r[4] == -0.5)} rows)")

# ---------------------------------------------------------------------------
print("\n5. Alpha output is bit-identical — this is a recording change only")
same = all(abs(r[1] - alpha_in[r[0]]) < 1e-12 for r in rows)
ok(same, "every alpha_score stored exactly as computed, refusals included")
worst = max(abs(r[1] - alpha_in[r[0]]) for r in rows)
ok(worst == 0.0, f"largest alpha difference is {worst}")

src = open(os.path.join(os.path.dirname(__file__), "..", "modules",
                        "alpha_model.py"), encoding="utf-8", errors="replace").read()
ok("is_refusal" not in src,
   "alpha_model.py does not reference the fix — the model was not touched")

# ---------------------------------------------------------------------------
print("\n6. No historical row was modified")
ok(rows_for(HISTORIC) == historic_before,
   f"the {len(historic_before)} pre-fix rows are byte-identical")
after = rows_for(HISTORIC)
ok(all(r[2] == 0.0 for r in after) and len(after) == 50,
   f"the 286 false zeros already on disk keep their 0.0 — the fix is "
   f"forward-only and rewrites no history ({len(after)} rows checked)")
ok(all(r[4] == 0.0 for r in after),
   "including the value column, on the same rows")

# ---------------------------------------------------------------------------
print("\n7. did_not_score becomes truthful")
c = sqlite3.connect(DB)
scored_mom = c.execute("SELECT COUNT(*) FROM factor_history WHERE cycle_id=? "
                       "AND momentum IS NOT NULL", (CYCLE,)).fetchone()[0]
c.close()
ok(scored_mom == N_TOTAL - N_MOM_REFUSED,
   f"momentum scored {scored_mom} of {N_TOTAL} "
   f"(expected {N_TOTAL - N_MOM_REFUSED}, was {N_TOTAL} before the fix)")

# ---------------------------------------------------------------------------
print("\n8. The refusal test itself is right about every alpha_model return")
import model_config as mc
for name, d in REFUSALS.items():
    ok(mc.is_refusal(d), f"{name} recognised as a refusal")
for name, d in (("genuine zero momentum", GENUINE_ZERO_MOM),
                ("genuine momentum", GENUINE_MOM),
                ("genuine value", GENUINE_VALUE),
                ("genuine quality", GENUINE_QUALITY),
                ("genuine sentiment", GENUINE_SENTIMENT),
                ("distressed value -0.5", DISTRESSED_VALUE)):
    ok(not mc.is_refusal(d), f"{name} is NOT a refusal")
ok(not mc.is_refusal({}), "an empty dict is not a refusal")
ok(not mc.is_refusal(None), "None is not a refusal")
ok(not mc.is_refusal({"score": 0.0, "confidence": 0.0}),
   "confidence 0 without a reason is not a refusal — it is a measurement")

# ---------------------------------------------------------------------------
print("\n9. Provenance and recording agree on what a refusal is")
import factor_provenance as fp
n_scored = 0
for key, d in REFUSALS.items():
    r = fp.capture(f"T_{key}.NS", CYCLE, {"momentum": d} if "momentum" in key
                   else {"value": d} if "value" in key
                   else {"quality": d} if "quality" in key else {"sentiment": d})
    per = r.get("factors") or {}
    n_scored += sum(1 for v in per.values() if v.get("scored"))
ok(n_scored == 0,
   f"capture() counts no refusal as scored ({n_scored} did)")
r = fp.capture("T_REAL.NS", CYCLE, {"momentum": GENUINE_MOM})
ok((r.get("factors") or {}).get("momentum", {}).get("scored") is True,
   "and still counts a real computation as scored")
ok(r.get("complete") is True,
   f"a fully-evidenced factor is complete ({r.get('complete')})")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 66)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
