# Proposal v1.6.1: correct the sector map that picks valuation peers

**Superseded for decision purposes by `docs/PEER_METHODOLOGY_DECISION_2026-10-14.md`** (owner, 2026-10-14: prioritise a universe-wide methodology over isolated sector corrections).
That document corrects revision 2's census: 2,151 fallback stocks, not 479/440/376/226 peer-set
counts. Of the 78 stocks without peer rows, 64 are distress judgements that never use peers.

**Status: DRAFT, revision 2. Nothing in the map is implemented.** Audit defect D-01
(`docs/AUDIT_FOUR_FACTOR_2026-10-14.md`).

**Owner decisions on revision 1 (2026-10-14):**
- **Options A and B:** not approved as final classifications.
- **The map:** stays unchanged. Adani Enterprises keeps its current classification until a
  classification rule and an authoritative source are documented.
- **Keynote Financial:** cost a dedicated capital-markets sector before placing it.
- **Configuration:** capture the peer counts and the fallback table with the map.
- **Deployment:** not authorised.

Revision 2 does exactly that, and finds that the larger problem is the fallback table, not the
handful of map entries (section "The larger problem").

The queries are in `research/sector_map_costing_2026-10-14.sql`. Yahoo's classification of the
candidates is in `docs/audit/capital_markets_candidates_yahoo_2026-10-14.json`.

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
- **Check on the method:** using each stock's own stored peer rows, the recomputation reproduces
  the stored value score exactly for all 12 stocks, KEYFINSERV included (0.8700).
- **Where revision 1's KEYFINSERV gap came from (0.008):** it read a peer's multiples off another
  stock's peer rows. During one night's scan DLF, GODREJPROP and OBEROIRLTY were each read with two
  different P/Es (about 2.5% apart), because Yahoo data was re-fetched mid-scan. So within one cycle,
  different stocks can be compared against slightly different values for the same peer. That is a
  reproducibility limitation of live fetching, recorded rather than fixed here.
- **"After" figures** use each new peer's own stored multiples.
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

**Option B (costed 2026-10-14 by the same method).** ADANIENT moves to Diversified as a
conglomerate and comes out of Infra. ADANIGREEN also comes out of Infra, as in option A. The
Diversified members keep ADANIENT as a peer, so they do not move.

| Stock | Value before → after | Alpha before → after | Label |
|---|---|---|---|
| ADANIPORTS | +0.2766 → −0.8145 (Infra P/E mean 63.0 → 15.2) | 30.33 → **13.96** | **Buy → Neutral** |
| ADANIENT | +0.1547 → −0.4867 (peers BAJAJHLDNG, TATAINVEST, GODREJIND) | 13.81 → 4.19 | Neutral |
| GPPL | +0.4999 → −0.0373 | 24.27 → 16.21 | Buy |
| IRB | +0.5783 → +0.0795 | 5.93 → −1.55 | Neutral |
| KNRCON | +0.6559 → +0.7847 | −9.61 → −7.68 | Neutral |

KALYANKJIL, EDELWEISS and KEYFINSERV change exactly as in option A.

**A against B:**

| | Option A | Option B |
|---|---|---|
| Stocks that change | 12 | 8 |
| Labels that flip | KALYANKJIL Neutral → Buy; GODREJIND Neutral → Sell | KALYANKJIL Neutral → Buy; ADANIPORTS Buy → Neutral |
| ADANIENT's own peers | unchanged (it stays where it is scored today) | it moves to holding companies |
| Infra's peer pool | keeps one Adani conglomerate | ports and roads only |
| Not shown in the impact table | — | ADANIGREEN's own peers stay Power, so it does not move |

What to weigh:
- **Option A** keeps ADANIENT's own valuation basis.
- **Option B** treats it as a conglomerate. That matches Yahoo's view that it is not infrastructure
  (Energy / Thermal Coal), but compares it with holding companies whose P/Es are high.
- **Neither is established by this evidence.** It is a classification judgement for the owner.

**KEYFINSERV choices:**

| Choice | Peers | Value | Alpha |
|---|---|---|---|
| Today (Real_Estate) | DLF, GODREJPROP, OBEROIRLTY | +0.8784 | 6.35 |
| NBFC, appended (proposed) | BAJFINANCE, BAJAJFINSV, MUTHOOTFIN (lenders) | +0.4840 | 0.56 |
| Removed from the map | falls back to Yahoo "Financial Services" → Banking: HDFCBANK, ICICIBANK, SBIN | −0.3131 | −11.40 |

