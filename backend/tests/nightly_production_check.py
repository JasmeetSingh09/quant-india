"""
nightly_production_check.py — did last night's scan go the way it should?

Run by .github/workflows/nightly.yml at 03:30 UTC, about an hour after the scan
normally finishes. It answers five questions, and exits 1 if any answer is bad,
saying which and why:

  1. Did tonight's scan run and finish?
  2. Did the number of failures jump? 4 on 2026-09-10 became 72 on 2026-09-11,
     and nothing reported it.
  3. Are dozens of stocks that were scoring failing night after night? The
     scan's "no market data" error also fires when Yahoo's info lookup fails on
     the server, which is our problem, not the stocks'. On 2026-09-11 and 12, 71
     stocks that had scored every night failed together while Yahoo priced them
     from another machine. The universe filter no longer excludes such stocks,
     so without this check the problem would be silent.
  4. Does the Portfolio Lab audit still pass against production?
  5. Were the night's scores built on the company data they need? On
     2026-09-12 the value factor scored for 84 of 2,573 stocks while every
     other check passed, because each missing input had a recorded reason.

Read-only. Questions 1-3 are GET requests. The Portfolio Lab audit sends
compute-only POSTs; the one endpoint that records advice, /portfolio/advise,
is not among them.

    python backend/tests/nightly_production_check.py
    python backend/tests/nightly_production_check.py --skip-portfolio-lab
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("QUANT_INDIA_API", "https://quant-india.onrender.com")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORTFOLIO_LAB_AUDIT = os.path.join(ROOT, "docs", "step5_portfolio_lab_audit.py")

# A jump must be large in both senses: 2 -> 7 is noise, 4 -> 72 is not.
JUMP_FACTOR = 3
JUMP_MIN_EXTRA = 50
# Previously-scoring stocks one night from exclusion that count as an outage.
# A handful is the filter finding newly dead tickers; dozens at once is not.
AT_RISK_ALERT = 10
# Fundamentals coverage, from /scan/provenance-gap. On 2026-09-09 and 10 the
# value factor scored for 95% of stocks and ROE was missing for 15%; on 09-12
# it was 3% and 98%. The lines sit well clear of a normal night and well short
# of the nights that went wrong.
VALUE_SCORED_MIN_PCT = 85.0
QUALITY_INPUT_MISSING_MAX_PCT = 25.0


def _names(tickers, n=5):
    return ", ".join(str(t).replace(".NS", "") for t in (tickers or [])[:n])


def _unreadable(payload, what):
    if not isinstance(payload, dict) or "error" in payload:
        return f"{what} could not be read: {str(payload)[:160]}"
    if payload.get("status") == "UNMEASURED":
        return f"{what} is UNMEASURED: {payload.get('reason')}"
    return None


def judge_scan(status, today):
    """Reasons tonight's scan is not a finished pass for `today`. Empty is good."""
    bad = _unreadable(status, "the scan status")
    if bad:
        return [bad]
    reasons = []
    cycle = str(status.get("cycle") or "")[:10]
    if cycle != today:
        reasons.append(f"no scan cycle for {today}; the latest is {cycle or 'none'}")
    if status.get("running"):
        reasons.append(f"the scan is still running (started {status.get('started_at')})")
    else:
        if not status.get("finished_at"):
            reasons.append("the scan is not running and has no finish time")
        done, total = status.get("done"), status.get("total")
        if isinstance(done, int) and isinstance(total, int) and done < total:
            reasons.append(f"the scan stopped after {done:,} of {total:,} tickers")
    return reasons


def judge_jump(failures):
    bad = _unreadable(failures, "the scan failure audit")
    if bad:
        return [bad]
    st = failures.get("stability_vs_previous_cycle")
    if not isinstance(st, dict):
        return ["there is no previous cycle to compare tonight's failures with"]
    then, now = int(st.get("failed_then") or 0), int(st.get("failed_now") or 0)
    if now > max(JUMP_FACTOR * then, then + JUMP_MIN_EXTRA):
        new = _names(st.get("new_today"))
        return [f"failures jumped from {then} to {now} since {st.get('previous_cycle')}"
                + (f"; new tonight include {new}" if new else "")]
    return []


def judge_at_risk(failures):
    bad = _unreadable(failures, "the scan failure audit")
    if bad:
        return [bad]
    ar = failures.get("at_risk_of_exclusion")
    if (not isinstance(ar, dict) or ar.get("status") == "UNMEASURED"
            or not isinstance(ar.get("previously_scored"), int)):
        why = ar.get("reason") if isinstance(ar, dict) else "the field is absent"
        return [f"the early warning for the universe filter is unavailable: {why}"]
    # Stocks whose latest attempt found a short price history and no market cap
    # are the source being short of a real company, not an outage: on 2026-09-14,
    # 47 of them, Yahoo's history restarting 2026-08-17. Only the rest count.
    n = ar.get("previously_scored_unexplained")
    examples = ar.get("examples_previously_scored_unexplained")
    if not isinstance(n, int):          # a deploy from before the split
        n, examples = ar["previously_scored"], ar.get("examples_previously_scored")
    if n >= AT_RISK_ALERT:
        short = ar.get("previously_scored_short_history")
        return [f"{n} stocks that scored in the last 60 days found no market data on each "
                f"of their last 2 attempts"
                + (f", not counting {short} with too little price history at the source"
                   if isinstance(short, int) and short else "")
                + f". The filter will not exclude them, but this many at once is a data "
                  f"problem on our side, not delisting; e.g. {_names(examples)}"]
    return []


