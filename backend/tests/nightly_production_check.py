"""
nightly_production_check.py — did last night's scan go the way it should?

Run by .github/workflows/nightly.yml at 03:30 UTC, about an hour after the scan
normally finishes. It answers four questions, and exits 1 if any answer is bad,
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
    if ar["previously_scored"] >= AT_RISK_ALERT:
        return [f"{ar['previously_scored']} stocks that scored in the last 60 days found no "
                f"market data on each of their last 2 attempts. The filter will not exclude "
                f"them, but this many at once is a data problem on our side, not delisting; "
                f"e.g. {_names(ar.get('examples_previously_scored'))}"]
    return []


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
    return subprocess.run([sys.executable, PORTFOLIO_LAB_AUDIT], cwd=ROOT).returncode


def run_checks(get=fetch, portfolio_lab=run_portfolio_lab, today=None, out=print):
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = get("/alpha/universe/status")
    failures = get("/health/data-integrity?domain=scan_failures")

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
                + f", {ar.get('never_scored')} never priceable")

    rows = [("Tonight's scan ran and finished", judge_scan(status, today)),
            ("Scan failures did not jump", judge_jump(failures)),
            ("No run of failures among stocks that were scoring", judge_at_risk(failures))]
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
