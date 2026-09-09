# Step 3B — The six transitions the resolver refused to link

Read-only against production Postgres, 2026-09-09, 70.4s. No writes, no change
to the resolver, the adjustment layer, V1.4, historical observations or factor
calculations.

## Why these six

Step 3A showed that wherever the resolver *merges* two ISINs, a corporate action
filed under either one reaches the prices: A=35, B=0, C=0 over 49 transitions.
That result says nothing about the cases where the resolver *declined* to link —
and there, by construction, an action on one side cannot reach prices on the
other. These six were the only place a genuinely unlinked adjustment could hide.

## Result

| Verdict | Count |
|---|---|
| A — same security and correctly linkable | 0 |
| **B — action exists but genuinely unlinked** | **1** |
| **C — evidence suggests a different security** | **0** |
| D — no adjustment required | 2 |
| E — genuinely indeterminate | 3 |

**All six are the same issuer.** Every pair shares its ISIN issuer prefix
(characters 0–6), which is evidence read from the identifier itself rather than
from the resolver or from any table this project maintains. So none of the six is
a recycled ticker belonging to a different company, and **C = 0 on evidence, not
on assumption**.

### The resolver's stated reason is wrong in all six cases

Each refusal carries the message *"the same ticker reused after a long gap —
merging these would hide a real delisting"*. The ISINs say otherwise: these are
the **same company** resuming trade after a long suspension, not a ticker handed
to someone else.

**The refusal is still the right call**; only the explanation is wrong. Merging
DSKULKARNI across a 3,058-day hole would manufacture a continuous series through
an eight-year trading halt, and a 252-day momentum window spanning that hole
would be arithmetic about nothing. Declining is conservative and correct. The
message should say "resumed after a long suspension" rather than asserting a
ticker reuse the ISIN contradicts.

## The six, individually

| # | symbol | ISIN a → b | issuer | gap | ratio b/a | verdict |
|---|---|---|---|---|---|---|
| 1 | SUMEETINDS | INE235C01010 → INE235C01028 | INE235C (same) | 245d | 11.44 | **B** |
| 2 | MBECL | INE748A01016 → INE748A01024 | INE748A (same) | 704d | 41.73 | E |
| 3 | BURNPUR | INE817H01014 → INE817H01022 | INE817H (same) | 559d | 3.23 | D |
| 4 | DSKULKARNI | INE891A01014 → INE891A01022 | INE891A (same) | 3,058d | 0.67 | E |
| 5 | KSE | INE953E01014 → INE953E01022 | INE953E (same) | 4,218d | 0.28 | D |
| 6 | EASTSILK | INE962C01027 → INE962C01035 | INE962C (same) | 530d | 14.00 | E |

Company names are unavailable because the production `nse_stocks` table is empty
— a separately recorded defect. Identity here rests on the ISIN, which is
stronger evidence than a name lookup anyway.

**Cross-check:** MBECL and EASTSILK are the same securities the corrected
continuity check classified as resumptions (MBECL +4,072% after 704 days silent;
EASTSILK +1,300% after 530 days). Two independent checks agree on what these
are, which is the kind of corroboration worth noting.

## The one B, and why it does not distort any return

**SUMEETINDS.** A 10→2 split (multiplier 0.2), ex-date **2025-10-03**, filed
under the **old** ISIN `INE235C01010`. The resolver did not link the segments, so
that action cannot reach the new segment's rows.

That is a genuine unlinked action. **It has no effect on any return**, and the
reason is arithmetic rather than luck:

- old segment: 2011-07-04 → 2024-10-17
- new segment: 2025-06-19 → 2025-10-01
- **the ex-date (2025-10-03) falls after every observation of both segments**

The convention is `adjusted(t) = close(t) * PROD(m for ex_date > t)`. When the
ex-date is later than every stored observation, the factor is the *same constant*
for all of them, and a uniform scaling cancels in every ratio:

    adjusted(t1)/adjusted(t0) = [close(t1)/close(t0)] * F/F = close(t1)/close(t0)

Every quantity V1.4 computes is a ratio — momentum is a return, its volatility is
the standard deviation of daily returns, low-risk is volatility and drawdown.
None of them reads a price level. So this stranded action changes nothing that
the model actually consumes, whether the segments are merged or not.

**Conclusion: B=1 in form, 0 in effect.**

## Is any production fix warranted?

**No — not from this investigation.**

- **C = 0.** No transition risks splicing two different companies together.
- **The single B has provably zero impact on returns.**
- **The two Ds need nothing.**
- **The three Es are indeterminate for one reason only: an unparsed corporate
  action sits near the boundary.** They are not evidence of a linkage defect;
  they are three more instances of the 12,778-unparsed-actions problem, which is
  already queued as the next piece of work.

E was left as E. No merge was forced to make it disappear, and no identity was
resolved to tidy the table — which was the explicit instruction and is also the
right scientific posture.

## Limits

- The action search window is +/-120 days around each boundary. An action whose
  ex-date falls *inside* a segment but more than 120 days from the boundary would
  not be found. For the segments here — several of which are only 5 to 73 days
  long — that window comfortably covers the short side.
- Three of six remain indeterminate until the unparsed actions are characterised.
  That work, not this one, is what would change their verdicts.

## Recommended sequence, unchanged

1. ~~Continuity correction~~ — done.
2. ~~ISIN/split linkage~~ — done, no defect.
3. ~~The six resolver-ambiguous transitions~~ — done, no fix warranted.
4. **Characterise the 12,778 unparsed corporate actions.** This now blocks three
   different open questions: the true unexplained-move count in continuity, the
   JBMA-style missing multiplier, and the three E verdicts here.
5. Only then decide whether Momentum / Low-Risk historical validation can be
   called fully trustworthy.
