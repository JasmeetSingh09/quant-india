# Quant India — Promise Ledger (Wave 1 MVP)

## Mission
Build India's Financial Memory: a pipeline that extracts every
forward-looking management promise from Indian earnings call
transcripts, verifies quotes against source PDFs, tracks promises
to outcomes, and publishes receipt-backed Guidance Reliability
scorecards. Facts only, never buy/sell recommendations.

## Wave 1 scope (DO NOT build beyond this)
- 20 companies (10 large caps, 10 mid caps), latest quarter first,
  then multi-year backfill
- Pipeline: PDF in → promises JSON + summary MD + scorecard MD out
- Quote verification pass (mandatory, see Rules)
- Simple local dashboard (single HTML file) that renders the
  scoreboard from the JSON files
- NO user accounts, NO deployment, NO alerts, NO memory search,
  NO knowledge graph. Those are later waves.

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
   verbatim_quote (normalize whitespace only). Found →
   quote_verified: true. Not found → move entry to a "rejected"
   array in the same JSON. Report pass rate.
2. Target pass rate ≥95%. Below that, tighten the extraction
   prompt — flag it, don't silently accept.
3. Nothing with quote_verified: false ever appears in scorecards
   or the dashboard.

## Summary spec (one .md per transcript)
One page: top 5 promises (one line each with deadline); guidance
revisions (reaffirmed/raised/lowered/quietly dropped vs prior
quarters); 3 most interesting verbatim quotes.

Wave 1, stage 1 is **promise-only**: the schema captures promises,
not reported financials or Q&A tone, so "headline numbers as
management presented them" and "tone notes (what was emphasized /
dodged)" are left as honestly-blank sections with a note. Populating
them (a schema extension or a second summarization pass) is a
later-wave feature — it must not block the >=95% accuracy work.

## Scorecard spec (one .md per transcript)
Table: # | Promise (short) | Verbatim quote | Deadline | Verdict |
Evidence | Resolution notes.
New promises start PENDING. Verdicts are only assigned by comparing
against published results, never guessed.

## Dashboard spec (single self-contained HTML, vanilla JS)
Reads all promises JSONs. Shows: company list with promise counts
and (once verdicts exist) reliability score = (DELIVERED +
0.5*PARTIAL) / total non-pending verifiable promises, plus a
specificity index (share of promises that are numeric). Click a
company → full promise table with quotes. Clean, minimal,
screenshot-friendly. Links to source filings; never rehosts PDFs.

## Engineering rules
- Python 3.12+, minimal deps (pypdf/pdfplumber, anthropic SDK).
- API key from env var ANTHROPIC_API_KEY, never hardcoded.
- Idempotent: re-running skips already-verified transcripts unless
  --force.
- Every stage prints a clear report (counts, pass rates, rejects).
- Git commit after each working stage.

### Additions agreed in build review (backfill + coverage monitor)
- `backfill <TICKER|all>` command: runs extract + verify over every
  PDF already present under `data/transcripts/<TICKER>/`, so Wave 1
  launches with `config.backfill_years` of history, not one quarter.
  No new extraction logic — it loops the existing extract+verify and
  respects idempotency (`--force` to re-run). This is the "latest
  quarter first, then multi-year backfill" line above, made runnable.
- `monitor` command (coverage-gap monitor): a LOCAL printed report,
  not an alerting system. For each company, if results were reported
  but no transcript has been ingested within `config.gap_alert_days`,
  it lists the gap so ingestion never breaks silently. Reads/writes
  `data/coverage_state.json`. Kept report-only to stay inside the
  "NO alerts" Wave 1 scope — no notifications, no deployment.
- Auto-fetching transcripts from BSE/NSE is explicitly OUT of Wave 1
  (later wave). `monitor` only reports gaps in what's already on disk.

## What "done" means for Wave 1, stage 1
One transcript (Titan) → verified JSON with ≥95% quote pass rate +
summary + scorecard + visible in dashboard. One company, one
quarter, fully through. Everything else follows from that.
