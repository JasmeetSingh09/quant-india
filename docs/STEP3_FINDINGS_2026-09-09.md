# Step 3 — Production Data Integrity: findings and what they mean

Companion to `STEP3_PRODUCTION_AUDIT_2026-09-09.md`, which is generated
mechanically from the endpoint responses (also archived here as `*.json`).
That file is the evidence. This file is the reading of it, including the
places where the audit itself was wrong.

- **Snapshot (UTC):** 2026-09-09T10:36:10Z
- **Target:** production Postgres via the read-only endpoint
  `/health/data-integrity`
- **Mode:** read-only throughout. No production row was created, altered,
  repaired, backfilled, normalised or deleted. V1.4 untouched.

## Does the evidence support "production data integrity audited"?

**Partly. Two domains are genuinely audited. Two produced findings that need a
follow-up query before they mean anything. One is retracted. One cannot be
audited at all.**

| Domain | Reported | What it actually supports |
|---|---|---|
| `prices` | PASS | **Audited.** Clean, on the full archive. |
| `missing_data` | PASS | **Audited.** Clean, on the full current cycle. |
| `continuity` | FAIL | **Finding needs refinement** — the check counts resumptions after suspension as overnight moves. |
| `identity` | FAIL | **Check premise wrong** — in India a stock split mints a new ISIN, so "one symbol, several ISINs" is normal. |
| `news` | FAIL | **Relevance figure RETRACTED** — it measured the audit's own broken name lookup. The over-shared-article finding stands. |
| `fundamentals_pit` | FAIL/PARTIAL | **Cannot be audited.** No PIT fundamentals exist. The unparsed-actions finding is real. |

So: "audit machinery validated" is fully supported (109/109 synthetic tests).
"Production data integrity audited" is supported **for prices and missing
data**, and not yet for the rest.

---

## 1. Prices — PASS, and this is the headline

**6,598,053 rows · 4,253 securities · 3,744 trading days · 2011-07-04 to
2026-09-07 · 96.2s.**

All nine checks returned zero defects: close present, OHLC present, close
positive, high >= low, close inside its own high-low range, volume not
negative, ISIN present, nothing dated in the future, no duplicate (symbol, day).

The row count matches the expected 6.6M archive exactly, so `examined` is a
measurement and not an aspiration.

**The ISIN question is settled.** 0 of 6,598,053 rows lack an ISIN — 100%
coverage. The local dev sample's 26,816 missing were rows fetched before the
ISIN feature landed, and that gap correctly did **not** extrapolate to
production. The corporate-action join has full identity coverage to work with.

## 2. Missing data — PASS

**70,576 input rows · 4 factors · 2,704 securities · 0 unexplained.**

| factor | recorded | present | genuine zero | flagged missing | refused | unexplained |
|---|---|---|---|---|---|---|
| momentum | 16,354 | 15,964 | 8 | 390 | 130 | 0 |
| quality | 18,928 | 18,153 | 277 | 775 | 0 | 0 |
| sentiment | 10,829 | 10,803 | 2,704 | 26 | 13 | 0 |
| value | 24,465 | — | — | — | — | 0 |

Every absent value is either flagged or explained. Zero unexplained across all
four factors. This is the check that matters — a missing input with a reason is
a limitation, one without is a defect — and there are none.

Worth noting rather than failing: sentiment's 2,704 genuine zeros is exactly one
per security, which is a per-security baseline input, not 2,704 coincidences.

## 3. Continuity — FAIL, but the count is not yet a defect count

**6,593,800 day-over-day steps examined. 2,233 moves of 40% or more: 566
explained by a corporate action within 3 days, 1,667 not.**

Calendar coverage is excellent: exactly **one** gap longer than 5 days in
fifteen years (2014-10-01 to 2014-10-07, 6 days — a holiday cluster).

The 1,667 is **not** 1,667 corrupt rows, for two reasons.

**(a) The check counts resumptions as overnight moves.** `LAG` returns the
previous *stored* day. A security suspended for three years and then resumed
appears here as a single enormous "overnight" jump, and neither price is wrong —
the two observations are simply not adjacent in time. The top offenders are
+9,933% (KAUSHALYA), +5,600% (WINSOME), +4,072% (MBECL). NSE circuit filters
make a genuine +9,933% overnight move impossible, which is the signature of a
resumption or a consolidation, not of a bad price.

*Fixed and tested, not yet deployed:* the check now carries `LAG(day)` as well
as `LAG(close)` and excludes moves whose neighbours are more than 10 days apart,
reporting those separately as resumptions rather than dropping them or calling
them corruption.

**(b) 38.8% of corporate actions cannot explain anything** — see section 5.
Many of the 1,667 may be explained by actions that are stored but unparsed.

