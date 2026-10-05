# Integrity review: what the failing checks actually mean

**2026-10-05. Read-only:** queries against production Postgres and Yahoo; nothing was written.
Source: the live `/health/data-integrity` report. Overall FAIL, with 5 checks failing.

## Summary

| Check | Reported | What it is | Real defect? |
|---|---|---|---|
| News article names its company | 10,369 of 19,751 fail | The check takes names from `nse_stocks`, which is empty on production, so it tests headlines against bare tickers | **No** for the matcher (98.7% name their company); **yes** for the check and for name search |
| One symbol, one security | 549 symbols | A split gives the same company a new ISIN; `security_identity` links them (Step 3A, 35 of 35 verified) | **No** (known false alarm) |
| Corporate action parsed | 12,778 unparsed | 12,207 meetings, demergers, buy-backs; 320 rights; 228 REIT/InvIT distributions; 13 preference-share bonuses; **8 splits and 2 consolidations missed by the parser** | **10 real misses**, plus demergers never adjusted |
| Large overnight move explained | 1,597 unexplained | 1,156 are sub-Rs 2 tick noise in 44 symbols; 72 are funds; actions filed under the other ISIN count as unexplained | **Yes:** missing splits and bonuses, see below |
| Article scored for more than 5 companies | 9 | List headlines ("copper boom stocks") that predate v1.4.3's list rule | Minor |

## The real defect: splits and bonuses missing from the corporate-action data

The checks covered moves of at least 40% between consecutive trading days, from a price of at least
Rs 10, matching an action filed under either ISIN or the symbol.

- **22 moves:** the ISIN changed on the day the price fell, and no action exists. Examples:
  - Bajaj Finance, 2025-06-16, -90%;
  - Kotak Mahindra Bank, 2026-01-14, -80%;
  - Varun Beverages, 2024-09-12, -59%;
  - TD Power, JBM Auto, Dolphin.
- **146 moves:** same ISIN, no action. Real crashes or missing data. Those identified so far:
  - Britannia, 2018-11-29, -49% (a bonus);
  - United Spirits, 2018-06-15, -80% (a split);
  - Alkyl Amines, 2021-05-11, -56%;
  - Tide Water Oil, 2016 and 2021;
  - Godfrey Phillips, 2025.
- **92 moves next to an action the parser did not read.** Examples:
  - Asian Paints, 2013-07-30, -90%: a 1:10 split;
  - Solar Industries, 2016: a split;
  - Siemens, 2025-04-07, -43%: the Siemens Energy demerger;
  - SKF India, 2025: a demerger.

**Effect.** Each missing split or bonus leaves a fake crash in the adjusted price series, which the
point-in-time backtests (momentum, low risk) read as a real return. Large companies are among them.

**Yahoo's split records match most of these exactly** (`Ticker.splits`):

| Company | Date | Yahoo factor |
|---|---|---|
| Kotak | 2026-01-14 | x5 |
| Britannia | 2018-11-29 | x2 |
| Asian Paints | 2013-07-30 | x10 |
| Alkyl Amines | 2021-05-11 | x2.5 |
| Varun Beverages | 2024-09-12 | x2.5 |
| United Spirits (UNITDSPR) | 2018-06-15 | x5 |

Not always, though. Bajaj Finance shows x2 on Yahoo, but its price fell 90% (a 1:2 split plus a
4:1 bonus, a factor of 10). Yahoo misses the bonus.

## Other findings

- **Company names are missing on production.** `stock_universe` reads `nse_stocks` through sqlite3,
  but production keeps its data in Postgres. Search by company name returns nothing ("20 microns"
  finds none) or too little ("reliance" finds only RELIANCE).
- **Rights-entitlement lines (`-RE`)** are short-lived rights, not shares, and some are in the
  price archive. They carry INE ISINs, so the fund exclusion does not catch them.
- **Demergers are not adjusted at all.** Adjusting them needs the value split between the two
  companies, which is not in the data.

## Proposed fixes (need the owner's approval; each writes to production or changes data used by backtests)

1. **Fill missing splits and bonuses.**
   - Use a Yahoo split factor only when it agrees, within 10%, with the jump between consecutive
     prices on that day.
   - Where it disagrees (Bajaj Finance), list the event for entry by hand from the company's own
     filing.
   - Every added row is labelled with its source ("Yahoo, verified against the price jump"), never
     presented as an exchange filing.
   - Teach the parser the wording variants behind the 10 misses.
2. **Re-run the momentum point-in-time backtest on the repaired data**, as a declared data
   correction, reporting the original result and the corrected one side by side. The original
   stays as recorded.
3. **Load company names into production** from the stored NSE list (2,553 names, 2026-08-21; no new
   NSE fetch), and read them through the shared database. This fixes name search and the news check.
4. **Make the integrity checks honest:**
   - news: judge only headlines whose company name is known, and count the rest as unmeasured;
   - big moves: match actions under either linked ISIN, and report tick-size noise, funds and
     rights lines separately.
5. **Leave rights-entitlement lines (`-RE`) out of the scored universe,** like funds.
6. **Record demergers as a known limitation** wherever adjusted prices are shown.
