"""
data_integrity_test.py — an audit that cannot fail is not an audit.

Every check here is verified by BREAKING the data and confirming the check
notices, then repairing it and confirming the check clears. A check that has
only ever seen clean data has not been tested; it has been exercised.

That distinction matters more than usual here, because the test machinery in
this hardening phase has been wrong three times already: a tolerance derived at
one volatility and applied at another, an exception handler that turned HTTP 429
into "no data" and silently shrank the sample, and a stub that disabled the very
guard layer it was meant to be testing. Each reported a clean result on a sample
it had quietly narrowed.

So two properties are asserted throughout:

    the check FIRES on a defect, and CLEARS when the defect is removed;
    the `examined` count is the real number of rows, not an intention.

The second is the governing rule of Step 3. "6.6M rows checked" has to mean
6.6M rows were read, and the only way to know is to control the row count and
assert it.

Nothing here touches production. The audit runs against a local SQLite file
built for the purpose and deleted afterwards.
"""

import os
import sqlite3
import sys
import types
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "data_integrity_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import data_integrity as DI  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


N_SYMS, N_DAYS = 20, 30
EXPECTED_ROWS = N_SYMS * N_DAYS


def build_clean():
    if os.path.exists(DB):
        os.remove(DB)
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE bhavcopy_eod (
        symbol TEXT NOT NULL, day TEXT NOT NULL, open REAL, high REAL,
        low REAL, close REAL, volume REAL, isin TEXT,
        PRIMARY KEY (symbol, day))""")
    conn.execute("""CREATE TABLE factor_inputs (
        ticker TEXT, isin TEXT, cycle_id TEXT, observed_at TEXT, factor TEXT,
        input_name TEXT, value_num REAL, value_text TEXT, category TEXT,
        source TEXT, missing INTEGER DEFAULT 0,
        PRIMARY KEY (ticker, cycle_id, factor, input_name))""")
    d0 = date(2026, 1, 1)
    rows = []
    for s in range(N_SYMS):
        for k in range(N_DAYS):
            day = (d0 + timedelta(days=k)).isoformat()
            base = 100.0 + s
            rows.append((f"S{s}.NS", day, base, base + 2, base - 2, base + 1,
                         10000.0, f"INE{s:09d}"))
    conn.executemany("INSERT INTO bhavcopy_eod (symbol, day, open, high, low,"
                     " close, volume, isin) VALUES (?,?,?,?,?,?,?,?)", rows)

    fi = []
    for s in range(N_SYMS):
        for f, names in (("momentum", ["mom_12_1_pct", "ann_vol_pct"]),
                         ("value", ["pe_ratio", "pb_ratio"])):
            for nm in names:
                miss = 1 if (f == "value" and nm == "pe_ratio" and s % 5 == 0) else 0
                fi.append((f"S{s}.NS", f"INE{s:09d}", "2026-01-30",
                           "2026-01-30T00:00:00", f, nm, 1.0, None,
                           "derived", "test", miss))
    fi.append(("S0.NS", "INE000000000", "2026-01-30", "2026-01-30T00:00:00",
               "value", "refusal_reason", None, "no valuation data",
               "derived", "test", 0))
    conn.executemany("INSERT INTO factor_inputs (ticker, isin, cycle_id,"
                     " observed_at, factor, input_name, value_num, value_text,"
                     " category, source, missing) VALUES (?,?,?,?,?,?,?,?,?,?,?)", fi)
    conn.commit()
    conn.close()


def corrupt(sql):
    # The close has to be in a finally: one of these statements is EXPECTED to
    # raise (the duplicate the primary key refuses), and a leaked handle then
    # locks the file on Windows and takes the rest of the run down with it.
    conn = sqlite3.connect(DB)
    try:
        conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def status_of(name, report=None):
    r = report or DI.price_integrity()
    for f in r.get("findings", []):
        if f["check"] == name:
            return f
    return None


print("=" * 74)
print("THE CLEAN DATASET PASSES, AND EXAMINES WHAT IT SAYS IT DOES")
print("=" * 74)

build_clean()
r = DI.price_integrity()
print(f"  examined: {r['examined']}")
check("the clean dataset passes", r["status"] == "PASS", r["status"])
check("the examined ROW count is the real one",
      r["examined"]["rows"] == EXPECTED_ROWS,
      f"{r['examined']['rows']} vs {EXPECTED_ROWS} seeded")
check("the examined SECURITY count is the real one",
      r["examined"]["securities"] == N_SYMS, f"{r['examined']['securities']}")
check("the examined DAY count is the real one",
      r["examined"]["trading_days"] == N_DAYS, f"{r['examined']['trading_days']}")
check("every finding carries its own examined count",
      all(f["examined"] == EXPECTED_ROWS for f in r["findings"]),
      "so a verdict cannot drift from the sample it came from")

print()
print("=" * 74)
print("SYNTHETIC CORRUPTION — EACH DEFECT MUST TRIP ITS OWN CHECK")
print("=" * 74)

CORRUPTIONS = [
    ("high < low",
     "UPDATE bhavcopy_eod SET high = 1, low = 999 "
     "WHERE symbol='S3.NS' AND day='2026-01-05'",
     "high >= low"),
    ("negative close",
     "UPDATE bhavcopy_eod SET close = -5 "
     "WHERE symbol='S4.NS' AND day='2026-01-06'",
     "close is positive"),
    ("null close",
     "UPDATE bhavcopy_eod SET close = NULL "
     "WHERE symbol='S5.NS' AND day='2026-01-07'",
     "close is present"),
    ("close above its own high",
     "UPDATE bhavcopy_eod SET close = high + 50 "
     "WHERE symbol='S6.NS' AND day='2026-01-08'",
     "close lies within its own high-low range"),
    ("null OHLC",
     "UPDATE bhavcopy_eod SET open = NULL "
     "WHERE symbol='S7.NS' AND day='2026-01-09'",
     "open/high/low are present"),
    ("negative volume",
     "UPDATE bhavcopy_eod SET volume = -1 "
     "WHERE symbol='S8.NS' AND day='2026-01-10'",
     "volume is not negative"),
    ("stripped ISIN",
     "UPDATE bhavcopy_eod SET isin = NULL "
     "WHERE symbol='S9.NS' AND day='2026-01-11'",
     "every row carries an ISIN"),
]

for label, sql, which in CORRUPTIONS:
    build_clean()
    before = status_of(which)
    corrupt(sql)
    after = status_of(which)
    fired = before["status"] == "PASS" and after["status"] == "FAIL"
    check(f"{label:<26} trips its check", fired,
          f"before={before['status']} after={after['status']} bad={after['bad']}")
    if fired:
        check("  ...and names the offending record", bool(after["offenders"]),
              str(after["offenders"])[:52])
        check(f"  ...and still examines all {EXPECTED_ROWS} rows",
              after["examined"] == EXPECTED_ROWS,
              "a defect must not shrink the sample")

print()
print("=" * 74)
print("A FUTURE OBSERVATION")
print("=" * 74)

# The boundary is deliberately today+1, because the server clock is UTC and NSE
# trading days are IST. So the test has to inject something unambiguously future
# -- a year out -- not "tomorrow", which is legitimately reachable.
build_clean()
FUT = (date.today() + timedelta(days=400)).isoformat()
check("today's boundary is not itself in the past",
      DI._future_boundary() >= date.today().isoformat(),
      DI._future_boundary())
before = status_of("no observation is dated in the future")
check("clean data has no future observation", before["status"] == "PASS")
corrupt(f"UPDATE bhavcopy_eod SET day = '{FUT}' "
        f"WHERE symbol='S2.NS' AND day='2026-01-20'")
after = status_of("no observation is dated in the future")
check("a future-dated observation trips the check",
      after["status"] == "FAIL", f"bad={after['bad']} offenders={after['offenders']}")
check("  ...and names it", bool(after["offenders"]))

# The UTC/IST trap that has already produced one false alarm in this project.
build_clean()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
corrupt(f"UPDATE bhavcopy_eod SET day = '{TOMORROW}' "
        f"WHERE symbol='S2.NS' AND day='2026-01-20'")
check("a row dated TOMORROW does NOT trip it",
      status_of("no observation is dated in the future")["status"] == "PASS",
      "IST runs ahead of the server's UTC clock; that is not corruption")

print()
print("=" * 74)
print("A DUPLICATE — AND PROOF THE CONSTRAINT IS WHAT STOPS IT")
print("=" * 74)

build_clean()
try:
    corrupt("INSERT INTO bhavcopy_eod (symbol, day, open, high, low, close,"
            " volume, isin) VALUES ('S1.NS','2026-01-02',1,2,0.5,1,1,'INE000000001')")
    blocked = False
except sqlite3.IntegrityError:
    blocked = True
check("the primary key REFUSES a duplicate in production shape", blocked,
      "so in production the check should never fire -- which is why it must be "
      "tested somewhere it can")

# Rebuild without the constraint, so the detector is exercised rather than
# shielded by the thing it is meant to back up.
os.remove(DB)
conn = sqlite3.connect(DB)
conn.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, open REAL,"
             " high REAL, low REAL, close REAL, volume REAL, isin TEXT)")
conn.executemany("INSERT INTO bhavcopy_eod VALUES (?,?,?,?,?,?,?,?)",
                 [(f"S{s}.NS", (date(2026, 1, 1) + timedelta(days=k)).isoformat(),
                   100.0, 102.0, 98.0, 101.0, 10000.0, f"INE{s:09d}")
                  for s in range(N_SYMS) for k in range(N_DAYS)])
conn.execute("CREATE TABLE factor_inputs (ticker TEXT, isin TEXT, cycle_id TEXT,"
             " observed_at TEXT, factor TEXT, input_name TEXT, value_num REAL,"
             " value_text TEXT, category TEXT, source TEXT, missing INTEGER)")
conn.commit()
conn.close()
check("without the constraint, clean data still passes the dup check",
      status_of("no duplicate (symbol, day)")["status"] == "PASS")
corrupt("INSERT INTO bhavcopy_eod VALUES ('S1.NS','2026-01-02',1,2,0.5,1,1,'INE000000001')")
d = status_of("no duplicate (symbol, day)")
check("an injected duplicate trips the check", d["status"] == "FAIL",
      f"bad={d['bad']}")
check("  ...and the examined count rises to 601, not stays at 600",
      d["examined"] == EXPECTED_ROWS + 1, str(d["examined"]))

print()
print("=" * 74)
print("IDENTITY — TICKER REUSE IS A DEFECT, A RENAME IS NOT")
print("=" * 74)

build_clean()
r = DI.identity_integrity()
print(f"  examined: {r['examined']}")
check("clean identity passes", r["status"] == "PASS", r["status"])
check("the symbol count is real", r["examined"]["symbols"] == N_SYMS)
check("the ISIN count is real", r["examined"]["distinct_isins"] == N_SYMS)

# Ticker reuse: one symbol, two ISINs. Two companies in one price series.
build_clean()
corrupt("UPDATE bhavcopy_eod SET isin = 'INE999999999' "
        "WHERE symbol='S1.NS' AND day > '2026-01-15'")
r = DI.identity_integrity()
f = [x for x in r["findings"] if x["check"] == "one symbol means one security"][0]
check("ticker reuse trips the identity check", f["status"] == "FAIL",
      f"bad={f['bad']} {f['offenders']}")
check("  ...and the domain FAILS", r["status"] == "FAIL", r["status"])

# A rename: one ISIN, two symbols. ZOMATO -> ETERNAL. Must NOT fail.
build_clean()
corrupt("UPDATE bhavcopy_eod SET symbol = 'S1RENAMED.NS' "
        "WHERE symbol='S1.NS' AND day > '2026-01-15'")
r = DI.identity_integrity()
check("a rename does NOT fail the audit", r["status"] == "PASS", r["status"])
check("  ...but it IS reported", bool(r["renames_observed"]),
      str(r["renames_observed"])[:60])

# An altered ISIN that is not a real ISIN at all.
build_clean()
corrupt("UPDATE bhavcopy_eod SET isin = 'GARBAGE' WHERE symbol='S2.NS'")
r = DI.identity_integrity()
f = [x for x in r["findings"] if x["check"] == "every ISIN is well formed"][0]
check("a malformed ISIN trips the check", f["status"] == "FAIL",
      f"bad={f['bad']} {f['offenders']}")

print()
print("=" * 74)
print("REPAIR MUST CLEAR IT")
print("=" * 74)

build_clean()
corrupt("UPDATE bhavcopy_eod SET high = 1, low = 999 "
        "WHERE symbol='S3.NS' AND day='2026-01-05'")
check("the corrupted dataset FAILS overall",
      DI.price_integrity()["status"] == "FAIL")
build_clean()
check("the repaired dataset PASSES again",
      DI.price_integrity()["status"] == "PASS",
      "a check that only ever passes has not been tested")

print()
print("=" * 74)
print("MISSING DATA — THE COUNTS THEMSELVES")
print("=" * 74)

build_clean()
m = DI.missing_data_audit()
print(f"  examined: {m.get('examined')}")
check("the missing-data audit runs", m["status"] == "PASS", m["status"])
by = {p["factor"]: p for p in m["per_factor"]}
check("it reports per factor", set(by) == {"momentum", "value"}, str(set(by)))
check("momentum has no missing inputs", by["momentum"]["flagged_missing"] == 0)
check("value's missing inputs are counted",
      by["value"]["flagged_missing"] == 4, f"{by['value']['flagged_missing']}")
check("a refusal is counted separately from a missing input",
      by["value"]["securities_that_refused"] == 1,
      "refusal, NULL, zero and unavailable are four different things")
check("the input row count is real",
      m["examined"]["input_rows"] == N_SYMS * 4 + 1,
      f"{m['examined']['input_rows']}")

print()
print("=" * 74)
print("CONTINUITY — A JUMP IS EITHER AN EVENT, A SPLIT, OR TWO COMPANIES")
print("=" * 74)


def seed_actions(rows):
    """rows: (isin, ex_date, kind)"""
    conn = sqlite3.connect(DB)
    conn.execute("DROP TABLE IF EXISTS corporate_actions")
    conn.execute("""CREATE TABLE corporate_actions (
        isin TEXT NOT NULL, symbol TEXT, ex_date TEXT NOT NULL, kind TEXT NOT NULL,
        num REAL, den REAL, amount REAL, subject TEXT, parsed INTEGER DEFAULT 0,
        sig TEXT NOT NULL, fetched_at TEXT,
        PRIMARY KEY (isin, ex_date, sig))""")
    conn.executemany(
        "INSERT INTO corporate_actions (isin, ex_date, kind, num, den, parsed,"
        " sig) VALUES (?,?,?,2,1,1,?)",
        [(i, d, k, f"{i}{d}") for i, d, k in rows])
    conn.commit()
    conn.close()


build_clean()
seed_actions([])
r = DI.continuity_integrity()
print(f"  examined: {r['examined']}")
check("a flat clean series has no large moves", r["status"] == "PASS", r["status"])
check("the step count is real (600 rows - 20 symbols = 580 steps)",
      r["examined"]["day_over_day_steps"] == EXPECTED_ROWS - N_SYMS,
      str(r["examined"]["day_over_day_steps"]))
check("the day span is reported",
      r["examined"].get("first_day") == "2026-01-01", str(r["examined"].get("first_day")))

# A 2-for-1 split that was never applied: the close halves overnight.
build_clean()
seed_actions([])
corrupt("UPDATE bhavcopy_eod SET close = close / 2.0, open = open / 2.0,"
        " high = high / 2.0, low = low / 2.0 "
        "WHERE symbol='S3.NS' AND day >= '2026-01-15'")
r = DI.continuity_integrity()
f = [x for x in r["findings"] if "corporate action" in x["check"]][0]
check("an unexplained 50% overnight drop trips continuity",
      f["status"] == "FAIL", f"bad={f['bad']} {f['offenders'][:2]}")

# The SAME drop, with the split on record. Must NOT fail: this is the
# adjustment layer working, and flagging it would punish correctness.
build_clean()
seed_actions([("INE000000003", "2026-01-15", "split")])
corrupt("UPDATE bhavcopy_eod SET close = close / 2.0, open = open / 2.0,"
        " high = high / 2.0, low = low / 2.0 "
        "WHERE symbol='S3.NS' AND day >= '2026-01-15'")
r = DI.continuity_integrity()
f = [x for x in r["findings"] if "corporate action" in x["check"]][0]
check("the same drop WITH a corporate action does NOT fail",
      f["status"] == "PASS", f"bad={f['bad']} {f['offenders'][:2]}")
check("  ...and the move is still counted, not hidden",
      f["examined"] >= 1, f"examined={f['examined']}")

# A resumption after a long silence is NOT an overnight move. A stock that
# stops trading and comes back months later at a different price has produced
# no defect; the two observations are simply not adjacent in time.
build_clean()
seed_actions([])
corrupt("DELETE FROM bhavcopy_eod WHERE symbol='S4.NS' "
        "AND day >= '2026-01-05' AND day <= '2026-01-25'")
corrupt("UPDATE bhavcopy_eod SET close = close * 20, open = open * 20, "
        "high = high * 20, low = low * 20 "
        "WHERE symbol='S4.NS' AND day > '2026-01-25'")
r = DI.continuity_integrity()
f = [x for x in r["findings"] if "corporate action" in x["check"]][0]
check("a resumption after a 21-day silence is NOT counted as a defect",
      f["bad"] == 0, f"bad={f['bad']}")
check("  ...but it IS reported separately, not dropped",
      r["examined"]["large_moves_after_long_silence"] == 1,
      str(r["examined"].get("resumption_examples")))
check("  ...and the adjacent count excludes it",
      r["examined"]["large_moves_adjacent"] == 0,
      str(r["examined"]["large_moves_adjacent"]))

# A calendar gap is listed, never failed -- a holiday and a hole look identical.
build_clean()
seed_actions([])
corrupt("DELETE FROM bhavcopy_eod WHERE day >= '2026-01-10' AND day <= '2026-01-20'")
r = DI.continuity_integrity()
check("a 12-day hole is reported as a gap", r["calendar_gap_count"] >= 1,
      str(r.get("calendar_gaps_over_5d"))[:60])
check("  ...but does NOT fail the domain", r["status"] == "PASS",
      "NSE holidays are not derivable from this table")

print()
print("=" * 74)
print("IDENTITY — A MERGE IS SIMULTANEOUS, A RENAME IS SEQUENTIAL")
print("=" * 74)

# Two symbols sharing one ISIN ON THE SAME DAY. No rename can produce this.
build_clean()
corrupt("UPDATE bhavcopy_eod SET isin = 'INE000000001' WHERE symbol='S2.NS'")
r = DI.identity_integrity()
f = [x for x in r["findings"] if "on any given day" in x["check"]][0]
check("a same-day ISIN collision trips the merge check", f["status"] == "FAIL",
      f"bad={f['bad']} {f['offenders'][:2]}")

# A sequential rename shares an ISIN but never on the same day.
build_clean()
corrupt("UPDATE bhavcopy_eod SET symbol = 'S1RENAMED.NS' "
        "WHERE symbol='S1.NS' AND day > '2026-01-15'")
r = DI.identity_integrity()
f = [x for x in r["findings"] if "on any given day" in x["check"]][0]
check("a sequential rename does NOT trip the merge check",
      f["status"] == "PASS", f"bad={f['bad']}")

print()
print("=" * 74)
print("FUNDAMENTALS / PIT — THE ABSENCE IS THE FINDING")
print("=" * 74)

build_clean()
seed_actions([("INE000000003", "2026-01-15", "split")])
r = DI.fundamentals_pit_integrity()
print(f"  examined: {r['examined']}")
check("the domain never reports PASS", r["status"] in ("PARTIAL", "FAIL"),
      r["status"])
check("it states outright that no fundamentals history is stored",
      r["fundamentals_history"]["stored"] is False
      and r["fundamentals_history"]["status"] == "UNMEASURED")
check("  ...and says what that costs",
      "point-in-time" in r["fundamentals_history"]["consequence"].lower())
check("corporate actions ARE counted", r["examined"]["corporate_actions"] == 1,
      str(r["examined"].get("corporate_actions")))
check("factor input rows are counted",
      r["examined"]["factor_inputs"] == N_SYMS * 4 + 1,
      str(r["examined"].get("factor_inputs")))

# An unparsed corporate action is stored, visible, and does nothing.
build_clean()
seed_actions([("INE000000003", "2026-01-15", "split")])
corrupt("UPDATE corporate_actions SET parsed = 0")
f = [x for x in DI.fundamentals_pit_integrity()["findings"]
     if "parsed into a multiplier" in x["check"]][0]
check("an unparsed corporate action trips its check", f["status"] == "FAIL",
      f"bad={f['bad']}")

# A factor input observed in the future.
build_clean()
seed_actions([])
corrupt("UPDATE factor_inputs SET observed_at = '2099-01-01T00:00:00' "
        "WHERE ticker='S1.NS'")
f = [x for x in DI.fundamentals_pit_integrity()["findings"]
     if "observed in the future" in x["check"]][0]
check("a future observation time trips its check", f["status"] == "FAIL",
      f"bad={f['bad']}")

print()
print("=" * 74)
print("MISSING DATA — FIVE STATES, AND ONLY ONE IS A DEFECT")
print("=" * 74)

build_clean()
m = DI.missing_data_audit()
by = {p["factor"]: p for p in m["per_factor"]}
check("clean inputs have nothing unexplained", m["status"] == "PASS", m["status"])
check("the five states are reported separately",
      all(k in by["value"] for k in
          ("present", "genuine_zero", "flagged_missing",
           "securities_that_refused", "unexplained")),
      str(sorted(by["value"])))

# A genuine zero is NOT missing. Zero debt is a fact.
build_clean()
corrupt("UPDATE factor_inputs SET value_num = 0 "
        "WHERE ticker='S7.NS' AND input_name='pb_ratio'")
by = {p["factor"]: p for p in DI.missing_data_audit()["per_factor"]}
check("a genuine zero is counted as a value, not as missing",
      by["value"]["genuine_zero"] == 1 and by["value"]["unexplained"] == 0,
      f"zero={by['value']['genuine_zero']} unexplained={by['value']['unexplained']}")

# A null that nobody flagged and nobody explained. The only real defect.
build_clean()
corrupt("UPDATE factor_inputs SET value_num = NULL, value_text = NULL, missing = 0 "
        "WHERE ticker='S8.NS' AND input_name='pb_ratio'")
m = DI.missing_data_audit()
by = {p["factor"]: p for p in m["per_factor"]}
check("an unflagged, unexplained null IS a defect",
      by["value"]["unexplained"] == 1, str(by["value"]["unexplained"]))
check("  ...and it fails the domain", m["status"] == "FAIL", m["status"])

print()
print("=" * 74)
print("NEWS — AN ARTICLE MUST BE ABOUT THE COMPANY IT WAS SCORED FOR")
print("=" * 74)


def seed_articles(rows):
    """rows: (ticker, title, published_at)"""
    conn = sqlite3.connect(DB)
    conn.execute("DROP TABLE IF EXISTS factor_input_articles")
    conn.execute("""CREATE TABLE factor_input_articles (
        ticker TEXT NOT NULL, cycle_id TEXT NOT NULL, title_hash TEXT NOT NULL,
        title TEXT, published_at TEXT, finbert_label TEXT,
        finbert_confidence REAL, weight REAL, observed_at TEXT,
        PRIMARY KEY (ticker, cycle_id, title_hash))""")
    conn.executemany(
        "INSERT INTO factor_input_articles (ticker, cycle_id, title_hash, title,"
        " published_at, finbert_label, finbert_confidence, weight, observed_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        [(t, "2026-09-09", str(abs(hash((t, ti)))), ti, p, "neutral", 0.5, 1.0,
          "2026-09-09T00:00:00") for t, ti, p in rows])
    conn.commit()
    conn.close()


TODAY = date.today().isoformat()

# Real headlines in the shape the app stores them, for the seven securities the
# sentiment bug was found on. RELEVANT ones name the company; the INTRUDER is a
# genuine general-market headline of exactly the kind that used to be scored as
# company news.
RELEVANT = [
    ("SBIN.NS", "State Bank of India raises MCLR by 10 bps across tenors"),
    ("ONGC.NS", "ONGC to invest Rs 1 lakh crore in green energy by 2030"),
    ("COALINDIA.NS", "Coal India output rises 5% in August"),
    ("ITC.NS", "ITC hotels demerger record date announced"),
    ("ADANIPORTS.NS", "Adani Ports handles record cargo volume in Q2"),
    ("AXISBANK.NS", "Axis Bank net profit rises 18% on lower provisions"),
    ("TCS.NS", "TCS wins multi-year deal with European retailer"),
]
INTRUDER = "Sensex ends 400 points higher; Nifty reclaims 25,000"

build_clean()
seed_articles([(t, ti, TODAY) for t, ti in RELEVANT])
r = DI.news_integrity()
print(f"  examined: {r.get('examined')}  relevance {r.get('relevance_pct')}%")
check("relevant articles pass", r["status"] == "PASS", str(r.get("reason", r["status"])))
check("the article count is real", r["examined"]["articles"] == len(RELEVANT),
      str(r["examined"]))
check("all seven securities are covered",
      r["examined"]["securities"] == 7, str(r["examined"]["securities"]))
check("relevance is 100%", r["relevance_pct"] == 100.0, str(r["relevance_pct"]))

# The regression: each company's OWN headline must match, individually. A single
# aggregate number can hide six passes and one silent failure -- which is how
# SBIN and ONGC reported confidence 1.00 on zero relevant articles.
for tk, title in RELEVANT:
    build_clean()
    seed_articles([(tk, title, TODAY)])
    rr = DI.news_integrity()
    check(f"  {tk:<15} matches its own headline",
          rr["status"] == "PASS" and rr["relevance_pct"] == 100.0,
          str(rr.get("worst_securities") or rr.get("reason", "")))

# An off-topic article must be caught.
build_clean()
seed_articles([(t, ti, TODAY) for t, ti in RELEVANT]
              + [("SBIN.NS", INTRUDER, TODAY)])
r = DI.news_integrity()
f = [x for x in r["findings"]
     if x["check"].startswith("every scored article names")][0]
check("an off-topic article trips the news check", f["status"] == "FAIL",
      f"bad={f['bad']} {f['offenders']}")
check("  ...and it is attributed to the right security",
      any("SBIN" in w for w in r["worst_securities"]),
      str(r["worst_securities"]))
check("  ...and relevance drops below 100%", r["relevance_pct"] < 100.0,
      f"{r['relevance_pct']}%")

# A future-dated article.
build_clean()
seed_articles([(t, ti, TODAY) for t, ti in RELEVANT]
              + [("TCS.NS", "TCS announces Q9 results",
                  (date.today() + timedelta(days=400)).isoformat())])
f = [x for x in DI.news_integrity()["findings"]
     if x["check"] == "no article is published in the future"][0]
check("a future-dated article trips the check", f["status"] == "FAIL",
      f"bad={f['bad']}")

# An undated article — cannot be time-decayed, so its weight is invented.
build_clean()
seed_articles([(t, ti, TODAY) for t, ti in RELEVANT]
              + [("ITC.NS", "ITC board meeting scheduled", None)])
f = [x for x in DI.news_integrity()["findings"]
     if x["check"] == "every article carries a publication date"][0]
check("an undated article trips the check", f["status"] == "FAIL",
      f"bad={f['bad']}")

# And clean again.
build_clean()
seed_articles([(t, ti, TODAY) for t, ti in RELEVANT])
check("the repaired news set passes again",
      DI.news_integrity()["status"] == "PASS")

print()
print("=" * 74)
print("ADVERSARIAL NEAR-MISSES — HEADLINES THAT LOOK RIGHT AND ARE NOT")
print("=" * 74)
print("  A friendly headline only proves the matcher says yes. These check that")
print("  it says no, which is the half that produced the 2026-09-03 defect.")
print()

# (ticker, headline, must_match). Every False here is a headline that would
# feed one company's sentiment from another company's -- or the whole market's
# -- news.
NEAR_MISSES = [
    ("ITC.NS", "Nifty stocks switch to defensive mode", False),   # the substring bug
    ("ITC.NS", "Investors switch out of IT", False),
    ("ONGC.NS", "Oil prices rise on supply concerns", False),     # sector, not company
    ("ONGC.NS", "Natural gas output from private fields climbs", False),
    ("AXISBANK.NS", "Banks rally as RBI holds rates", False),     # generic token
    ("COALINDIA.NS", "Coal prices surge in global markets", False),
    ("COALINDIA.NS", "India GDP growth beats estimates", False),
    ("TCS.NS", "IT services hiring slows across the sector", False),
    ("ADANIPORTS.NS", "Adani Enterprises raises funds", False),   # sibling, not this one
    ("ADANIPORTS.NS", "Port traffic at Indian ports rises", False),
    # Deliberately expected to MATCH -- see the accepted trade-off below.
    ("RELIANCE.NS", "Reliance Power arm wins solar order", True),
]

for tk, title, must_match in NEAR_MISSES:
    build_clean()
    seed_articles([(tk, title, TODAY)])
    rr = DI.news_integrity()
    matched = rr.get("relevance_pct") == 100.0
    verb = "accepts" if must_match else "rejects"
    ok = matched == must_match
    check(f"  {tk:<14} {verb}: {title[:36]}", ok,
          "" if ok else
          ("MATCHED, and should not have" if matched
           else "REJECTED, and should not have"))

print()
print("-" * 74)
print("ACCEPTED TRADE-OFF — deliberate, and re-checked so it stays deliberate")
print("-" * 74)
# RELIANCE.NS resolves to words={'reliance'} with NO phrase, so "Reliance Power"
# matches it. That is a decision the source already made and documented: the
# group-token block is lifted only for the company whose entire name IS the
# group name, because blocking it left Reliance Industries with no identifying
# term at all and 17 of its own articles unmatched. The sibling contamination is
# the price paid, knowingly.
#
# The test above pins the CURRENT behaviour rather than an opinion about it, so
# that if the fallback is ever removed this line reports it instead of the
# change passing silently.
print("  RELIANCE.NS matches 'Reliance Power' because its whole name is the")
print("  group name and the bare token is its only identifier. Documented in")
print("  rss_news._identity_terms; the alternative lost 17 of its own articles.")

print()
print("-" * 74)
print("KNOWN DEFECT — found by this audit, not fixed here")
print("-" * 74)

# Declared, not asserted away. `_identity_terms` shortens a multi-word name to
# its first two tokens so "Adani Ports and Special Economic Zone Limited" can be
# found as "Adani Ports". For State Bank of India those two tokens are "state
# bank", which matches every state bank on earth.
#
# This is NOT silently fixed here. Changing the matcher changes which articles
# feed the sentiment factor, which changes scores -- a model input change, and
# the model is frozen. It is reported for a decision instead.
#
# The test asserts the defect STILL EXISTS. If someone fixes it, this line goes
# red and tells them to delete it, which is the opposite of a warning nobody
# reads.
build_clean()
seed_articles([("SBIN.NS", "State Bank of Mauritius opens Mumbai branch", TODAY)])
leaks = DI.news_integrity().get("relevance_pct") == 100.0
KNOWN = [("SBIN matches 'State Bank of <anywhere>'",
          "the two-token name shortening yields the phrase 'state bank'")]
print(f"  [{'still present' if leaks else 'FIXED - remove this block'}] "
      f"{KNOWN[0][0]}")
print(f"      {KNOWN[0][1]}")
print("      mechanism: CONFIRMED.  live incidence: UNMEASURED -- the article")
print("      provenance tables live in production Postgres, not locally.")
check("the known defect is still where the audit says it is", leaks,
      "if this fails the defect is fixed; delete the block")

print()
print("=" * 74)
print("AN UNMEASURABLE CHECK MUST NOT REPORT PASS")
print("=" * 74)

conn = sqlite3.connect(DB)
conn.execute("DROP TABLE bhavcopy_eod")
conn.commit()
conn.close()
r = DI.price_integrity()
check("a missing table reports UNMEASURED, not PASS",
      r["status"] == "UNMEASURED", r["status"])
check("and claims no findings", not r.get("findings"),
      "a check that could not run is not a check that passed")

build_clean()
full = DI.audit()
# The property is "no NUMBER pretending to summarise everything", not "no key
# whose name contains score" -- the explanatory key `no_single_score` is itself
# named that way. So look for a numeric top-level score, which is the thing that
# would actually mislead.
numeric_scores = [k for k, v in full.items()
                  if isinstance(v, (int, float)) and not isinstance(v, bool)
                  and ("score" in k or "health" in k or "grade" in k)]
check("the overall report carries no single health score",
      "no_single_score" in full and not numeric_scores,
      f"numeric scores present: {numeric_scores}" if numeric_scores
      else "components are not commensurable; averaging hides which half broke")
check("the overall verdict is one of PASS/PARTIAL/FAIL",
      full["overall"] in ("PASS", "PARTIAL", "FAIL"), full["overall"])

try:
    os.remove(DB)
except Exception:
    pass

print()
print("=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