Neither group is a true peer for a capital-markets firm. A dedicated capital-markets sector would
need its own membership list. That is outside this proposal and not costed.

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

## Spec capture: done separately, map unchanged

The spec gap was fixed on its own, at the owner's request, ahead of the map decision. The commit is
local and not pushed.

**What `current_spec()` now records** as `sector_map`:
- the sector order (the first match wins);
- every sector's members, in order;
- a hash of both.

**Test:** `tests/sector_map_spec_test.py` (7 checks, in CI) shows the capture matches the module, and
that removing a member, reordering a sector, or reordering the sectors each moves the hash.

**Drift against v1.6.0.** Once deployed, the drift check reports `sector_map` as "never captured by
this version" (coverage), not as behavioural drift. That is accurate: v1.6.0's hash never protected
the map.

**Still not captured:**
- the peer counts, which are inline literals: `peers[:5]` in `get_sector_peers` and `peers[:3]` in
  `_compute_value_factor`;
- the Yahoo-sector fallback table inside `get_sector_peers`.

They belong in the same version as the map change.

## What also changes, and what does not

**Also changes (the first item is already done, separately; see above):**
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

## Revision 2: the larger problem is the fallback table

**Who every scored stock is valued against tonight** (query 2 in the SQL file):

| Peers used | Stocks | How they got there |
|---|---|---|
| BHEL, LT, SIEMENS | 479 | Yahoo "Industrials" → Capital_Goods |
| M&M, MARUTI, TMPV | 440 | Yahoo "Consumer Cyclical" → Auto (jewellers, hotels, textiles, retailers) |
| JSWSTEEL, SAIL, TATASTEEL | 376 | Yahoo "Basic Materials" → Steel_Metal (chemicals, paper, fertilisers) |
| HDFCBANK, ICICIBANK, SBIN | 226 | Yahoo "Financial Services" → Banking (brokers, AMCs, NBFCs, insurers) |
| INFY, TCS, WIPRO | 185 | "Technology" → IT |
| CIPLA, DRREDDY, SUNPHARMA | 172 | "Healthcare" → Pharma |
| HINDUNILVR, ITC, NESTLEIND | 165 | "Consumer Defensive" → FMCG |
| DLF, GODREJPROP, OBEROIRLTY | 92 | "Real Estate" |
| none (market averages) | 78 | no usable peers |
| the rest | ~250 | mapped sectors |

About 2,230 of the 2,462 scored stocks are not in `NSE_SECTORS` (which lists 236) at all. Each takes its peers from the
**three largest companies** of one of 11 broad Yahoo sectors. So the value factor for most of the
universe answers "cheap compared with three mega-caps in a broad sector", not "cheap against
sector peers" as the methodology describes it.

**This is a specification issue.** The methodology document does say "sector peers come from
today's sector map", and the code does exactly that. But the peer groups do not deliver the
comparison the methodology describes. Correcting KALYANKJIL or EDELWEISS in the map alone would leave
this untouched.

## Revision 2: a dedicated capital-markets sector, costed

**Membership screen:**
- All 2,462 scored stocks were screened by company name (`security_names`) for capital-markets
  terms, plus 12 named firms the screen cannot catch (ANGELONE, BSE, CAMS, KFINTECH and others):
  120 candidates.
- Each candidate's Yahoo sector and industry were fetched on 2026-10-14.
- This is a screen, not a universe-wide classification. The app stores no industry for any stock.

**Candidate rule:** Yahoo industry = "Capital Markets". That gives 49 stocks.

**Ordering:** members in descending stored market cap, so each member's peers are the three largest
other members, the same structural rule every sector uses. The top four are GROWW, MOTILALOFS, AIIL
and ANGELONE.

| Measure | Result |
|---|---|
| Members | 49 |
| Their peers today | HDFCBANK, ICICIBANK, SBIN for 48; DLF, GODREJPROP, OBEROIRLTY for KEYFINSERV |
| Peer availability | every member has at least 2 peers with a P/E; 0 fall back to market averages |
| Value moves of 0.05 or more | 39 |
| Mean change in alpha | 8.50 points |
| Direction | 38 rise, 11 fall: large banks make brokers look expensive |
| Labels that flip | 12 (8 Neutral → Buy, 4 Sell → Neutral) |
| Effect on other stocks | none: the members come from the fallback, not from any mapped sector's first five, apart from KEYFINSERV, which must leave Real_Estate, where it is 10th and never anyone's peer |
| KEYFINSERV | alpha 6.35 → **1.76** (value 0.87 → 0.56), against GROWW, MOTILALOFS, AIIL |

