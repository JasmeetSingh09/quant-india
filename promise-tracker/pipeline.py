#!/usr/bin/env python3
"""Quant India — Promise Ledger pipeline (Wave 1, stage 1).

Implements the contract in CLAUDE.md. Commands:

  extract  <pdf>          PDF -> promises JSON (Anthropic API, model claude-sonnet-4-6)
  verify   <json>         quote-verification pass against the source PDF; updates
                          quote_verified, moves failures to the rejected array,
                          prints the pass rate (the >=95% gate)
  render   <json>         generates the summary MD and scorecard MD
  backfill <TICKER|all>   runs extract+verify over every PDF already present under
                          data/transcripts/<TICKER>/  (launch with history, not one
                          quarter). --force re-runs already-ingested transcripts.
  monitor                 coverage-gap report (local, report-only; no alerts)

The extraction prompt below quotes the CLAUDE.md extraction + verification rules
VERBATIM. If you change the rules in CLAUDE.md, change them here too.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
TRANSCRIPTS = ROOT / "data" / "transcripts"
PROMISES = ROOT / "data" / "promises"
OUTPUT = ROOT / "data" / "output"
STATE_PATH = ROOT / "data" / "coverage_state.json"
COMPANIES_PATH = ROOT / "companies.json"

# Brief specified claude-sonnet-4-6 (verified: current, active model ID).
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000

QUARTER_RE = re.compile(r"(FY\d{2}Q[1-4])", re.IGNORECASE)

# The promise-record fields the model is asked to fill. company / ticker /
# transcript_source / quote_verified / verdict / verdict_evidence are overwritten
# deterministically after extraction, so the model can't get them wrong.
SCHEMA_FIELDS = [
    "company", "ticker", "quarter_of_call", "transcript_source", "speaker",
    "verbatim_quote", "quote_location", "promise_type", "specificity",
    "target_metric", "deadline", "verifiable", "quote_verified", "verdict",
    "verdict_evidence", "extraction_confidence",
]

# ---------------------------------------------------------------------------
# Extraction prompt — rules quoted VERBATIM from CLAUDE.md
# ---------------------------------------------------------------------------

RULES_VERBATIM = """\
## Promise record schema (every extracted item)
{
  "company": "",
  "ticker": "",
  "quarter_of_call": "",
  "transcript_source": "",
  "speaker": "",
  "verbatim_quote": "",
  "quote_location": "",
  "promise_type": "",
  "specificity": "",
  "target_metric": "",
  "deadline": "",
  "verifiable": true,
  "quote_verified": false,
  "verdict": "PENDING",
  "verdict_evidence": "",
  "extraction_confidence": ""
}
Field notes: transcript_source = exact filename. speaker = name +
title as written in transcript. verbatim_quote = EXACT words from
PDF, no paraphrase. quote_location = page number. promise_type =
revenue|margin|capex|expansion|product_launch|debt|revision|other.
specificity = numeric|directional|vague. verdict = PENDING|DELIVERED|
MISSED|PARTIAL|UNVERIFIABLE. extraction_confidence = high|medium|low.

## Extraction rules (NON-NEGOTIABLE)
1. Only checkable claims count. "We are excited about the future"
   = NOT a promise. "We expect double-digit jewellery growth" = promise.
