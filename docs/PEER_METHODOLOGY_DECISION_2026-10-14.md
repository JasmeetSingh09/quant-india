# Value-factor peer methodology: decision document (2026-10-14)

**Status:** for owner decision. Nothing is implemented, nothing is deployed, and the current map,
fallback and formula are unchanged.

**What this replaces.** It supersedes the classification choices in
`PROPOSAL_V161_SECTOR_MAP_2026-10-14.md`, whose options A and B the owner did not approve.

**How to reproduce it.** Every number comes from `research/sector_map_costing_2026-10-14.sql`, which
is read-only, against production cycle 2026-10-14. The inputs are fingerprinted (query 6):

| Table | Rows | md5 |
|---|---|---|
| alpha_scan2 | 2,491 | `df7c3957b6155540cc8cbeec9f611763` |
| factor_inputs (value) | 22,162 | `a062761bb3e64f77af3aa9ad79d626e5` |
| factor_input_peers | 7,152 | `c0ee393d7c70cf549836386697ac7e44` |

These rows are written once per cycle and not rewritten. A re-run that reproduces the fingerprints
is reading the same inputs.

## 1. What the methodology says and what the code does

**The methodology** (`PHASE0_V1_METHODOLOGY_2026-09-14.md`) describes value as P/E and P/B
"compared with up to 3 sector peers".

**The code:**
1. If the stock is in the hand-written `NSE_SECTORS`, its peers are the first 3 other members of the
   first sector listing it.
2. Otherwise, Yahoo's sector for the stock is mapped through an 11-entry table to one of ours, and
   its peers are that sector's first 3 members.
3. If neither applies, the stock gets no peers and the market averages 22 ± 8 and 3.2 ± 1.5 are
   used.

## 2. Census: how every scored stock was valued (query 4)

| Peer source | Stocks |
|---|---|
| Hand-written map (`NSE_SECTORS`, 236 listed) | 234 |
| Yahoo fallback: Industrials → Capital_Goods (BHEL, LT, SIEMENS) | 470 |
| Yahoo fallback: Consumer Cyclical → Auto (M&M, MARUTI, TMPV) | 425 |
| Yahoo fallback: Basic Materials → Steel_Metal (JSWSTEEL, SAIL, TATASTEEL) | 367 |
| Yahoo fallback: Financial Services → Banking (HDFCBANK, ICICIBANK, SBIN) | 210 |
| Yahoo fallback: Technology → IT | 169 |
| Yahoo fallback: Healthcare → Pharma | 153 |
| Yahoo fallback: Consumer Defensive → FMCG | 151 |
| Yahoo fallback: Real Estate | 85 |
| Yahoo fallback: Communication Services → Telecom | 66 |
| Yahoo fallback: Utilities → Power | 28 |
| Yahoo fallback: Energy → Oil_Gas | 27 |
| No peer comparison: 64 distress (both multiples ≤ 0, scored −0.5), 4 refused, 9 on market averages | 77 |
| **Total scored** | **2,462** |

**What the census shows:**
- **Most stocks use the fallback.** 2,151 stocks (87%) take their peers through the fallback, and
  every one of them is compared with the three largest names of a broad Yahoo sector.
- **Corrections to earlier figures.** Revision 2 of the proposal gave 479/440/376/226 and "78 with no
  peers". Those were peer-set counts that included mapped members, and the "78" was mostly distress
  cases that never use peers.
- **Status.** This is a methodology-validity question, not a data defect: the code does what it is
  written to do, but the comparison it produces is not the one the methodology describes.

## 3. Classification source: requirements, and what is known

| Requirement | NSE industry classification | Yahoo `sector` / `industry` |
|---|---|---|
| Authority | The exchange's own (macro sector → sector → industry → basic industry) | A data vendor's |
| Coverage of our 2,462 | Expected to cover every NSE equity; **unverified here** | Fetched for 120 candidates only; not stored for the universe |
| Licensing and terms | **Unknown: the owner must check** | Use governed by Yahoo's terms; the app already depends on it |
| Update frequency | **Unknown: the owner must check** | Changes without notice |
| Access from the app | Not allowed (the app must not fetch nseindia.com); a file would be supplied by the owner and versioned in the repo | Already fetched live |
| Quality seen so far | — | Noisy: "Capital Markets" includes investment-holding firms and a power exchange (IEX) |

**Recommendation:** NSE's classification as the source, supplied as a versioned file, with Yahoo
industry as a cross-check only. A disagreement between them is listed, not resolved silently.

## 4. Candidate rules (written before any of section 5 was computed)

These are to be judged on definition, not on what they do to scores.

