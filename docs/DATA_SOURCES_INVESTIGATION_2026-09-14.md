# Data sources for a 2026 verdict: first investigation

**2026-09-14, after the v1.4.1 freeze.** Desk research only. Public product pages
and search results were read. No provider was contacted, nothing was downloaded,
and nothing was bought.

**Status labels:**
- **Verified:** the provider's own page or documentation says so.
- **Search summary:** a search result quoting the provider; confirm before relying on it.
- **Unclear:** not stated anywhere public.

## What a source must have

- **Option 1, company accounts:** each company's figures **as first published**, kept apart from later restatements, together with the date each became public.
- **Coverage:** NSE-listed companies, delisted ones included, for about 10 years or more.
- **Variables:** revenue, net income, EPS, equity, total assets, operating cash flow, capex, debt, shares outstanding.
- **Licence:** allows research and competition use, including publishing aggregate results.

## Option 1: historical Indian company accounts, as first published

| Source | Keeps figures as first published? | India and delisted coverage | History | Access | Verdict so far |
|---|---|---|---|---|---|
| **LSEG Point-in-Time Fundamentals** (formerly Reuters Fundamentals) | **Yes** (search summary): "preliminary, original, re-statements, reclassifications, and final figures", "timestamped to the moment that they were made available" | India not confirmed; delisted not stated | 1997 on for non-US companies (search summary) | Institutional licence; price not public | Strongest point-in-time design. India coverage and student access unclear. |
| **FactSet Fundamentals Point-in-Time** | **Yes** (search summary): data "as it appeared … since February 1999" | FactSet Fundamentals covers 86,000+ companies "including inactive companies" in 115+ countries. India's point-in-time coverage not confirmed. | 1999 on | Institutional; price not public | Point-in-time design matches; India unclear. |
| **S&P Compustat Snapshot** (usually through WRDS at a university) | **Yes** for Snapshot (search summary): "both the preliminary and the final data", snapshots from 1987 | Compustat Global covers "international exchanges"; whether Snapshot covers India is not confirmed | 1987 on | WRDS institutional subscription | Needs a university; global Snapshot coverage unclear. |
| **CMIE Prowess dx** | **Unclear.** Data "as filed with the Ministry of Company Affairs" and "methodically standardised"; handling of restatements and filing dates not stated | **All NSE and BSE listed companies**; "we do not drop companies once they are added" (no survivorship bias). Verified on the CMIE page. | Since 1989 (verified) | "Specially designed for" the academic community; price not public | **Best Indian coverage.** The deciding question is restatement handling. |
| **ACE Equity Nxt** (Accord Fintech) | Unclear | 40,000+ Indian companies, from annual reports (search summary) | Not stated | Commercial; price not public | Unclear on every criterion that matters. |
| **BSE XBRL financial results** | **Yes by nature:** filings as submitted | BSE-listed companies. XBRL results voluntary from June 2015, mandatory from 1 April 2017 (search summary). | 2015 or 2017 on | Licensed through Deutsche Börse (search summary; that page returned 404) | Point-in-time by construction, about 9 years. Licence terms unverified. |

NSE's own filings are excluded: collection from NSE has been paused since 2026-09-08 under our written commitment.

## Option 2: historical dated news

| Source | Headlines | Dates | History | Terms | Verdict so far |
|---|---|---|---|---|---|
| **GDELT GKG 2.x** | **Yes since September 2019:** a `PAGE_TITLE` block in the Extras field. Verified on the GDELT blog. | Records are processed in 15-minute batches; whether a precise publisher timestamp exists is unverified | About 7 years of headlines, which passes the 5-year bar | **Verified:** "unlimited and unrestricted use for any academic, commercial, or governmental use … without fee", citation required | Passes access and history. Still to check: the exact time field, and whether articles can be matched to the right company to the standard set on 2026-09-03. |

## Questions to send, if approved

**To CMIE (Prowess dx):**
1. When a company later restates or revises a past year's figures, does Prowess dx keep the originally filed figures, or overwrite them?
2. Is the filing or publication date stored for each annual and quarterly statement?
3. Can a school student use Prowess dx through an institutional subscription, and may aggregate results be published in a research competition?
4. What does individual or academic access cost?

**To LSEG and FactSet (point-in-time products):**
1. How many Indian companies are covered, from which year, and are delisted companies included?
2. Is there academic or student access, and at what price?

**To a university library with WRDS:** does Compustat Global Snapshot include Indian companies, and from which year?

**To Deutsche Börse (BSE corporate data):** what are the licence terms and price for historical XBRL financial results for non-commercial research?

**For the family to find out:** school, mentor or competition access to any of the above, and a budget ceiling.

## Sources

- [CMIE Prowess dx product page](https://www.cmie.com/kommon/bin/sr.php?kall=wproducts&tabno=7010&prd=prowessdx)
- [IIM Calcutta library: CMIE Prowessdx](https://library.iimcal.ac.in/cmie-prowessdx/)
- [LSEG Point in Time Fundamentals](https://www.lseg.com/en/data-analytics/financial-data/company-data/fundamentals-data/point-in-time-fundamentals)
- [LSEG Worldscope Fundamentals](https://www.lseg.com/en/data-analytics/financial-data/company-data/fundamentals-data/worldscope-fundamentals)
- [FactSet Fundamentals Point-in-Time](https://www.factset.com/marketplace/catalog/product/factset-fundamentals-point-in-time)
- [FactSet Fundamentals](https://www.factset.com/marketplace/catalog/product/factset-fundamentals)
- [S&P Global fundamental data](https://www.spglobal.com/market-intelligence/en/solutions/products/fundamental-data)
- [WRDS: Compustat Global basics](https://wrds-www.wharton.upenn.edu/pages/grid-items/compustat-global-wrds-basics/)
- [Accord Fintech: ACE Equity Nxt](https://www.accordfintech.com/ace-equity-nxt)
- [BSE: About XBRL](https://www.bseindia.com/static/about/xbrl_info.aspx)
- [XBRL International: BSE mandates XBRL for financial statements](https://www.xbrl.org/news/bse-mandate-xbrl-for-financial-statements/)
- [GDELT: GKG 2.0 now includes page titles](https://blog.gdeltproject.org/gkg-2-0-now-includes-page-titles/)
- [GDELT: about and terms of use](https://www.gdeltproject.org/about.html)
- [GDELT GKG 2.1 codebook](http://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf)