**Status: the real unexplained-move count is unknown until the check is re-run
with both corrections.**

### Rerun after the correction (deployed 2026-09-09T12:52Z)

| | |
|---|---|
| day-over-day steps examined | 6,593,800 |
| large moves (>=40%) total | 2,233 |
| — adjacent (neighbours <=10 days apart) | 2,163 |
| — resumptions after a long silence | 70, now excluded |
| of the 2,163: explained by a corporate action | 566 |
| of the 2,163: not explained | **1,597** |

The correction did what it should. Every absurd outlier was a resumption and is
now classified as one rather than counted as a defect: WINSOME +5,600% after
1,404 days silent, ARIHANT +2,188% after 1,537 days, MBECL +4,072% after 704.

**The remaining 1,597 are still NOT called defects**, and the new offender list
shows why. After the extremes are removed the top entries are +267% and +191%,
then repeated *exact* +100.0% values — KSERASERA on 2020-03-24, 2020-03-27 and
2020-04-13. An exact doubling recurring on separate days is the signature of a
**sub-rupee stock moving one tick**: at Rs 0.05 a single Rs 0.05 tick is +100%.
That is the price grid, not corruption, and a percentage threshold is the wrong
instrument at that price level.

Two accounting gaps also remain open:

- 12,778 of 32,964 corporate actions (38.8%) are unparsed and so can explain
  nothing;
- 1,458 of 4,342 ISINs have no corporate action on record at all (coverage is
  2,884 ISINs).

Until both are accounted for, the honest statement is that the true unexplained
count is **unknown, and bounded above by 1,597**.

## 4. Identity — the merge check passes; the reuse check has a wrong premise

**6,598,053 rows · 4,253 symbols · 4,342 distinct ISINs · 162.4s.**

- `one ISIN trades under one symbol on any given day` — **PASS, 0 of
  6,598,053.** No accidental merges anywhere in fifteen years. This is a real,
  clean result.
- `one symbol means one security` — 549 of 4,253 symbols carry multiple ISINs.

**That second finding is a false positive of the check's premise.** The named
symbols are JBMA (4 ISINs), ASTRAL, AJANTPHARM, ALKYLAMINE, AMRUTANJAN,
APCOTEXIND (3 each) — well-known companies that never changed identity. In the
Indian market a **face-value change (a stock split) causes NSDL to issue a new
ISIN for the same company**. So "one symbol, several ISINs" over fifteen years
is the ordinary signature of a company that has split its stock, not ticker
reuse. The check treated the two as identical.

Also noted: several entries in the rename list (`INF109K012R6`, `INF346A01034`,
`INF109KA1962`) carry the **INF** prefix — mutual-fund and ETF units, not
equities (INE = equity).

### The question this raises, which matters more than the finding

Corporate actions are joined to prices **on ISIN**. If a split mints a new ISIN,
then pre-split price rows carry the *old* ISIN while the split action may be
recorded under the *new* one. The adjustment would then fail to apply to exactly
the rows that need it — a material defect in the adjustment layer, not a
cosmetic one.

This is a **hypothesis, not a finding.** It needs one targeted query: for a
symbol with an ISIN transition, does `corporate_actions` hold the split under
the old ISIN, the new one, or both? Until that is answered, the correctness of
the adjusted price series for split-affected securities is **unverified**.

## 5. Fundamentals / PIT — the absence is the finding

**No point-in-time fundamentals table exists.** Valuation and quality inputs are
fetched live from Yahoo at scoring time, which returns each statement as it
reads *today*, not as it read on the date being scored.

Consequence, stated plainly: **no backtest using the value or quality factors
can claim to be point-in-time.** Only the price and corporate-action layer is
PIT. This is not a failure to measure — it is a measurement of an absence, and
it bounds what any historical result can honestly claim.

What *does* exist was measured:

- **32,964 corporate actions**, covering **2,884 ISINs**, ex-dates spanning
  **2011-07-04 to 2026-09-21**. All 32,964 carry an ISIN (0 defects).
- 13 announced future ex-dates — legitimate, counted not failed.
- **481,419 factor inputs**, all carrying an observation time, none observed in
  the future (0 defects on both).

**Real defect: 12,778 of 32,964 corporate actions (38.8%) were never parsed
into a multiplier.** They are stored, visible, and have no effect on any price.
This bears directly on section 3 and on the adjustment layer generally.

Coverage gap worth noting: corporate actions cover 2,884 ISINs, while the price
archive holds 4,342 distinct ISINs. 1,458 ISINs have no corporate action on
record — some legitimately (never had one), some possibly not.

## 6. News — one figure retracted, one finding stands

