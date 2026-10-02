# Proposal: check the Google News results too (v1.4.3)

**Status: APPROVED by the owner 2026-10-02 ("DO IT"). Implemented in rss_news (SHORT_NAMES, _keep_search_item, _keep_market_item, _LIST_CUE). The list rule was narrowed after measuring it on this sample: "in focus", "buzzing stocks" and "among N stocks" dropped real news, so only "stocks to watch / to buy / to track / in news" and "top stocks" count. Implemented result on the 150: 129 kept, 120 right (93%), 120 of 121 real articles kept. Re-check on fresh news before relying on it.**

## The problem

Each stock's news comes from two places (`backend/modules/rss_news.get_rss_stock_news`):
1. a Google News search for "`<company name>` stock NSE";
2. general market feeds.

v1.4.2 fixed step 2. **Step 1 is not filtered at all**: whatever Google returns is scored. For names made of ordinary words, Google returns general market stories. Live on 2026-10-01, articles that name the company:
- **Oil India:** 5 of 20, for example "Indian shares post worst day in 10 weeks on oil spike".
- **SBI:** 7 of 20. This undercounts, because SBI headlines say "SBI", which is not one of its match terms.

## Evidence

- **Data:** the live app's news for the 40 stocks most often in the top 100, read on 2026-10-01: 799 articles (`quant_data/step1_news/`).
- **Labels:** a seeded random 150 (seed 20261002) were labelled by hand: about the company or not. The guide is the one used for the research matcher: lists of "stocks to watch" and separately listed relatives (Reliance Jio, NTPC Green, ITC Hotels) count as not about the company.

| Option | Articles kept | About the company | Real company articles kept |
|---|---|---|---|
| Today: no filter | 150 | 121 (81%, 95% CI 74–86%) | 121 of 121 |
| A. v1.4.2 match rules | 121 | 111 (92%, CI 85–95%) | 111 of 121 (92%) |
| **B. A plus a hand-checked list of short names** | 133 | 120 (90%, CI 84–94%) | **120 of 121 (99%)** |

**Option A loses real news.** "HUL Q1 results…", "SBI … NSE IPO", "HCL Tech shares fall…" and "M&M Share Price Today" do not use the full name. The short-name list (SBI, HUL, HCL Tech, M&M, L&T, Zomato, Airtel…) already exists, hand-checked, in `research/gdelt_strict.py`.

**What B still lets through (13):**
- **5 list headlines:** "Stocks to Watch Today: …", "Stocks in news: …".
- **4 relatives or demerged units:** Reliance Jio, NTPC Green Energy, Vedanta Iron & Steel, ITC Hotels.
- **4 passing mentions:** in stories about the NSE IPO.

Dropping list headlines (the research matcher's list rule) would remove the first 5. On this sample that gives about 94%, but that number comes from the same sample, not a fresh check.

## The change, if approved (B, plus the list rule)

1. **Filter step 1 like step 2.** An article from the Google search is kept only if it names the company by the v1.4.2 rules or by its hand-checked short name.
2. **The short-name list moves into the app** (`rss_news.SHORT_NAMES`), copied from `research/gdelt_strict.ALIASES`, and is recorded in the frozen spec.
   - It covers the about 200 most-traded companies.
   - Other stocks use the v1.4.2 rules alone (option A: 92% of real articles kept on this sample).
3. **List headlines are dropped from both steps.** These are "stocks to watch", "stocks in news", "in focus" and "buzzing stocks". They name a company without saying anything about it.

**Not changed:** the Google query, FinBERT, the time decay and the weights.

**What this does to scores:**
- Stocks whose Google results were mostly market-wide news, such as Oil India, will have fewer articles.
- Their sentiment moves toward neutral, with lower confidence. That is the honest direction: less evidence, a weaker opinion.
- Before release, one nightly cycle is compared before and after: how many stocks' sentiment moves, and by how much.

## Rollout, if approved

1. **Code and tests:** the cases above, plus "SBI" now accepted for SBI, and Oil India's market-wide headlines rejected.
2. **CI:** all suites pass.
3. **Deploy:** outside 00:02–03:00 UTC, with no backfill running.
4. **Version:** freeze **v1.4.3** (with its own go-ahead). Check that v1.4.2's drift reports the change as behavioural (`news_matching` values differ), then that v1.4.3 is clean.

## Limits of this evidence

- **One day of news, and one labeller (Claude).** Jasmeet re-labelling about 40 of the 150 would show whether the labels hold.
- **The 40 most-traded stocks only.** The worst cases (Oil India) are smaller companies with generic names, where the gain should be larger. They were spot-checked, not sampled.
