# Proposal v1.6.1: correct the sector map that picks valuation peers

**Status: DRAFT, awaiting owner decision. Nothing is implemented.** The current map stays in force
until this is approved. Audit defect D-01 (`docs/AUDIT_FOUR_FACTOR_2026-10-14.md`).

## The problem

**How peers are chosen.** The value factor (15% of V1) compares a stock's P/E and P/B with up to
three sector peers. The peers come from `data_fetcher.NSE_SECTORS`: the first five other members of
the first sector that lists the stock, of which `_compute_value_factor` uses the first three.

**What is wrong with the map:**
- **Wrong sectors.** Kalyan Jewellers (KALYANKJIL) and Edelweiss Financial Services (EDELWEISS) are
  listed under Steel_Metal, so both are valued against Tata Steel, JSW Steel and SAIL. Keynote
  Financial Services (KEYFINSERV) is listed under Real_Estate.
- **Stocks in two sectors.** KALYANKJIL (Steel_Metal and Consumer_Durables), ADANIGREEN (Power and
  Infra) and ADANIENT (Infra and Diversified). The first listing wins for the stock itself, but the
  second listing still makes it a peer for other members of that sector.
- **The map is not in the frozen specification.** `strategy_version.current_spec()` does not capture
  it, so editing it today would not move the spec hash, and the drift check would not see it.

## Evidence (reproduced, not estimated)

**Data and method:**
- Production cycle 2026-10-14, read-only.
- Each score was recomputed with the methodology's value formula from the multiples the scan stored
  (`factor_inputs`, `factor_input_peers`).
- **Check on the method:** using the current peers, the recomputation reproduces the stored value
  score for 11 of 12 stocks exactly. KEYFINSERV is off by 0.008, because peer multiples were
  re-fetched at slightly different times during the night.
- **Alpha after** = stored alpha + 15 × (value after − value before). Value is the only factor that
  moves.

**Independent sector check.** Yahoo's `.info` fetched on 2026-10-14:

| Stock | Yahoo industry | Agrees with the move? |
|---|---|---|
| KALYANKJIL | Consumer Cyclical / Luxury Goods | yes |
| EDELWEISS | Financial Services / Financial Conglomerates | yes |
| KEYFINSERV | Financial Services / Capital Markets | yes |
| ADANIGREEN | Utilities / Utilities – Renewable | yes |
| ADANIENT | Energy / Thermal Coal | n/a (a conglomerate) |

The NSE's own industry classification should be confirmed by hand by the owner. The app does not
fetch from nseindia.com.

## The change (option A, recommended)

**Rule.** Each stock is in exactly one sector. A stock in two sectors keeps the sector that applies
to it today (the first match), so its own peers do not change, and its second listing is removed.

| Stock | Today | Proposed | Why |
|---|---|---|---|
| KALYANKJIL | Steel_Metal (effective) and Consumer_Durables | Consumer_Durables only | jeweller; peers TITAN, WHIRLPOOL, BATAINDIA |
| EDELWEISS | Steel_Metal | NBFC, appended last | financial conglomerate; peers BAJFINANCE, BAJAJFINSV, MUTHOOTFIN |
| KEYFINSERV | Real_Estate | NBFC, appended last | capital-markets firm; the map's closest group |
| ADANIGREEN | Power (effective) and Infra | Power only | renewable utility |
| ADANIENT | Infra (effective) and Diversified | Infra only | keeps its current own sector |

**Why "appended last".** Adding to the end of NBFC changes no existing NBFC member's peers. Those
peers are drawn from the first five names, and NBFC already has 13.

**Option B (not costed).** Put ADANIENT in Diversified as a conglomerate and remove it from Infra.
That changes ADANIENT's own peers and every Infra member's. Choose it only with a separate impact
run.

## Impact on the 2026-10-14 cycle (option A)

