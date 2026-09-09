# Step 3C — Corporate-action parser fix and production re-parse

2026-09-09. Parser corrected, dry-run gated, write approved and executed,
post-write verification passed. V1.4, historical prices, identity mappings,
factor formulas, weights and thresholds untouched. A5 not rerun.

## What was wrong

Four parser gaps, each reproduced from a real production subject line:

| Real subject | Why the shipped parser missed it |
|---|---|
| `Face Value Split Rs.10/- To Rs.2/-` | `_SPLIT_RE` required the literal word "from" |
| `Sub-Division From Rs 10/- To Rs 2/-` | parser also required "split" in the text |
| `Bonus - 3:1` | `_BONUS_RE` had no room for a hyphen |
| `Annual Geneeral Meeting/Div.Rs.3/- Per Share` | `_DIV_RE` required "dividend"; feed writes `Div.` |

**JBMA is the clearest case.** Its subject reads `Bonus 1:1 And Face Value
Split Rs.10/- To Rs.5/- Per Share` — one line carrying two actions. The bonus
was parsed and stored; the split was not, and because `store()` writes one row
per action found, the split was never recorded anywhere. It was not among the
12,778 unparsed rows. It was not in the table at all. Its only trace was a
price series that halved twice while the record explained one halving.

That is why the 12,778 was the wrong measure. The right one is subject lines
describing more than the archive stored: **94 in 32,530 events (0.29%)**.

## The gate earned its place twice

**Dry run v1 said DO NOT WRITE.** 12 conflicts and 24 drops, both mine:

- **24 DROPs were a real regression I introduced.** The feed runs words
  together — `Annual General Meetingdividend`, `Interimdividend`, `Specia
  Ldividend` — and the shipped regex read them because it carried no leading
  word boundary. I added one and silently lost 24 real dividends, one of them
  Rs 850. The parser recovering 94 actions was simultaneously destroying 24
  that already worked.
- **12 CONFLICTs were an artifact of the dry run.** `store()` keys rows by
  `(isin, ex_date, sig)` with sig derived from the subject, so one date can
  legitimately hold an interim and a final dividend. Comparing by
  `(isin, ex_date, kind)` collapsed them last-write-wins over an unordered set.

Neither would have been found by reading the four regexes. Only running them
against all 32,964 rows found them.

**Dry run v2 was clean and deterministic.**

| criterion | result |
|---|---|
| rows examined | 32,964 / 32,964 |
| ADD | 94 (80 dividend, 11 split, 3 bonus; 83 in coverage) |
| CONFLICT | **0** |
| DROP | **0** |
| determinism | identical across 3 runs, including add ordering |
| `safe_to_write` | True |

## The write

Additive-only was enforced by the **database**, not by the function's
intentions: every insert carried `ON CONFLICT (isin, ex_date, sig) DO NOTHING`,
so a wrong plan could at worst fail to insert. Verified idempotent beforehand —
a second run plans zero.

| | |
|---|---|
| rows before → after | 32,964 → **33,058** (delta **+94**) |
| parsed before → after | 20,186 → 20,280 (**+94**) |
| pre-existing parsed rows | 20,186 |
| **lost or altered** | **0** |
| `reconciles` | True |

The delta was measured and reconciled, not assumed. Separately, all 20,186
pre-existing parsed rows were fingerprinted on their **values** (isin, ex_date,
sig, kind, num, den, amount) before and after. A count alone would not catch a
silent rewrite; the fingerprint would.

## Post-write verification

| # | Check | Result |
|---|---|---|
| 1 | Row delta matches +94 | PASS |
| 2 | All 94 additions present | **0 still recoverable** |
| 3 | No pre-existing action lost/changed | **0 of 20,186** |
| 4 | No NCRPS/preference/debenture as equity bonus | **0** |
| 5 | JBMA split present | bonus 1:1 + split 10→5, combined **0.25** |
| 6 | 20MICRONS split; last E resolved | split 10→5; **E → A** |
| 7 | 35 ISIN transitions unchanged | 34 identical, 1 intended |
| 8 | Adjusted-price continuity, affected securities | see below |
| 9 | All counts reported | this document |
| 10 | A5 rerun | **not rerun** |

Final table: **33,058 rows** — 19,252 dividend, 536 bonus, 492 split, 12,778
other; 20,280 parsed.

**The unparsed count is still 12,778, and that is correct.** The 94 were new
rows, not reclassifications; the original `other` rows remain as the record of
what the feed actually said. 20MICRONS shows it plainly — the old `other` row
sits beside the new `split` row.

### Adjusted-price continuity for the affected securities

ISIN/split diagnostic, re-run after the write:

| | before | after |
|---|---|---|
| A — correctly linked | 35 | **36** |
| B — action exists, unlinked | 0 | 0 |
| C — wrong security | 0 | 0 |
| D — no adjustment required | 13 | 13 |
| E — unable to determine | 1 | **0** |

Exactly one verdict changed, and two adjusted returns:

- **JBMA −52.03% → −4.06%.** That residual *was* the missing split. Recorded is
  now 0.25 against an implied 0.2399, leaving ~4% — a plausible one-day move
  rather than half the price.
- **20MICRONS None → +5.24%**, previously unmeasurable.

The other 34 transitions are identical, adjusted returns included.

## A defect found in the verification itself

`post_write_verify` first returned `UNMEASURED: IndexError: tuple index out of
range`. Its `LIKE '%ncrps%'` patterns were inlined as literals, and psycopg2
reads `%` as a parameter marker whenever params are passed — which the db
wrapper always does, even with an empty tuple.

**It works perfectly on SQLite**, and every local test in this repo runs on
SQLite, so the entire class of defect is invisible to them. It surfaced only
because the function refused to report a success it could not substantiate. A
version that swallowed the exception and returned `all_clear` would have looked
identical and been worthless.

Patterns are parameters now, and the check was confirmed to *fire* on a planted
`Bonus Ncrps 46:1` — so "0" means the query works, not that it matched nothing.

## What this does and does not settle

**Settled.** The parser gaps are closed, the 94 recoverable actions are stored,
the two named events are correct, and the adjustment layer reaches them.

**Not settled.** Whether the value/quality factors can ever be point-in-time
(they cannot, without PIT fundamentals — Step 7), and production news relevance,
which this audit never measured. Both remain open.