2. Aspirations with a metric or deadline count ("we aim to open
   50 stores this year").
3. Capture hedging inside the quote itself; hedged promises are
   still promises.
4. If management reaffirms/revises PRIOR guidance, promise_type =
   "revision" and note the original in target_metric.
5. NEVER paraphrase or reconstruct a quote. If exact words can't
   be quoted, EXCLUDE the item entirely.
6. Every entry MUST have quote_location. No location = no entry.

## Verification rules (the product IS this step)
1. After extraction, search the source PDF text for each
   verbatim_quote (normalize whitespace only). Found ->
   quote_verified: true. Not found -> move entry to a "rejected"
   array in the same JSON. Report pass rate.
2. Target pass rate >=95%. Below that, tighten the extraction
   prompt -- flag it, don't silently accept.
3. Nothing with quote_verified: false ever appears in scorecards
   or the dashboard.
"""

PROMPT_TEMPLATE = """\
You extract forward-looking management promises from an Indian earnings-call
transcript, following these rules EXACTLY. Facts only; never opinions or advice.

{rules}

Company: {company}  (ticker: {ticker})
Quarter of call: {quarter}
Source filename: {filename}

The transcript follows, with "=== PAGE n ===" markers. Use the page number of the
marker immediately preceding a quote as its quote_location.

Return ONLY a JSON array (no prose, no markdown fences). Each element is one promise
object with exactly the schema fields above. Copy verbatim_quote CHARACTER-FOR-
CHARACTER from the transcript text between the page markers — this is checked against
the source and any quote that isn't found verbatim is rejected. Set quote_verified to
false and verdict to "PENDING" for every item (a later step assigns those). If there
are no qualifying promises, return [].

=== TRANSCRIPT ===
{transcript}
"""

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load_companies() -> dict:
    data = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    return {c["ticker"]: c for c in data["companies"]} | {"_config": data.get("config", {})}


def normalize_ws(text: str) -> str:
    """Collapse every run of whitespace to a single space (whitespace only,
    per verification rule 1). No case-folding, no punctuation changes."""
    return " ".join(text.split())


def read_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    if pdfplumber is None:
        _fail("pdfplumber is not installed. Run: pip install -r requirements.txt")
    pages: list[tuple[int, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            pages.append((i, page.extract_text() or ""))
    return pages


def parse_ticker_and_quarter(pdf_path: Path) -> tuple[str, str]:
    """Ticker from the parent folder (data/transcripts/<TICKER>/...) or the
    filename prefix; quarter from an FYnnQn token in the filename."""
    ticker = pdf_path.parent.name if pdf_path.parent.name not in ("transcripts", "") else pdf_path.stem.split("_")[0]
    ticker = ticker.upper()
    m = QUARTER_RE.search(pdf_path.stem)
    quarter = m.group(1).upper() if m else "UNKNOWN"
    return ticker, quarter


def parse_json_array(text: str) -> list:
    """Parse the model's response into a JSON array, tolerating code fences or
    stray prose around it."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"schema_version": 1, "tickers": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def record_ingest(ticker: str, quarter: str, filename: str) -> None:
    state = load_state()
    t = state["tickers"].setdefault(ticker, {"transcripts": [], "last_results_date": None})
    if quarter not in t["transcripts"]:
        t["transcripts"].append(quarter)
    t["last_transcript_ingested"] = quarter
    t["last_ingested_at"] = _dt.date.today().isoformat()
    t["last_file"] = filename
    save_state(state)


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

def cmd_extract(pdf_arg: str) -> Path:
    pdf_path = Path(pdf_arg)
    if not pdf_path.is_absolute():
        pdf_path = (ROOT / pdf_path).resolve() if not pdf_path.exists() else pdf_path.resolve()
    if not pdf_path.exists():
        _fail(f"PDF not found: {pdf_arg}")

    try:
        import anthropic
    except ImportError:
        _fail("anthropic SDK not installed. Run: pip install -r requirements.txt")

    companies = load_companies()
    ticker, quarter = parse_ticker_and_quarter(pdf_path)
    company = companies.get(ticker, {}).get("name", ticker)

    pages = read_pdf_pages(pdf_path)
    if not any(t.strip() for _, t in pages):
        _fail(f"No extractable text in {pdf_path.name} (scanned PDF? OCR is out of Wave 1 scope).")
    transcript = "\n".join(f"=== PAGE {n} ===\n{t}" for n, t in pages)

    prompt = PROMPT_TEMPLATE.format(
        rules=RULES_VERBATIM, company=company, ticker=ticker,
        quarter=quarter, filename=pdf_path.name, transcript=transcript,
    )

    print(f"extract: {pdf_path.name}  ({ticker} {quarter}, {len(pages)} pages) -> model {MODEL}")
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    resp = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        items = parse_json_array(raw)
    except json.JSONDecodeError as e:
        _fail(f"model did not return valid JSON ({e}). First 400 chars:\n{raw[:400]}")

    # Deterministic overrides — the model can't get these wrong.
    for it in items:
        it["company"] = company
        it["ticker"] = ticker
        it["transcript_source"] = pdf_path.name
        it.setdefault("quarter_of_call", quarter)
        if not it.get("quarter_of_call"):
            it["quarter_of_call"] = quarter
        it["quote_verified"] = False
        it["verdict"] = "PENDING"
        it.setdefault("verdict_evidence", "")
        for f in SCHEMA_FIELDS:
            it.setdefault(f, "")

    doc = {
        "ticker": ticker,
        "company": company,
        "quarter_of_call": quarter,
        "transcript_source": pdf_path.name,
        "pdf_path": str(pdf_path.relative_to(ROOT)) if ROOT in pdf_path.parents else str(pdf_path),
        "extracted_at": _dt.date.today().isoformat(),
        "pass_rate": None,
        "promises": items,
        "rejected": [],
    }
    PROMISES.mkdir(parents=True, exist_ok=True)
    out = PROMISES / f"{ticker}_{quarter}.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    record_ingest(ticker, quarter, pdf_path.name)
    print(f"extract: wrote {len(items)} candidate promise(s) -> {out.relative_to(ROOT)}")
    print("extract: run `verify` next — nothing is trusted until quotes are verified.")
    return out


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def cmd_verify(json_arg: str) -> float:
    json_path = Path(json_arg)
    if not json_path.is_absolute() and not json_path.exists():
        json_path = (ROOT / json_arg)
    if not json_path.exists():
        _fail(f"promises JSON not found: {json_arg}")

    doc = json.loads(json_path.read_text(encoding="utf-8"))
    pdf_rel = doc.get("pdf_path")
    pdf_path = (ROOT / pdf_rel) if pdf_rel and not Path(pdf_rel).is_absolute() else Path(pdf_rel or "")
    if not pdf_path.exists():
        _fail(f"source PDF for verification not found: {pdf_rel} (needed to check quotes).")

    full_norm = normalize_ws("\n".join(t for _, t in read_pdf_pages(pdf_path)))

    # Re-evaluate every entry (promises + previously rejected) so verify is idempotent.
    all_items = list(doc.get("promises", [])) + list(doc.get("rejected", []))
    verified, rejected = [], []
    for it in all_items:
        quote = str(it.get("verbatim_quote", ""))
        has_loc = str(it.get("quote_location", "")).strip() != ""
        found = bool(quote.strip()) and normalize_ws(quote) in full_norm
        if found and has_loc:  # rule 6: no location = no entry
            it["quote_verified"] = True
            verified.append(it)
        else:
            it["quote_verified"] = False
            it.setdefault("reject_reason",
                          "quote not found verbatim" if not found else "missing quote_location")
            rejected.append(it)

    total = len(all_items)
    pass_rate = (len(verified) / total * 100.0) if total else 0.0
    doc["promises"], doc["rejected"] = verified, rejected
    doc["pass_rate"] = round(pass_rate, 1)
    doc["verified_at"] = _dt.date.today().isoformat()
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    gate = "PASS" if pass_rate >= 95.0 else "BELOW GATE"
    print(f"verify: {len(verified)}/{total} quotes verified — pass rate {pass_rate:.1f}%  [{gate}]")
    if pass_rate < 95.0 and total:
        print("verify: pass rate < 95% — tighten the extraction prompt before scaling (CLAUDE.md).")
        for it in rejected:
            print(f"  rejected ({it.get('reject_reason')}): {str(it.get('verbatim_quote',''))[:80]!r}")
    return pass_rate


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def _short(it: dict) -> str:
    return (it.get("target_metric") or it.get("verbatim_quote") or "")[:70]


def cmd_render(json_arg: str) -> None:
    json_path = Path(json_arg) if Path(json_arg).exists() else (ROOT / json_arg)
    if not json_path.exists():
        _fail(f"promises JSON not found: {json_arg}")
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    if doc.get("pass_rate") is None:
        print("render: warning — this file hasn't been verified yet. Run `verify` first.")

    verified = doc.get("promises", [])  # only verified entries live here post-verify
    ticker, company, quarter = doc["ticker"], doc["company"], doc["quarter_of_call"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stem = f"{ticker}_{quarter}"

    # --- scorecard (deterministic table, per CLAUDE.md scorecard spec) ---
    sc = [f"# {company} ({ticker}) — Promise Scorecard: {quarter}", ""]
    sc.append(f"_Source: {doc['transcript_source']} · verified quotes only · "
              f"pass rate {doc.get('pass_rate')}%_")
    sc.append("")
    sc.append("| # | Promise | Verbatim quote | Deadline | Verdict | Evidence | Resolution notes |")
    sc.append("|---|---------|----------------|----------|---------|----------|------------------|")
    for i, it in enumerate(verified, 1):
        q = str(it.get("verbatim_quote", "")).replace("|", "\\|")
        short = _short(it).replace("|", "\\|")
        sc.append(f"| {i} | {short} | {q} | "
                  f"{it.get('deadline','')} | {it.get('verdict','PENDING')} | "
                  f"{it.get('verdict_evidence','')} |  |")
    (OUTPUT / f"{stem}.scorecard.md").write_text("\n".join(sc) + "\n", encoding="utf-8")

    # --- summary (one page, built from verified structured data) ---
    numeric = [it for it in verified if it.get("specificity") == "numeric"]
    revisions = [it for it in verified if it.get("promise_type") == "revision"]
    top5 = (numeric + [it for it in verified if it not in numeric])[:5]
    sm = [f"# {company} ({ticker}) — Call Summary: {quarter}", ""]
    sm.append(f"_Source: {doc['transcript_source']} · {len(verified)} verified promise(s)_")
    sm.append("")
    sm.append("## Top promises")
    for it in top5:
        sm.append(f"- {_short(it)} — deadline: {it.get('deadline') or 'n/a'} "
                  f"({it.get('promise_type','other')}, {it.get('specificity','')})")
    if not top5:
        sm.append("- _None verified for this quarter._")
    sm.append("")
    sm.append("## Guidance revisions")
    if revisions:
        for it in revisions:
            sm.append(f"- {_short(it)} — was: {it.get('target_metric','?')}")
    else:
        sm.append("- _No reaffirmed/revised prior guidance captured._")
    sm.append("")
    sm.append("## Most specific verbatim quotes")
    for it in numeric[:3]:
        sm.append(f"> {it.get('verbatim_quote','')}  \n>  — {it.get('speaker','')} (p.{it.get('quote_location','')})")
    if not numeric:
        sm.append("- _None._")
    sm.append("")
    sm.append("## Headline numbers & tone")
    sm.append("_Not captured by Wave 1 stage-1 extraction (schema is promise-only). "
              "See the open question in the review notes — extend the schema or add a "
              "second summarization pass to populate this._")
    (OUTPUT / f"{stem}.summary.md").write_text("\n".join(sm) + "\n", encoding="utf-8")

    print(f"render: wrote {stem}.summary.md and {stem}.scorecard.md -> {OUTPUT.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------

def cmd_backfill(target: str, force: bool) -> None:
    companies = load_companies()
    tickers = [t for t in companies if t != "_config"] if target.lower() == "all" else [target.upper()]
    for ticker in tickers:
        folder = TRANSCRIPTS / ticker
        pdfs = sorted(folder.glob("*.pdf")) if folder.exists() else []
        if not pdfs:
            print(f"backfill: {ticker} — no PDFs under {folder.relative_to(ROOT)}, skipping")
            continue
        for pdf in pdfs:
            _, quarter = parse_ticker_and_quarter(pdf)
            out = PROMISES / f"{ticker}_{quarter}.json"
            if out.exists() and not force:
                doc = json.loads(out.read_text(encoding="utf-8"))
                if doc.get("pass_rate") is not None:
                    print(f"backfill: {ticker} {quarter} already ingested (pass "
                          f"{doc['pass_rate']}%) — use --force to redo")
                    continue
            out = cmd_extract(str(pdf))
            cmd_verify(str(out))
    print("backfill: done.")


# ---------------------------------------------------------------------------
# monitor  (coverage-gap report — local, report-only)
# ---------------------------------------------------------------------------

def cmd_monitor() -> None:
    companies = load_companies()
    cfg = companies.get("_config", {})
    gap_days = int(cfg.get("gap_alert_days", 15))
    state = load_state()
    today = _dt.date.today()

    print(f"monitor: coverage-gap report (report-only; gap_alert_days={gap_days})")
    print(f"{'TICKER':<12}{'#tx':>4}  {'last quarter':<14}{'last ingested':<14}gap")
    gaps = 0
    for ticker, comp in companies.items():
        if ticker == "_config":
            continue
        t = state["tickers"].get(ticker, {})
        n = len(t.get("transcripts", []))
        last_q = t.get("last_transcript_ingested", "-")
        last_at = t.get("last_ingested_at", "-")
        flag = ""
        if n == 0:
            flag, gaps = "NO TRANSCRIPTS", gaps + 1
        else:
            # If a results date was recorded (manual in Wave 1; auto-fetch is a later
            # wave), flag when it's older than gap_alert_days with nothing ingested since.
            rd = t.get("last_results_date")
            if rd:
                try:
                    days = (today - _dt.date.fromisoformat(rd)).days
                    if days > gap_days and (last_at == "-" or last_at < rd):
                        flag, gaps = f"RESULTS {days}d AGO, NO TX", gaps + 1
                except ValueError:
                    pass
        print(f"{ticker:<12}{n:>4}  {last_q:<14}{last_at:<14}{flag}")
    print(f"monitor: {gaps} coverage gap(s). "
          "Note: results dates are manual in Wave 1 (BSE/NSE auto-fetch is a later wave).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Quant India - Promise Ledger pipeline (Wave 1).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="PDF -> promises JSON")
    pe.add_argument("pdf")

    pv = sub.add_parser("verify", help="quote-verification pass")
    pv.add_argument("json")

    pr = sub.add_parser("render", help="summary MD + scorecard MD")
    pr.add_argument("json")

    pb = sub.add_parser("backfill", help="extract+verify over a ticker's folder")
    pb.add_argument("target", help="TICKER or 'all'")
    pb.add_argument("--force", action="store_true", help="re-run already-ingested transcripts")

    sub.add_parser("monitor", help="coverage-gap report")

    args = p.parse_args(argv)
    if args.cmd == "extract":
        cmd_extract(args.pdf)
    elif args.cmd == "verify":
        cmd_verify(args.json)
    elif args.cmd == "render":
        cmd_render(args.json)
    elif args.cmd == "backfill":
        cmd_backfill(args.target, args.force)
    elif args.cmd == "monitor":
        cmd_monitor()


if __name__ == "__main__":
    main()
