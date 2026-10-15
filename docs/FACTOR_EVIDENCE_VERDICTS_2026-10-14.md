# Factor evidence verdicts (2026-10-14)

**Purpose.** This is the investment-evidence track, kept separate from software correctness. The
four-factor audit (`AUDIT_FOUR_FACTOR_2026-10-14.md`) shows the scores are computed as specified. It
says nothing about whether they predict returns; this page records what does.

Every verdict below comes from an existing, pre-registered result. No new test was run for this
page.

| Factor (V1 weight) | Verdict | Evidence | Point-in-time? | Out of sample / robustness | Net of costs | What is missing |
|---|---|---|---|---|---|---|
| **Momentum** (35%) | **Demonstrated edge** at 1, 3, 6 and 12 months | Factor test 1 (`FACTOR_TEST1_RESULT_2026-09-13.md`): pre-registered; Bonferroni 0.00625; re-run twice after data corrections with the verdict unchanged | **Yes**: NSE prices 2011–2026, adjusted, delisted names included | Held in 2019–2026 alone and in liquid stocks (momentum robustness H1); mostly outside the most liquid third | Top-group portfolio *described* net of 0.4% round-trip costs, not tested as a hypothesis | A pre-registered net-of-cost test; a fresh out-of-sample period. **None is accruing:** no NSE price is stored after 2026-09-07 while collection is paused (corrected 2026-10-15, `DATA_COVERAGE_REPORT_2026-10-15.md`) |
| **Value** (15%) | **Not established** | Factor test 2: "no lead" (approximate: restated statements, about 3 years, listed-today names only). Value/quality test from as-published reports: **insufficient data**, 36.4% coverage against an 80% gate, not run | **No**: fundamentals are fetched live; no point-in-time history | — | — | Point-in-time accounts with ≥ 80% coverage, or a new pre-registration stating its survivorship bias. The peer methodology (`PEER_METHODOLOGY_DECISION_2026-10-14.md`) also changes what "value" measures for 87% of stocks |
| **Quality** (25%) | **Not established** | As value: approximate "no lead"; the as-published test had insufficient data | **No** | — | — | As value; plus the Piotroski missing-as-zero policy (inventory L1) |
| **Sentiment** (25%) | **Measurement valid; predictive power untested** | Factor test 3: FinBERT reads Indian headlines correctly (macro-F1 0.734, κ 0.60). That tests the *instrument*, not returns | Headline-level history only from 2026-09-03, and stored for about 47% of stocks (D-02) | — | — | A pre-registered return test (the GDELT plan: titles only from 2019-09-22; pre-registration not yet written). Also the FinBERT licence question |
| Low risk (0%, shown) | **No demonstrated edge** | Factor test 1 | Yes | — | — | Removed from scoring in v1.6.0 |
| 52-week high (reported, not scored) | **Adds beyond momentum** at 3–12 months (not at 1) | Factor test 4 | Yes | First half and second half both positive; the second half is weaker | Described after costs | v1.7.0 display proposal, pending |
| **Composite V1 score and labels** | **Untested** | — | Cannot be computed historically (live fundamentals and news) | Forward record only; the methodology's first read is due from 2026-12-27 | — | The forward track record, graded on its pre-set horizon |

## Reading

- **Only momentum has passed.** It is 35% of the score.
- **The other 65% of V1 is unvalidated:** quality 25%, sentiment 25% and value 15%. One reason is
  that the data to test them point-in-time does not exist here.
- **No Buy/Sell label is validated.** The labels are a composite, and the composite has not been
  tested.

## Next evidence steps (each needs its own pre-registration, written before any run)

1. **Momentum, net of costs:** a pre-registered test of the top-group portfolio against the eligible
   universe, net of 0.415% per unit of turnover, on the 2011–2026 archive. Then a held-out forward
   window.
2. **Sentiment returns:** the GDELT pre-registration, covering horizon, universe, title-only matching
   and the known matcher limits. It should fix the FinBERT revision (now pinned) and the failure
   policy before it runs.
3. **Value and quality:** only with a new pre-registration that states its data limits. The approved
   plan cannot be loosened after its gate failed.
4. **The composite:** the forward record, as planned. No backtest is possible.
