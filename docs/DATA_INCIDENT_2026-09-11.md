# Data incident: company data missing from the nightly scan, from 2026-09-11

**Status:** open. Recorded 2026-09-13. The machine-readable list of affected
cycles is `docs/degraded_cycles.json`.

## What happened

Each nightly scan asks Yahoo for each stock's company information: market cap,
P/E, P/B, ROE, free cash flow. From the 2026-09-11 scan, a growing share of those
requests came back empty or incomplete *during the scan*. Where they did, the
value factor could not score and the quality factor fell back to fewer inputs.
The scan still finished, and every missing input was recorded with a reason, so
the scan's own audit passed each night.

| Scan cycle | Stocks scored | Value factor scored | ROE missing | Valuation peers found | No-market-data failures |
|---|---:|---:|---:|---:|---:|
| 2026-09-09 | 2,704 | 2,575 (95%) | 15% | 2,318 | — |
| 2026-09-10 | 2,706 | 2,577 (95%) | 15% | 2,320 | 4 |
| **2026-09-11** | 2,635 | **1,365 (52%)** | 53% | 1,248 | 72 |
| **2026-09-12** | 2,573 | **84 (3%)** | 98% | 84 | 135 |
| **2026-09-13** | 2,656 | **1,533 (58%)** | 48% | 1,399 | 107 |

Source: `GET /scan/provenance-gap?cycle=…` and `GET /health/data-integrity?domain=scan_failures`
on production.

## What it affected

- **Published scores, signals and cap tiers** for 2026-09-11 to 13. A stock
  missing company data was scored on momentum, sentiment and whatever quality
  inputs remained, and one missing market cap dropped out of the tier rankings.
- **The daily prediction snapshots** for those three dates. They are sealed by a
  hash chain (`prediction_seals`) and have **not** been changed. An analysis of
  the track record should exclude or separately report these snapshot dates when
  it judges the value or quality factors or the composite score.
- **Momentum** (price history) and the **Piotroski inputs** (financial
  statements) were not affected.
- 71 stocks that had been scoring would have been dropped from the scan for a
  week by the universe filter. That was prevented on 2026-09-12 (`4773fe7`).

## What is known about the cause

- The lookup works outside the scan. On 2026-09-13 at 20:1x UTC, production's
  `/stock/metrics` returned full company information for AKCAPIT, RELIANCE and
  AADHARHFC in under 1.5 seconds each.
- It is **not** a library update: `requirements.txt` last changed 2026-09-08, and
  no yfinance or curl_cffi release was published between the good and bad nights.
- It is **not** a change to the lookup or the scan's pacing: `_ticker_info` last
  changed in July, the scan's worker count in August, and every `alpha_model.py`
  change predates the healthy 2026-09-10 scan.
- The worst night was also the fastest scan (2h05m, against 2h25m–2h48m), which
  suggests Yahoo refused requests quickly rather than letting them time out.
- The bad nights followed days with several deploys. That is a correlation, not
  a demonstrated cause.
- `alpha_model._ticker_info` caches any non-empty payload for 24 hours, while
  `data_fetcher._info_looks_complete` exists precisely because Yahoo returns
  truncated payloads under load. A truncated payload cached during the scan
  would stay for the rest of the day. Likely a contributor; not yet proven.

## Fixes

| | Change | Status |
|---|---|---|
| Filter guard | A stock that scored in the last 60 days is never excluded | Shipped 2026-09-12 (`4773fe7`) |
| A | Nightly check goes red when value or ROE coverage collapses (value under 85% of stocks, or ROE missing for over 25%) | Built and tested; not yet deployed |
| B | Inside the scan, retry company-info lookups that come back empty, truncated or timed out (waits of 2 s then 5 s); keep a truncated payload for 10 minutes, not 24 hours. Outside the scan a lookup still asks once | Built and tested; not yet deployed |
| E | This record and `degraded_cycles.json` | This commit |
| D | Don't publish a scan whose fundamentals coverage collapsed | Proposed; decide after B has run |

## Also found, not changed

`alpha_model._fetch_info_once` (formerly the body of `_ticker_info`) runs the
lookup in a one-thread executor and waits 6 seconds for it. Leaving that
executor's `with` block waits for the thread to finish, so a lookup that hangs
still holds the scan worker until it returns. The timeout decides what the
scan *uses*, not how long it *waits*. Worth fixing on its own; it was left out
of B to keep that change narrow.
