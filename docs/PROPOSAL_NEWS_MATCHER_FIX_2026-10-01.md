# Proposal: stop the sentiment factor reading other companies' news

**Status: PROPOSAL, awaiting the owner's approval.** It changes v1.4.1 behaviour, so it needs approval and a new version, v1.4.2 (AGENTS.md rule 3). No code has been changed.

## The problem

Sentiment is 25% of every stock's score. Each stock's news comes from two places (`backend/modules/rss_news.py`):
1. a Google News search for the company (primary);
2. general market headlines that "mention" the company (secondary). **This step is where the leak is.**

`_identity_terms` turns a company name into match terms. Two parts of it are too loose.

**1. One ordinary word from the name is enough.** When a name is mostly generic words, a fallback adds the remaining words back as single-word matches:

| Company | Matches any headline with |
|---|---|
| Oil India | "india" |
| Adani Green | "green" |
| IDFC First Bank | "first" |
| BHEL | "heavy" |
| Just Dial | "just" |
| MCX | "exchange" |
| ICICI Lombard | "general" |
| IRFC | "railway" |
| Tata Motors PV | "vehicles" |

115 of the 204 most-traded companies match on a single word from a multi-word name.

**2. Generic two-word prefixes count.** For example "state bank" (the SBI leak recorded on 2026-09-09) and "life insurance".

**Evidence:**
- **Live:** `/stock/news?ticker=OIL.NS` on 2026-09-26 returned 20 headlines, all about other things (forex reserves, the rupee, other companies' IPOs).
- **Measured:** 300 matches of the app's matcher on general news, drawn at random (seed 20260926) and labelled by hand (`quant_data/gdelt_match/label_300_claude.tsv`). **30 were about the right company (10%).**

## The fix (in `_identity_terms` only)

1. **A single word from a multi-word name never counts on its own.** The ticker still counts, and one-word names still count (Infosys, Wipro, Cipla).
2. **A leading "the" is dropped** ("The Tata Power Company" becomes "tata power").
3. **A two-word prefix counts unless:**
   - it contains "and", "of" or "&"; or
   - it is made only of generic words and does not start with a group name. "State bank" and "life insurance" go; "Tata Motors" and "Adani Ports" stay.
4. **"railway" and "railways" join the existing list of sector words.**

The full-name phrase, the Google News step, `_mentions`, the sentiment model, the time decay and the weights are all unchanged.

## Measured on the same 300 labelled headlines

| | Right kept | Wrong kept | Share right |
|---|---|---|---|
| Today's matcher | 30 of 30 | 270 of 270 | 10% |
| **With the fix** | **29 of 30** | **6 of 270** | **83%** |

- **The one right headline lost** names "Airtel" without "Bharti". The Google News search (step 1) still finds such news.
- **The 6 still wrong** come from one-word names (Apollo, ABB, BSE, Siemens) and one HDFC case. Fixing those needs a hand-checked list of names (the research matcher's approach). That is a larger change, left for later.

**Limits of this evidence:**
- The sample is general news (GDELT). The app's step 2 reads business feeds, where the share right should be higher.
- One person (Claude) labelled it. Jasmeet re-labelling 50 would strengthen it.

## Effect on scores

- **Who changes:** only stocks whose market-feed matches change. Leaked headlines were mostly general news scored near neutral, but they also pulled weight and "confidence" away from real company news.
- **Before release:** the change is measured on one nightly cycle: how many stocks' sentiment moves, and by how much.

## Rollout, if approved

1. **Code:** change `_identity_terms`, with tests for every case above and for the unchanged one-word names.
2. **CI:** all suites pass, run locally.
3. **Deploy:** outside 00:02–03:00 UTC, with no backfill running.
4. **New version:** freeze **v1.4.2**, with this document as its note. Freezing is a production write and needs its own go-ahead. Then check `/strategy/drift/v1.4.2` reports no behavioural drift.
5. **Record:** v1.4.1's history is kept unchanged. Signals before the change stay attributed to v1.4.1.
