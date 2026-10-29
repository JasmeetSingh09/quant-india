# Questions for the lawyer (2026-10-29)

These go with `PRIVACY_POLICY_DRAFT_2026-10-29.md` and `TERMS_OF_USE_DRAFT_2026-10-29.md`. Each
one is a fact from the code plus the question it raises. They are ordered by how likely they are to
block a launch.

1. **SEBI (Research Analyst Regulations 2014 / Investment Adviser Regulations 2013).**
   - **Fact:** the app is public and free. It ranks named NSE stocks ("Top Picks", in groups by
     company size), labels them Strong Buy / Buy / Sell / Strong Sell, and can email price and
     signal alerts.
   - **Question:** does this need registration, or a change of labels or features, or does the
     educational disclaimer suffice?
   - **Fallback that lowers the risk:** rename the labels ("Highest model scores", "Model: high /
     low") and drop the signal alerts.
2. **Minors.**
   - **Fact:** the pilot users were described in the code as classmates, which likely means under 18.
   - **Question:** DPDP section 9 requires verifiable parental consent and bans tracking and
     behavioural monitoring of children. Should the app be 18+ only, or build parental consent and
     switch off product events for minors?
3. **Cross-border storage.**
   - **Fact:** the database is in Japan (Supabase, Tokyo), the server likely in the US (Render), and
     email goes through Gmail.
   - **Question:** is a notice enough under DPDP section 16 as it stands now?
4. **Yahoo Finance data.**
   - **Fact:** prices and fundamentals are fetched with the unofficial `yfinance` library and shown to
     the public.
   - **Question:** Yahoo's terms restrict this to personal use. What is the exposure, and is a
     licensed feed needed before launch, or before any monetisation?
5. **FinBERT licence.**
   - **Fact:** the sentiment model's card now says CC BY-NC-SA 4.0 (non-commercial).
   - **Question:** is a free app "non-commercial"? What changes if ads or a paid tier are added?
6. **NSE data.**
   - **Fact:** historical bhavcopy files from the NSE archive are stored and used. A request to NSE
     for permission is still unanswered.
   - **Question:** may they be shown publicly?
7. **Sidebar attribution.**
   - **Fact:** the sidebar says "Data via NSE · NewsAPI", but most live data comes from Yahoo.
   - **Question:** what attribution should it show?
8. **Liability cap** and the enforceability of an "as is" clause under the Consumer Protection Act
   2019.
9. **Grievance officer and DPDP Rules timelines** (breach notice, response times) as currently
   notified.
