# Spec: `peer_basis`, a display-only marker of what each value score was compared with

**Status: specification, revision 2.** It carries the owner's label decisions of 2026-10-14. It was
approved in principle as a separate, versioned, display-only change. **Not implemented.**

**Separate from the redesign.** This is independent of the peer-methodology redesign
(`PEER_METHODOLOGY_DECISION_2026-10-14.md`). It describes today's behaviour honestly and changes
none of it.

## 1. Field values

`factors.value.peer_basis` is derived from data the value factor already has. Exactly one value
applies to each result:

| Value | When (today's code path) | Stock-page note | 2026-10-14 count |
|---|---|---|---|
| `hand_mapped_sector` | Peers came from the hand-written `NSE_SECTORS` | **Hand-mapped sector peers** | 233 |
| `broad_sector_fallback` | The stock is not in the map; peers are the first names of a Yahoo-sector group (`YAHOO_SECTOR_FALLBACK`) | **Broad-sector fallback peers** | 2,151 |
| `market_average` | No peers, or fewer than 2 with the multiple, so the 22 ± 8 / 3.2 ± 1.5 averages were used. **Shown per measure** (section 2). | **Market-average fallback** | 10 (+2 stocks whose P/E alone used the average, section 2) |
| `distress` | Both own multiples ≤ 0: the −0.5 judgement, which uses no peers | **Distress treatment — no peer comparison** | 64 |
| `not_measured` | No usable multiple (the refusal path) | **Not measured** (with its reason) | 4 |

**Wording rule (owner, 2026-10-14).** Each label names the calculation actually performed. None
may imply that a fallback is an industry-peer comparison, or that any score is validated. The
hand-written map holds known errors (D-01), so it is called a hand-mapped sector, not an industry.
The value `classified_industry` is reserved for rule R, once an authoritative classification is in
use.

## 2. Per-measure detail (the owner's metric-specific requirement)

`factors.value.measures` holds one entry each for `pe` and `pb`. Each entry has:
- `status`: `measured`, `not_measured`, `market_average`, or `non_positive_dropped`;
- `peers_used`: the number of peers with that multiple, as the code counts them today;
- `z`: `null` unless measured.

**This closes the reporting gap pinned by oracle check V16c.** Today a missing P/E reports
`pe_z_score` 0.0, the same as a P/E measured exactly at the mean. `pe_z_score` and `pb_z_score` stay
as they are, so stored history is unchanged; the new `measures.*.z` carries the honest value.

## 3. Where it appears

- **`/alpha/score` and `/alpha/explain`:** the new keys inside `factors.value`.
- **Stock page:** a one-line note under the value row (`StockExplorer.jsx`) and in the why-signal
  panel. The tier cards get a small marker for `broad_sector_fallback` and `market_average`.
- **Provenance (`factor_inputs`):** `value.peer_basis` is recorded as a *diagnostic* (in
  `DIAGNOSTIC_MAP`), so it does not count toward input completeness. `raw_inputs_available` cannot
  change.

## 4. What must not change, and how that is tested

| Must not change | Test |
|---|---|
| Any factor score, alpha, label or coverage | The 339 behavioural snapshots stay identical; the oracle suite stays unchanged; new value fixtures are recorded *before* the change and compared after |
| Rankings and tiers | `top_by_tier` output stays identical on the oracle suite's synthetic tiers (D09–D16) |
| Stored history | `factor_history` rows are byte-identical for a re-recorded synthetic cycle; `raw_inputs_available` is unchanged |
| Label accuracy | Each of the five values is produced by a synthetic case that takes exactly that code path, and by no other (exhaustive on the oracle cases V01–V16) |
| Frozen spec | The spec hash is unchanged (display keys are not parameters), shown by a test |

## 5. Versioning and release

- **Model version:** none. No parameter changes, so `MODEL_VERSION` and the frozen spec stay as they
  are. The release is identified by its commit and recorded in the changelog as a display change.
- **Deployment:** separately authorised, after the pending local commits are reviewed.
- **Rollback:** revert the commit. There is no data migration, because the new keys are additive.

## 6. Decided (owner, 2026-10-14)

1. **Labels:** as in section 1, bold, exactly as worded.
2. **Market-average fallback is shown per measure.** For example, "P/E: market-average fallback;
   P/B: not measured". Each measure in `measures` carries its own status. The top-level
   `peer_basis` is the basis of the measured measure or measures. When the two measured measures
   differ, the top level is `mixed` and the page shows both.

No open points remain. Implementation waits for authorisation as its own change.
