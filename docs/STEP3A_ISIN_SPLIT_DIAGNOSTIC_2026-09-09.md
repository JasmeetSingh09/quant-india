# Step 3A — Does a new ISIN break the corporate-action join?

Read-only diagnostic against production Postgres, 2026-09-09. No writes, no
score recalculation, no change to the adjustment layer, V1.4 untouched.

## The question

The Step 3 audit found 549 symbols carrying more than one ISIN. In India a
face-value change mints a new ISIN for the *same* company, so that is what a
stock split looks like — not ticker reuse. But corporate actions are stored
keyed by ISIN, and price rows before a split carry the OLD one. If the action
were filed under the NEW ISIN, the adjustment would miss exactly the rows it
must correct, and momentum across the split would be wrong while looking fine.

## The answer: the join is not broken

| Verdict | Count |
|---|---|
| **A — correctly linked** | **35** |
| **B — action exists but unlinked** | **0** |
| **C — linked to wrong security** | **0** |
| **D — no adjustment required** | **13** |
| **E — unable to determine** | **1** |
| total ISIN transitions examined | **49** across 40 symbols |

Population: 549 multi-ISIN symbols; 584 resolver links; 6 resolver-ambiguous;
link window `gap in [-5, +45] days`.

**Why it works.** `security_identity._resolve_pairs` unions ISINs that share a
symbol in sequence, and `pit_validation._apply_adjustment` maps *both* the price
rows and the corporate actions through that same canonical map
(`key = canonical.get(isin, isin)`). An action filed under either ISIN therefore
lands on one identity. Confirmed empirically in both directions:

- **360ONE** `INE466L01020 → INE466L01038`, gap 1d, merged. Dividend, 2:1 split
  and 1:1 bonus all filed under the **old** ISIN.
- **4THDIM** `INE382T01022 → INE382T01030`, gap 3d, merged. 10→2 split filed
  under the **new** ISIN.

Both adjust correctly.

## Raw versus adjusted across the ex-date

35 transitions had a measurable ex-date event. Residual after adjustment:

| residual | count |
|---|---|
| <= 5% | 23 |
| 5–10% | 4 |
| 10–20% | 7 |
| > 30% | 1 |

27 of 35 land within +/-10%. Representative cases:

| symbol | ex-date | multiplier | raw | adjusted |
|---|---|---|---|---|
| ADVANTA | 2013-07-05 | 0.2000 | −79.98% | **+0.11%** |
| AKI | 2023-06-22 | 0.2000 | −79.95% | **+0.26%** |
| AGIIL | 2025-02-07 | 0.5000 | −49.58% | **+0.85%** |
| ANGELONE | 2026-02-26 | 0.1000 | −90.10% | **−1.00%** |
| AEGISCHEM | 2015-09-16 | 0.1000 | −90.11% | **−1.06%** |
| APLAPOLLO | 2020-12-15 | 0.2000 | −79.54% | **+2.31%** |
| ALMONDZ | 2024-07-23 | 0.1667 | −83.85% | **−3.08%** |

A 90% phantom crash correcting to −1% is the adjustment layer working.

The 7 residuals in 10–20% are **not** evidence of a broken join. Indian small
caps carry 20% circuit limits and genuinely move on split days, so a residual of
that size is within plausible single-day range. They are listed, not accused.

## One real defect found: a missing corporate action

**JBMA, ex-date 2014-10-08.**

- last close before ex: 1,037.70 (2014-10-07)
- first close on/after ex: 248.90 (2014-10-08)
- raw return: −76.01%
- **implied true multiplier: 0.2399**
- **recorded multiplier: 0.5000** (a 1:1 bonus, and nothing else)
- ratio recorded/implied: **2.085**

A 1:1 bonus is on record. The implied multiplier says a second price-halving
action went ex the same day — a 10→5 face-value split — and it is **not in
`corporate_actions`**. 0.5 x 0.5 = 0.25 against an implied 0.2399, the remainder
being a genuine ~4% move that day.

Adjusted return for JBMA across that event is **−52.03%**, which is not a
plausible one-day move and is therefore residual error, not market action.

This is a **corporate-action completeness** defect, not an ISIN-linkage defect.
It is plausibly one instance of the 12,778 unparsed actions (38.8% of 32,964)
already recorded in the Step 3 audit. **Not fixed** — per the agreed sequence,
whether those actions matter to adjusted prices is determined before anything is
repaired.

## The E case

**20MICRONS** `INE144J01019 → INE144J01027`, 2013-01-28/29. The ISIN changed,
the ISIN-boundary raw return is −4.04%, and no *parsed* action sits at the
boundary. Correctly reported as unknown rather than as "no adjustment required" —
the distinction between D and E is exactly what stops an unparsed action from
being silently recorded as a clean bill of health.

## Three corrections to this diagnostic, disclosed

All three were mine, all the same root cause, and one nearly became a false
accusation against production.

1. **Inverted search window.** When two ISINs overlap in time, `prev.last` falls
   after `nxt.first`; the action window inverted and found nothing, reporting
   "no adjustment required" for a case never searched. Caught by the synthetic
   overlap test.
2. **Non-strict ex-date comparison.** `adjusted(t) = close(t) * PROD(m for
   ex_date > t)` — strictly greater. Multiplying a price that already trades
   post-action reported AJANTPHARM at **+99.71%** on a boundary whose raw return
   was −0.15%.
3. **Wrong anchor.** The ISIN transition is not the ex-date. **AHCL** changed
   ISIN on 2026-04-23 while its split and bonus went ex on 2026-04-24, so the
   pair being compared straddled no action at all; multiplying it produced
   **+895.84%**. Returns are now measured across the ex-date, with the
   ISIN-boundary return retained as a separate descriptive field.

**Production was never wrong in any of these.** `_apply_adjustment` uses
`bisect_left` and has always applied factors only to columns strictly before the
ex-date. The verdicts (A–E) were never affected either, since they derive from
the resolver rather than from this arithmetic — which is why the classification
was stable at A=35, B=0, C=0 across all three runs.

Synthetic tests: **30 assertions, all passing**, provoking every verdict and
pinning all three regressions, including the AHCL shape (ISIN boundary −0.4%,
ex-date raw −89.96%, adjusted +0.4%).

## Verdict C is unreachable, and that is a property

`bhavcopy_eod` is keyed on `(symbol, day)`, so one symbol cannot physically hold
two ISINs on the same day — which is why the identity audit found 0 same-day
collisions in 6,598,053 rows. And the resolver refuses to merge ISINs whose
ranges overlap by more than 5 days. Between them, "linked to the wrong security"
cannot arise. C stays in the scheme because that rule could be relaxed later,
and this is where it would surface.

## Limits of this result

- **49 of 584** resolver-linked transitions were examined (~8%), chosen as the
  six audit-named symbols plus alphabetical fill. The A/B/C outcome is driven by
  a structural rule rather than by the sample, so it should generalise — but it
  is a sample.
- **The 6 resolver-ambiguous transitions were not examined**, and they are
  precisely the population where verdict B would live: the resolver declined to
  link them, so an action on one side cannot reach prices on the other. Checking
  those 6 by name is the highest-value remaining query and is cheap.
- Whether the JBMA-style missing action is common is unknown until the 12,778
  unparsed actions are characterised.
