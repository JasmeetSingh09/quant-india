# Data coverage report (2026-10-15)

**Sources.** Existing records only: read-only queries of the production database on 2026-10-15,
plus local files named below. **Nothing was fetched or written. No missing history was estimated
or filled in.**

The report keeps two kinds of coverage apart:
- **point-in-time coverage:** values as they were known on past dates, which is what a historical
  test needs;
- **current-data coverage:** values fetched today for today's score, which cannot test the past.

## 1. Point-in-time history (usable for historical tests)

| Record | Range | Size | Gaps and limits |
|---|---|---|---|
| **NSE end-of-day prices** (`bhavcopy_eod`) | **2011-07-04 to 2026-09-07** | 3,744 trading days; about 6.6 million rows; 1,480 securities on the first day, 2,892 on the last | 217 days recorded as having no file (2011-08-15 to 2026-06-26), last checked 2026-09-08. **No price after 2026-09-07:** collection has been paused since 2026-09-08 under the written request to NSE |
| **Corporate actions** (`corporate_actions`) | Ex-dates 2011-07-04 to 2026-09-21 | Dividends 19,252, all parsed; bonuses 536, all parsed; splits 510, all parsed | **12,778 rows of kind `other`, none parsed.** Rights issues are among them; the rights reparse is a separate write awaiting approval. Last fetch: dividends and bonuses 2026-09-09, splits 2026-10-05 (the approved Yahoo-split fix), other 2026-09-07 |
| GDELT headlines (local, `~/quant_data/gdelt`) | 2019-09-01 to 2026-09-16; **titles only from 2019-09-22** | 5,147 files, 3.5 GB | Matcher precision unmeasured. In the 254-day sample, OIL took 225,686 of 588,558 matches (the common-word leak); 203 of 204 listed names matched |

**Not available point-in-time, and not reconstructed:**
- historical fundamentals (ROE, FCF, P/E, P/B, Piotroski inputs, as published at the time);
- historical shares outstanding, so no historical market capitalisation;
- the historical sector map;
- the app's own historical headlines before 2026-09-03;
- any Nifty total-return series;
- bid-ask or order-book data.

The annual-report pilot is the only route to as-published fundamentals:
- 474 of 1,033 company-years read: **45.9%, against the 80% gate**;
- estimated ceiling with every download 75–78%;
- local `~/quant_data/annual_reports`.

## 2. Forward records (point-in-time from their start date only)

These are stored as they happen. They cover the past only from their first day. They are
**prospective records, not historical tests**.

| Record | First | Latest | Size | Accruing? |
|---|---|---|---|---|
| **Score predictions** (`predictions`) | 2026-07-24 | 2026-10-14 | 130,303 rows; 2,777 stocks; 77 dates | **Yes.** Graded on its pre-set horizon; first read due from 2026-12-27 |
| **Factor history** (`factor_history`) | 2026-08-23 | 2026-10-15 | 120,232 rows; 2,767 stocks; 43 cycles | **Yes** |
| **Headlines and FinBERT labels** (`factor_input_articles`) | Cycle 2026-09-03 | Cycle 2026-10-15 | About 1.0 million rows; 43 cycles | **Yes**, for about 47% of stocks (D-02) |
| **Fundamentals as observed** (`accounts_observed`) | 2026-09-19 | 2026-10-15 | 115,884 rows; 2,647 stocks; 12 fields | **Yes.** This is the only point-in-time fundamentals record, and it starts on 2026-09-19 |
| **NSE prices for a forward momentum window** | — | **2026-09-07** | — | **No.** Nothing is stored after 2026-09-07. No forward momentum test is accruing |

**Correction.** `FACTOR_EVIDENCE_VERDICTS_2026-10-14.md` described a momentum out-of-sample period
as "accruing since 2026-09-07". That is not true while collection is paused, and the wording is
corrected in this commit.

## 3. Current-data coverage (today's score; cannot test the past)

The last complete scan cycle, **2026-10-14**, scanned 2,462 stocks (model `v1.5.0-statement-inputs`).
The 2026-10-15 cycle was still in progress when queried (1,160 rows).

| Factor | Measured | Not measured | What is missing |
|---|---|---|---|
| **Momentum** | 2,290 (93.0%) | 172 (7.0%) | Too little price history: the 12-1 return and volatility are absent for those 172 |
| **Quality** | ROE present for 95.8%, FCF yield for 97.4% | — | ROE missing for 103 stocks, FCF yield for 65 |
| **Value** | Valued for 2,458 of 2,462 | 4 with no measure used | P/E missing for 358 (14.5%, including loss-makers whose P/E is excluded). Sector P/E and P/B missing for 68 (no peers). Peers mostly from the Yahoo-sector fallback (census 2026-10-14: 233 mapped, 2,151 fallback, 77 none) |
| **Sentiment** | 1,158 stocks with stored headlines (47.0%) | The rest: "no news found" | 0 untitled headlines. Sentiment refusals are stored as 0 in `factor_history`, not NULL, so its NULL count (2) understates refusals. The headline count above is the reliable measure |

These describe **today's** inputs, fetched live from Yahoo and news sources. They say nothing about
what the same inputs were in any past month.

## 4. What this means for testing

| Factor | Point-in-time data for a historical test | Status |
|---|---|---|
| Momentum | **Yes**, 2011-07 to 2026-09 | Testable. Net-of-costs pre-registration at revision 3, awaiting approval. Forward window blocked while collection is paused |
| Quality, value | **No.** As-published coverage is 45.9% against an 80% gate; fundamentals observed only since 2026-09-19 | Not testable historically. The forward fundamentals record is accruing |
| Sentiment | Partly: GDELT titles 2019-09-22 to 2026-09-16 (unvalidated matcher); the app's own record only since 2026-09-03 | Testable, insufficient evidence; matcher gate first |
| Composite and labels | No | Forward record only (`predictions`, from 2026-07-24) |

**The last available price date is 2026-09-07.**
