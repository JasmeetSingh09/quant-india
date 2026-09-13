# The NSE collection pause did not cover the equity list download

**Found:** 2026-09-13. **Fixed:** in the commit that adds this record.

## The commitment

On 2026-09-08 a written request went to NSE Data and Analytics asking permission,
as a Non-Commercial User, to collect and retain published NSE data. It states:
"We have paused further collection pending your response."

`backend/modules/nse_access.py` enforces that. Its docstring lists what the pause
stops: "the nightly bhavcopy fetch, the recent gap repair, the backwards resume
walk, corporate action months and **the equity list download**."

## The gap

Only `bhavcopy.py` (five entry points) and `corporate_actions.py` (`fetch_month`)
ever called `collection_paused()`. `stock_universe.refresh_nse_stocks` did not.
Whenever its stored list was more than 24 hours old it:

1. visited `https://www.nseindia.com` to obtain session cookies;
2. downloaded `https://archives.nseindia.com/content/equities/EQUITY_L.csv`
   (falling back to `nsearchives.nseindia.com`).

It runs at every server start (`main.py`, `ensure_universe_loaded`) and from
`POST /stock/universe/refresh`, which forces it and requires no sign-in.

`nse_collection_pause_test.py` did not catch it. Its tripwire replaced only
`requests.get`, and this function downloads through a `requests.Session`, which
never calls `requests.get`.

## Evidence

Production's log for 2026-09-13, supplied from the Render dashboard:

```
11:35:21  Application startup complete.
11:35:26  File "/app/modules/stock_universe.py", line 554, in ensure_universe_loaded
              nse_result = refresh_nse_stocks()
          File "/app/modules/stock_universe.py", line 180, in refresh_nse_stocks
              conn.execute("DELETE FROM nse_stocks")
          sqlite3.OperationalError: database is locked
```

Line 180 is reached only after both requests above have succeeded and the CSV
has been parsed, so NSE was contacted at that startup. No deploy happened at
11:35; Render restarted the server on its own. The server was using about
1.6 GB of its 2 GB at 20:33 UTC the same day, so memory pressure is a likely
reason.

## Why it repeated

After the download, the write failed with "database is locked", so the list's
`last_updated` never moved. The list therefore stayed more than 24 hours old,
and every later start downloaded it again. This probably also explains why
production's `nse_stocks` table was found empty during Step 3.

## How many times

**Unknown.** Every server start since 2026-09-08 whose list was stale: each
deploy and each restart Render made on its own. Render's logs are the only record
and should be searched for `refresh_nse_stocks` or `NSE stock universe refreshed`.
The deploy of `eeb073a` (pushed 2026-09-13 20:33 UTC, before this fix) may have
added one more if its restart happened before this fix went live.

## The fix

- `refresh_nse_stocks` checks `collection_paused()` before any request. While
  paused it returns the standard `paused_result`, keeps the stored list and
  fetches nothing, forced or not. The endpoint and the startup call both go
  through it.
- `nse_collection_pause_test.py` places its tripwire under `requests.Session`,
  so every requests call is covered. Before the fix its new checks failed and
  recorded exactly the three NSE URLs above; the BSE list, which the commitment
  does not cover, still refreshes.

## Not fixed here

- The "database is locked" failure that stops the list ever updating. Harmless
  while paused (nothing is downloaded); it matters again when collection resumes.
- The memory pressure that probably caused the unplanned restart.
