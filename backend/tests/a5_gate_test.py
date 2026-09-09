"""
a5_gate_test.py — the stopping rule must be right before it is trusted.

A5 stops if the archive cannot support the pre-registered test. That decision is
made once, before any performance number exists, so the arithmetic behind it has
to be checked against a synthetic archive whose answer is known by construction
rather than against production, where it cannot be.

The conflation guard is the important one. Raw observations, unique securities,
unique formation dates and effective sample size are four different numbers, and
reporting a big one where a small one belongs is exactly how an underpowered
result gets published as a finding.
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

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "a5_gate_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import a5_gate as G  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def seed(n_days, n_secs, start=date(2015, 1, 1)):
    if os.path.exists(DB):
        os.remove(DB)
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, open REAL,"
                 " high REAL, low REAL, close REAL, volume REAL, isin TEXT,"
                 " PRIMARY KEY (symbol, day))")
    rows, d, made = [], start, 0
    while made < n_days:
        if d.weekday() < 5:
            for k in range(n_secs):
                rows.append((f"S{k}.NS", d.isoformat(), 100.0,
                             f"INE{k:09d}"))
            made += 1
        d += timedelta(days=1)
    conn.executemany("INSERT INTO bhavcopy_eod (symbol, day, close, isin) "
                     "VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return made


print("=" * 72)
print("FORMATION DATES AND WINDOW ARITHMETIC")
print("=" * 72)

seed(600, 5)
r = G.gate()
arch, cnt = r["archive"], r["counts"]
print(f"  archive: {arch['trading_days']} days, {arch['months_spanned']} months,"
      f" {arch['unique_securities_by_isin']} securities")

check("all seeded days are counted", arch["trading_days"] == 600)
check("securities counted by ISIN", arch["unique_securities_by_isin"] == 5)

# 600 trading days, formation needs 252 columns to the left. Month ends at
# index >= 252 qualify; 600 days is ~28.5 months, ~252 days is ~12 months.
n_form = cnt["unique_formation_dates"]
check("formation dates exclude the first ~12 months",
      10 <= arch["months_spanned"] - n_form <= 14,
      f"{arch['months_spanned']} months, {n_form} formations")

w = r["independent_windows"]
check("horizon 1 gives one window per formation month",
      w["1"] == n_form, f"{w['1']} vs {n_form}")
check("horizon 3 gives a third as many", w["3"] == n_form // 3, f"{w['3']}")
check("horizon 6 gives a sixth", w["6"] == n_form // 6, f"{w['6']}")
check("horizon 12 gives a twelfth", w["12"] == n_form // 12, f"{w['12']}")
check("overlapping exclusions are reported",
      r["overlapping_excluded"]["12"] == n_form - w["12"])

print()
print("=" * 72)
print("THE FOUR COUNTS MUST NOT BE CONFLATED")
print("=" * 72)

print(f"  raw observations       {cnt['raw_observations']}")
print(f"  unique securities      {cnt['unique_securities']}")
print(f"  unique formation dates {cnt['unique_formation_dates']}")
print(f"  effective sample size  {cnt['effective_sample_size']}")

check("raw observations exceed formation dates",
      cnt["raw_observations"] > cnt["unique_formation_dates"],
      "5 securities per month means 5x the rows")
check("raw observations are securities x formations",
      cnt["raw_observations"] == 5 * n_form, f"{cnt['raw_observations']}")
check("effective sample is NOT the raw count",
      cnt["effective_sample_size"] != cnt["raw_observations"])
check("effective sample equals the non-overlapping month count",
      cnt["effective_sample_size"] == w["1"])
check("the note spells out why they differ",
      "not a count of experiments" in cnt["note"].lower()
      or "NOT a count of experiments" in cnt["note"])

print()
print("=" * 72)
print("THE STOPPING RULE")
print("=" * 72)

v = r["verdict"]
check("a short archive does not clear the gross requirement",
      v["clears_gross"] is False, f"{v['best_horizon_windows']} windows")
check("the shortfall is reported", v["shortfall_gross"] > 0,
      f"{v['shortfall_gross']}")
check("the shortfall is expressed in years too",
      v["years_of_further_history_needed"] > 0,
      f"{v['years_of_further_history_needed']} yr")
check("net-of-cost is not cleared either", v["clears_net_of_cost"] is False)
check("the net requirement is the larger one",
      r["requirement"]["net_of_cost_windows_required"]
      > r["requirement"]["gross_windows_required"])

# A long archive must clear it, or the gate can never pass.
seed(5200, 3)
r2 = G.gate()
check("a long enough archive DOES clear the gross bar",
      r2["verdict"]["clears_gross"] is True,
      f"{r2['verdict']['best_horizon_windows']} windows")
check("but still fails net-of-cost at 686",
      r2["verdict"]["clears_net_of_cost"] is False,
      f"{r2['verdict']['best_horizon_windows']} of 686")

r3 = G.gate(required=10)
check("the threshold is a parameter, not baked in",
      r3["verdict"]["clears_gross"] is True
      and r3["requirement"]["gross_windows_required"] == 10)

print()
print("=" * 72)
print("SPEC IS READ FROM THE FROZEN MODEL, NOT RESTATED")
print("=" * 72)

import pit_validation as PV  # noqa: E402

s = r["specification"]
check("lookback comes from pit_validation",
      s["lookback_days"] == PV.MOM_LOOKBACK == 252, f"{s['lookback_days']}")
check("skip comes from pit_validation",
      s["skip_days"] == PV.MOM_SKIP == 21, f"{s['skip_days']}")
check("horizons come from pit_validation",
      tuple(s["horizons_months"]) == tuple(PV.HORIZONS), f"{s['horizons_months']}")

import inspect  # noqa: E402

src = inspect.getsource(G)


def _code_only(text):
    """Source with comments and string literals removed.

    The module's own docstring says it computes no Sharpe and no p-value, so a
    plain substring search finds those words in the sentence disclaiming them.
    The claim is about the CODE, so the prose has to go before it is checked.
    """
    import io as _io
    import tokenize as _tk
    out = []
    try:
        for tok in _tk.generate_tokens(_io.StringIO(text).readline):
            if tok.type in (_tk.COMMENT, _tk.STRING):
                continue
            out.append(tok.string)
    except Exception:
        return text
    return " ".join(out)


code = _code_only(src)
check("the gate computes no performance number",
      not any(w in code.lower() for w in ("sharpe", "p_value", "pvalue",
                                          "mean_return", "excess_return")),
      "checked against code with docstrings stripped")
check("the gate writes nothing",
      not any(w in code.upper() for w in ("INSERT ", "UPDATE ", "DELETE ",
                                          "DROP ", "ALTER ")))
check("stripping actually removed the prose",
      "sharpe" in src.lower() and "sharpe" not in code.lower(),
      "otherwise the check above passes for the wrong reason")

try:
    os.remove(DB)
except Exception:
    pass

print()
print("=" * 72)
print("THE STOPPING RULE — FIXED BEFORE THERE IS A RESULT TO WANT")
print("=" * 72)

# 199 protects against testing EARLY. It says nothing about testing REPEATEDLY
# once past it, and that is how this gate would most plausibly be broken: run at
# 199, get p = 0.09, run again at 205, again at 211, write down the first
# p < 0.05. Every step looks disciplined; the false-positive rate is not 5%.
cs = G.confirmatory_status(windows=171)
check("the rule exists and is stated", "exactly once" in G.ANALYSIS_RULE)
check("it names the threshold it fires at", "199" in G.ANALYSIS_RULE)
check("it says a later run is exploratory",
      "exploratory" in G.ANALYSIS_RULE.lower())
check("it records WHEN it was adopted", G.ANALYSIS_RULE_ADOPTED == "2026-09-09")
check("and the count at adoption, so it cannot be backdated",
      G.ANALYSIS_RULE_ADOPTED_AT_WINDOWS == 171,
      "adopted while underpowered and with no result in hand")
check("the rejected alternative is on the record",
      "alpha-spending" in cs.get("rejected_alternative", ""),
      "choosing it later, after a null, would be optional stopping in a suit")

check("below the threshold the test is not due", cs["due_now"] is False)
check("and says so", cs["status"] == "not yet due", cs["status"])
check("at the threshold it becomes due",
      G.confirmatory_status(windows=199)["due_now"] is True)
check("above the threshold it is still due, not overdue-and-skipped",
      G.confirmatory_status(windows=250)["due_now"] is True)
check("it has not been run", cs["already_run"] is False)

seed(600, 3)   # the previous section left the table dropped
check("the gate carries the rule in its payload",
      "stopping_rule" in G.gate(), "so it cannot be read without it")

import inspect as _i  # noqa: E402
_code = _code_only(_i.getsource(G))
check("the gate still computes no performance number",
      not any(w in _code.lower() for w in ("sharpe", "p_value", "pvalue",
                                           "mean_return", "excess_return")))
check("the only write is the schema for the run record",
      "INSERT " not in _code.upper() and "UPDATE " not in _code.upper()
      and "DELETE " not in _code.upper(),
      "CREATE TABLE IF NOT EXISTS only — schema, never a score")

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