| Stock | Why it moves | Value before → after | Alpha before → after | Label |
|---|---|---|---|---|
| KALYANKJIL | steel → consumer peers (P/E mean 15.9 → 54.0) | −0.9997 → +0.3458 | 8.35 → **28.53** | **Neutral → Buy** |
| ADANIENT | ADANIGREEN (P/E 123.7) leaves its peers (mean 58.6 → 20.1) | +0.1547 → −0.7805 | 13.81 → **−0.22** | Neutral |
| EDELWEISS | steel → NBFC peers | −0.3791 → +0.3180 | 15.92 → 26.38 | Buy |
| ADANIPORTS | loses ADANIGREEN as a peer | +0.2766 → −0.3705 | 30.33 → 20.62 | Buy |
| GODREJIND | loses ADANIENT as a peer | +0.0999 → −0.4262 | −9.87 → **−17.76** | **Neutral → Sell** |
| TATAINVEST | loses ADANIENT as a peer | −0.9194 → −0.4067 | −32.08 → −24.39 | Sell |
| KEYFINSERV | real estate → NBFC peers | +0.8784 → +0.4840 | 6.35 → 0.56 | Neutral |
| IRB | loses ADANIGREEN | +0.5783 → +0.3248 | 5.93 → 2.13 | Neutral |
| KNRCON | loses ADANIGREEN | +0.6559 → +0.8218 | −9.61 → −7.12 | Neutral |
| JSWHL | loses ADANIENT | −0.0112 → +0.0637 | −14.99 → −13.87 | Neutral |
| BAJAJHLDNG | loses ADANIENT | +0.5234 → +0.4810 | 10.75 → 10.11 | Neutral |
| GPPL | loses ADANIGREEN | +0.4999 → +0.4851 | 24.27 → 24.05 | Buy |

**Scope of the change:**
- 12 stocks change; 2 labels change (KALYANKJIL, GODREJIND).
- No other stock is affected:
  - Stocks outside the map take peers from the first five names of a mapped sector, and none of the
    moved stocks is among the first five of Steel_Metal, Real_Estate or Power.
  - Infra and Diversified are never used as fallback groups.
- **Rankings:** KALYANKJIL and GODREJIND move within their cap tiers. Other ranks move only by the
  score changes above.
- **Approximation:** for KNRCON and JSWHL, peer multiples not stored as peer rows were taken from the
  peer's own stored inputs, where a negative multiple had already been dropped.

## What also changes, and what does not

**Also changes:**
- **The spec captures the map.** `current_spec()` records a hash of `NSE_SECTORS` (and its version),
  so any future edit is visible to the drift check. Today it is not captured at all.
- **Stored rows are stamped.** `universe_scan.MODEL_VERSION` is bumped, so rows scored on the new map
  are distinguishable.

**Does not change:** weights, formulas, thresholds, the peer count, the fallback averages, and the
other three factors.

**Separate:** D-06, negative peer multiples entering the mean, is a separate decision and not part of
this proposal.

## Tests

**New checks:**
- One sector per mapped stock (oracle U02).
- Kalyan's and Edelweiss's peers (U03, U04).
- The spec hash changes when the map changes.

**Unchanged:** every other oracle, behavioural and CI check must stay unchanged. The behavioural
snapshots do not use the map.

**Proof the change does what it claims:** a before/after run on one stored cycle must reproduce the
table above.

## Version, deploy and rollback

**Version: v1.6.1.** This is a data correction to V1 that does change scores. v1.7.0 is reserved for
the pending 52-week-high proposal; if that is approved first, renumber this one.

**Order of steps:**
1. Owner approval.
2. Code, tests and the spec capture.
3. Deploy outside 00:02–03:00 UTC, with no backfill running.
4. Freeze v1.6.1.
5. Verify the first scan against the table.

**Rollback:** revert the commit and redeploy; the spec returns to v1.6.0. Rows scored under v1.6.1
keep their stamp, so they can be excluded from any study.

**Research records.** Factor history from before the change keeps the old peers. Any study spanning
the change must say so, or use one side only.

## Decision needed

1. **Approve option A, choose option B, or reject.**
2. **KEYFINSERV:** confirm NBFC as its group, or remove it from the map. Removing it means Yahoo's
   "Financial Services" sends it to Banking peers, a worse fit.