def judge_fundamentals(coverage):
    """Reasons the night's scores were built on too little company data. Empty is good."""
    if not isinstance(coverage, dict) or "error" in coverage:
        return [f"the fundamentals coverage report could not be read: {str(coverage)[:160]}"]
    if coverage.get("status") == "UNMEASURED" or coverage.get("available") is False:
        return [f"the fundamentals coverage report is unavailable: {coverage.get('reason')}"]
    total = (coverage.get("observations") or {}).get("total") or 0
    factors = coverage.get("factors") or {}
    value = factors.get("value") or {}
    reasons = []
    pct = value.get("scored_pct")
    if not isinstance(pct, (int, float)):
        reasons.append("the fundamentals coverage report has no figure for the value factor")
    elif pct < VALUE_SCORED_MIN_PCT:
        reasons.append(f"the value factor scored for only {value.get('scored') or 0:,} of "
                       f"{total:,} stocks ({pct:.0f}%, line {VALUE_SCORED_MIN_PCT:.0f}%); "
                       f"the rest were scored without it")
    for m in (factors.get("quality") or {}).get("missing_by_input") or []:
        if m.get("input") == "roe" and (m.get("pct_of_scored") or 0) > QUALITY_INPUT_MISSING_MAX_PCT:
            reasons.append(f"ROE was missing for {m['pct_of_scored']:.0f}% of stocks "
                           f"(line {QUALITY_INPUT_MISSING_MAX_PCT:.0f}%), so those quality "
                           f"scores rest on fewer inputs")
    return reasons


def judge_portfolio_lab(exit_code):
    return [] if exit_code == 0 else [
        f"the Portfolio Lab audit failed against production (exit {exit_code})"]


def fetch(path, timeout=300, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(BASE + path,
                                         headers={"User-Agent": "quant-india-nightly"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            if attempt < tries - 1:
                time.sleep(20 * (attempt + 1))
    return {"error": last}


def run_portfolio_lab():
    # Without this the scan summary printed above sat in Python's buffer while
    # the audit wrote straight to the log, so on GitHub it appeared after it.
    sys.stdout.flush()
    return subprocess.run([sys.executable, PORTFOLIO_LAB_AUDIT], cwd=ROOT).returncode


def run_checks(get=fetch, portfolio_lab=run_portfolio_lab, today=None, out=print):
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = get("/alpha/universe/status")
    failures = get("/health/data-integrity?domain=scan_failures")
    cycle = str(status.get("cycle") or today)[:10] if isinstance(status, dict) else today
    coverage = get(f"/scan/provenance-gap?cycle={cycle}")

    out(f"Production: {BASE}   date (UTC): {today}")
    if isinstance(status, dict) and "error" not in status:
        out(f"  scan: cycle {status.get('cycle')}, {status.get('progress_note')}, "
            f"excluded as unpriceable {status.get('excluded_no_market_data')}")
    if isinstance(failures, dict) and "error" not in failures:
        st = failures.get("stability_vs_previous_cycle") or {}
        ar = failures.get("at_risk_of_exclusion") or {}
        out(f"  failures: {st.get('failed_then')} in {st.get('previous_cycle')}, "
            f"{st.get('failed_now')} in {failures.get('cycle')}")
        if isinstance(ar.get("previously_scored"), int):
            names = _names(ar.get("examples_previously_scored"))
            out(f"  one night from exclusion: {ar['previously_scored']} that were scoring"
                + (f" ({names})" if names else "")
                + (f", of which {ar['previously_scored_short_history']} have too little "
                   f"price history at the source"
                   if isinstance(ar.get("previously_scored_short_history"), int) else "")
                + f", {ar.get('never_scored')} never priceable")
    if isinstance(coverage, dict) and coverage.get("factors"):
        v = coverage["factors"].get("value") or {}
        roe = next((m.get("pct_of_scored") for m in
                    (coverage["factors"].get("quality") or {}).get("missing_by_input") or []
                    if m.get("input") == "roe"), None)
        out(f"  fundamentals: value factor scored for {v.get('scored_pct')}% of stocks, "
            f"ROE missing for {roe}%")

    rows = [("Tonight's scan ran and finished", judge_scan(status, today)),
            ("Scan failures did not jump", judge_jump(failures)),
            ("No run of failures among stocks that were scoring", judge_at_risk(failures)),
            ("Scores were built on the company data they need", judge_fundamentals(coverage))]
    if portfolio_lab is not None:
        out("\nPortfolio Lab audit against production:")
        rows.append(("Portfolio Lab audit passes on production",
                     judge_portfolio_lab(portfolio_lab())))

    out("")
    failed = False
    for name, reasons in rows:
        out(f"[{'FAIL' if reasons else 'PASS'}] {name}")
        for r in reasons:
            out(f"       {r}")
        failed = failed or bool(reasons)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Nightly production check, {today}\n\n| Check | Result |\n|---|---|\n")
            for name, reasons in rows:
                fh.write(f"| {name} | {'**FAIL**: ' + '; '.join(reasons) if reasons else 'pass'} |\n")
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-portfolio-lab", action="store_true",
                    help="only the scan checks (about a minute instead of about six)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return run_checks(portfolio_lab=None if args.skip_portfolio_lab else run_portfolio_lab)


if __name__ == "__main__":
    sys.exit(main())