| Element | Rule R (recommended for owner review) |
|---|---|
| Peer group | Stocks sharing the source's **basic industry**. |
| Small groups | Fewer than *k* valid peers in the basic industry: widen to **industry**, then stop. No wider fallback. *k* = 3 proposed, matching today's three peers. |
| Insufficient peers | After widening, still fewer than 2 valid peers for a multiple: that multiple is **not measured**. Neither multiple measured: value is **not measured**, with the reason "too few classified peers". No market-average substitute. |
| Valid peer | Has the multiple and it is positive. This also settles D-06: a negative peer multiple is excluded, the same rule as the stock's own. |
| Conglomerates | Take the source's classification. Not decided by score impact. |
| Peer choice within a group | Kept as today's structure (the first 3 by a stated deterministic order), with the order defined as market cap descending, ties broken by ticker. "Nearest in size" is a separate methodology choice and not part of rule R. |
| Missing data | A missing own multiple: that leg is not measured. This differs from today, where it sits at the peer mean (inventory item L2). Owner decision. |
| Within-cycle consistency | Each peer's multiples are read once per cycle and reused. Today the same peer can carry two values in one night (DLF, GODREJPROP and OBEROIRLTY on 2026-10-14). |
| Determinism | Same inputs, same peers, same order. Covered by a test. |

## 5. Costing (sections 3–4 fixed first; source-independent alternatives only)

**What can and cannot be costed now.** Rule R cannot be costed until the classification file exists,
because no industry is stored for the universe. Two alternatives that need no source can be costed
now (query 5). Under the methodology, a not-measured factor contributes 0 and the weights are not
rescaled; coverage falls by 0.15 × the value confidence; tiers keep their 0.3 coverage floor.

| | Status quo | Alt 2: no value without a classified group (fallback removed) | Alt 3: no value when no multiple has ≥ 2 valid peers |
|---|---|---|---|
| Stocks whose value becomes not measured | 0 | 2,160 (the 2,151 fallback + 9 on market averages; the 64 distress judgements use no peers and are kept) | 10 |
| Mean absolute alpha change, affected stocks | — | 9.75 points | 6.86 points |
| Label flips | — | 705 (247 out of Buy/Strong Buy, 225 into Buy) | 3 (none to or from Buy) |
| Newly below the 0.3 coverage floor (drop out of tiers) | — | 144 | 0 |
| Top-10 buy slots changed (of 30, across the three tiers) | — | 14 | 0 |

**Reading the table:**
- **Alt 2** is the honest-today position: no value score without a defensible peer group. It is a
  large change, removing 15% of the score for 88% of the universe (2,160 of 2,462) until a classification exists.
  Under rule R, many of those stocks would regain value against proper peers.
- **Alt 3** is small, because the market-average path is rare (10 stocks). It is a clean,
  independent decision.
- **Rule R's cost** follows once the source exists: each stock is costed from the same frozen
  inputs, with peers re-derived.

**The capital-markets sector** costed earlier (49 Yahoo "Capital Markets" stocks, 12 flips,
KEYFINSERV 1.76) is kept only as an illustration of what a classified group changes. It is **not**
proposed as a membership.

## 6. Implementation plan, after the rule is approved

1. **The classification file** is supplied, committed and versioned (date, source, hash), and its
   coverage of the scored universe is reported.
2. **The rule** is implemented as a new model version, with the peer configuration in the frozen spec.
   The map, counts and fallback are already captured (`65c3fc9`); the classification file's hash
   would be added.
3. **Before/after** on frozen inputs (the fingerprinted cycle): every changed score, label and rank
   is listed.
4. **Tests:** rule determinism; minimum-peer and not-measured paths; no wider fallback; negative peer
   multiples excluded; an oracle check of value against independently derived peers.
5. **Freeze, deploy** (separately authorised), and verify the live commit and the drift check.
6. **Rollback:** revert to the prior version, whose spec is frozen. Rows carry the model-version
   stamp, so studies can exclude either side.

## 7. Decisions requested, in order

1. **The source.** Will you supply NSE's industry classification as a file? Please confirm its
   licence and update frequency.
2. **Rule R** as written, or amendments. In particular: the classification level, *k*, and "missing
   own multiple is not measured".
3. **Alt 3** (not measured instead of market averages): adopt now, or with rule R.
4. **Interim position until rule R is ready:** keep the status quo, which is documented as not
   matching the methodology's description, or adopt alt 2.
5. **Separate, later:** nearest-in-size peers; the constant-promotion work in
   `V1_CONSTANT_INVENTORY_2026-10-14.md`.