The 12 flips: ARYAMAN, IIFLCAPS, SGFIN, ANGELONE, GEOJITFSL, SMCGLOBAL, SHARDUL and HYBRIDFIN go
Neutral → Buy; ARIHANTCAP, 5PAISA, EMKAY and INVENTURE go Sell → Neutral.

**The candidate rule is not clean.** Yahoo's "Capital Markets" includes:
- investment-holding companies: DHUNINV, NAHARCAP, WELINV, SUMMITSEC, MASKINVEST;
- AIIL (Authum Investment), which is the third-largest member and therefore a peer for nearly every
  member;
- IEX, a power exchange.

Yahoo also splits AMCs ("Asset Management", 21 names, which itself includes holding companies) and
exchanges, depositories and rating agencies ("Financial Data & Stock Exchanges": BSE, MCX, CRISIL,
ICRA, CARERATING) into other industries. An authoritative classification is needed before any
membership is fixed.

## Revision 2: what a sound rule needs (proposed for the owner)

1. **An authoritative classification for every scored stock, not a hand list.**
   - The natural source is the NSE's own industry classification (macro-economic sector, sector,
     industry, basic industry).
   - The app must not fetch from nseindia.com, so the file has to be supplied by the owner and
     versioned in the repo.
   - Yahoo's industry is useful as a cross-check, not as the source: the noise above shows why.
2. **One documented level of that classification defines a peer group**, for example basic
   industry, falling back to industry when the group is too small. The fallback must be stated, not
   discovered.
3. **Multi-business companies** (ADANIENT, BAJAJHLDNG and others) take the classification the source
   assigns. The source settles placement, not the score outcome.
4. **Peer choice within a group.** Today it is the first three in list order, which in practice
   means the three largest, so a small broker is valued against Groww. Whether peers should instead
   be nearest in size is a methodology change and needs its own costing.
5. **Too few valid peers.** The owner suggested reporting value as not measured rather than using
   the 22 ± 8 and 3.2 ± 1.5 market averages. Tonight 78 stocks have no peers and 80 use the P/E
   average. This is a methodology change, separate from classification, and not costed here.
6. **Within-cycle reproducibility.** A peer's multiples can differ between stocks in the same cycle
   (see KEYFINSERV above). Reading each peer once per cycle would make peer groups consistent. This
   is an operational change, not costed.

## Revision 2: the three configuration elements are now captured

Done locally, not pushed, with no score change. They are in the frozen-spec field `sector_map`:
- **the map:** sector order and members in order;
- **the peer counts:** `data_fetcher.SECTOR_PEER_FETCH_LIMIT` = 5 and
  `alpha_model.VALUE_PEERS_USED` = 3;
- **the fallback table:** `data_fetcher.YAHOO_SECTOR_FALLBACK`, 11 entries.

The literals were promoted to named constants unchanged.

**Evidence:**
- `sector_map_spec_test.py`: 15 checks. Any change to any of the three moves the hash, and
  `get_sector_peers` still returns the same peer lists.
- Behavioural snapshots: 339/339 identical.
- `run_ci`: 68/68.
- `version_provenance_audit`: 103/103.

**A related gap, reported and not changed.** That audit's literal scan covers only momentum, the
composite and V2. It never inspects `_compute_quality_factor`, `_compute_value_factor` or
`_compute_sentiment_factor`. Their constants are not captured by the frozen spec, including:
- value's 22 ± 8 and 3.2 ± 1.5 averages, the spread floors, the −0.6/−0.4 weights and the distress
  −0.5/0.6;
- quality's 0.4/0.4/0.2 weights, the 12% ± 8% and 3.5% ± 4% references, and the penalties.

V1.4's precedent (promote to named constants, prove identity with recorded outputs, freeze) would
close it. That is a separate approval.

## Decision needed (revision 2)

Nothing here asks for a classification choice yet. In order:
1. **The classification source.** Will you supply the NSE industry classification file, or name
   another authoritative source?
2. **The rule.** Which level of that classification defines a peer group, with which fallback?
3. **Scope.** Does this version fix the fallback for the whole universe (about 2,230 stocks), or
   only the mis-mapped names? Fixing only the names leaves the larger problem in place.
4. **Separate decisions:** "not measured" for too few peers, peer choice by size, and closing the
   quality/value constant gap.

Once the source and rule are chosen, every affected stock is re-costed with the SQL file before
any approval. Options A and B above are kept for the record. They are not proposals any more.