### RETRACTED: the 39.3% relevance figure

The audit reported 18,024 of 29,710 scored articles as off-topic. **This is an
artifact of the audit, not a property of production.**

The audit resolved company names through `stock_universe.get_stock_by_symbol`,
which reads a **SQLite** table. `/stock/universe/stats` returns `{"nse":
{"count": 0}}` — **the table is empty in production**, so `/stock/search`
returns `"company_name": "20MICRONS"`, the bare symbol, with a null ISIN. The
audit therefore fell back to bare tokens for every ticker, and the token
`20microns` cannot match the headline `"20 Microns Q1 FY27 Results Preview"` —
an article plainly about that company, which the audit flagged as off-topic.

Production scoring does **not** use that path. It resolves the name from
yfinance `longName` (`news.py:399`), which returns "20 Microns Limited". So
production's matcher had the correct identity and the audit's did not.

**Production news relevance is UNMEASURED.** It is not 39.3%, and this audit
provides no evidence against the 100% precision measured when the matcher was
fixed on 2026-09-03.

### Real finding: `nse_stocks` is empty in production

`{"nse": {"count": 0, "last_updated": null}, "bse": {"count": 0}}`. This is a
genuine production defect with visible consequences — `/stock/search` shows bare
symbols instead of company names, and any code path depending on the universe
table gets no name, ISIN or sector. It is consistent with the outstanding
`QUANT_DATA_DIR` task: the SQLite file lives inside the container image and is
destroyed on every redeploy.

### Real finding: market-wide stories are scored as company news

This check does **not** depend on name resolution — it counts how many distinct
tickers share an identical stored headline — so it survives the retraction.

**148 headlines were each scored for more than 5 companies**, out of 24,499
distinct titles. 1,758 titles are shared by more than one security.

- `"market wrap: bel, hul, icici bank, axis bank"` — **135 companies**
- `"market trading guide: data patterns among fo"` — 134 companies
- `"ahead of market: 10 things that will decide"` — 129 companies
- `"nifty september futures trade at premium"` — 128 companies
- `"demat additions surge to 3.3 mn as ipo boom"` — 119 companies

This is the documented 2026-09-03 failure mode, still present. A structural
cause is visible in `rss_news.get_rss_stock_news`: the Google News search results
(step 1) are added **without** passing through the `_mentions` relevance gate —
only the general-market-feed results (step 2) are filtered.

### The SBIN "state bank" leak: mechanism confirmed, incidence zero

Measured, not assumed: **0 articles** in the 2026-09-09 cycle match "state bank"
without "state bank of india". The mechanism is confirmed and unfixed by design
(changing the matcher changes sentiment inputs while V1.4 is frozen), but its
live incidence in this cycle is **zero**.

---

## Synthetic test status

**109 assertions, 109 passed.** Every check is verified by injecting its defect,
confirming it fires, repairing the data, and confirming it clears. The suite
also asserts that `examined` counts are real and do not shrink when a defect is
present, and it pins two behaviours deliberately: the RELIANCE group-token
match (an accepted trade-off) and the SBIN leak (asserted to still exist, so a
fix cannot land silently).

## Confirmed defects

1. **12,778 of 32,964 corporate actions unparsed** (38.8%) — stored, no effect
   on any price.
2. **`nse_stocks` empty in production** — no company names, ISINs or sectors
   from the universe table; `/stock/search` degraded.
3. **148 headlines each scored for >5 companies**, up to 135 — market-wide
   stories entering company sentiment; step 1 of the news fetch is unfiltered.

## Legitimate limitations (not defects)

- No PIT fundamentals exist; only prices and corporate actions are PIT.
- One 6-day calendar gap in 2014 (holiday cluster).
- 13 future-dated corporate-action ex-dates (announced actions).
- Renames: one ISIN under several symbols is normal and is reported, not failed.

## Unresolved / needs a follow-up query

- Whether corporate actions for split-affected securities are keyed to the old
  or new ISIN. **This determines whether adjusted prices are correct for those
  securities.** Highest priority.
- The true unexplained large-move count, after excluding resumptions and after
  the unparsed actions are resolved.
- Production news relevance, which requires the audit to resolve names the way
  production does.

## Unmeasured

- Historical fundamentals PIT — impossible, no data exists.
- News relevance — audit defect, see above.

## Overall

**No single data-health score, by design.** A duplicate price row and an
undated article are not the same unit; averaging them would hide which half is
broken.

The price archive — the foundation everything else rests on — is clean on all
6,598,053 rows. The current scoring cycle has zero unexplained missing inputs.
Beyond that, three real defects are confirmed, one significant question about
the adjustment layer is open, and two of my own checks needed correcting before
their numbers meant anything.
