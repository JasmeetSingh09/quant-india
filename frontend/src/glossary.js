// Plain-English definitions for every piece of jargon on the site.
// Used by the <Term> component to show a tooltip on hover.
// Keep each definition short, concrete, and beginner-friendly.

export const GLOSSARY = {
  // ── Alpha model ──
  alpha_score:  "A single 0-to-100 style score (-100 to +100) summing up how attractive a stock looks right now. Positive = looks good to buy, negative = looks weak.",
  signal:       "The plain recommendation the score turns into: Strong Buy, Buy, Neutral, Sell, or Strong Sell.",
  confidence:   "How sure the model is, based on how much data it had. Higher = more trustworthy.",
  momentum:     "Has the stock been going up lately compared to similar stocks? Winners often keep winning for a while.",
  quality:      "Is this a financially healthy company? (good profits, low debt, strong cash flow).",
  value:        "Is the stock cheap or expensive compared to its peers? Cheaper can mean better value.",
  sentiment:    "Whether recent news headlines about the stock sound positive or negative (read by an AI model called FinBERT).",

  // ── Risk / performance metrics ──
  sharpe:       "Return earned for each unit of risk taken. Higher is better. Above 1 is good, above 2 is excellent.",
  sortino:      "Like the Sharpe ratio, but it only counts the 'bad' (downward) swings as risk. Higher is better.",
  calmar:       "Yearly return divided by the worst drop. Higher means you earned more for the pain you endured.",
  cagr:         "The smoothed average yearly growth rate — what your money grew by per year, on average.",
  max_drawdown: "The worst peak-to-bottom fall the portfolio suffered. -30% means it once dropped 30% from its high.",
  volatility:   "How much the price bounces around. Higher = bumpier ride.",
  var95:        "Value at Risk: on a normal bad day (worst 5% of days), this is roughly how much you'd lose.",
  cvar95:       "The average loss on those worst-5% days — i.e. how bad the bad days really get.",
  win_days:     "The percentage of days the portfolio went up.",
  alpha:        "Return that is NOT explained by just following the market — the part that could be real skill.",
  beta:         "How much the stock moves with the overall market. 1 = moves with the market, <1 = calmer, >1 = wilder.",
  information_ratio: "How consistently a portfolio beats its benchmark. Higher = more reliable outperformance.",

  // ── Backtest concepts ──
  backtest:     "Testing a strategy on past data to see how it would have done.",
  in_sample:    "The earlier slice of history used to 'train' or design the strategy.",
  out_of_sample:"A later slice of history the strategy never saw — the honest test of whether it really works.",
  overfitting:  "When a strategy looks great on past data but fails on new data because it was tuned too tightly to the past.",
  benchmark:    "A yardstick to compare against — here, the Nifty 50 index (India's top 50 stocks).",
  nifty:        "The Nifty 50 — India's main stock index, tracking the 50 largest companies.",

  // ── Optimizer ──
  markowitz:    "The classic way to mix stocks for the best return-vs-risk balance (from 1952). Can over-concentrate in one stock.",
  mvo:          "Mean-Variance Optimization — finds the stock mix with the best risk-adjusted return.",
  hrp:          "Hierarchical Risk Parity (2016) — a modern, more stable way to spread money across stocks by grouping similar ones together.",
  black_litterman: "A method that starts from the whole market's view, then nudges the mix based on your own opinions (here, AI sentiment).",
  efficient_frontier: "A curve showing the best possible return for each level of risk. Portfolios on it are 'efficient'.",
  equilibrium_weights: "The starting mix implied by each company's size in the market, before adding any opinions.",
  max_weight:   "A cap on how much of the portfolio any single stock can be — forces diversification.",
  hedge_ratio_w:"How the optimizer splits money across the chosen stocks.",

  // ── Monte Carlo ──
  monte_carlo:  "Running thousands of random 'what-if' futures to see the range of outcomes, not just one guess.",
  bootstrap:    "A Monte Carlo method that reshuffles real past returns — keeps the market's real behaviour (including crashes).",
  fat_tails:    "Real markets crash harder and more often than a tidy bell curve predicts. 'Fat tails' captures that extra danger.",
  percentile:   "A ranking point. The 5th percentile outcome means only 5% of futures were worse than this.",
  prob_loss:    "The chance of ending with less money than you started with.",

  // ── Pairs trading ──
  pairs_trading:"Buying one stock and short-selling a similar one, betting their price gap will snap back to normal. Profits even if the market falls.",
  cointegration:"A statistical test for whether two stocks' price gap reliably returns to an average — the key requirement for pairs trading.",
  hedge_ratio:  "How many shares of stock B to trade against each share of stock A so the bet is balanced (market-neutral).",
  zscore:       "How far the price gap is stretched from normal, in 'standard deviations'. Past ±2 usually triggers a trade.",
  spread:       "The price gap between the two paired stocks.",
  half_life:    "How many days the gap typically takes to revert halfway back to normal. Shorter = quicker trades.",
  market_neutral:"A position that can profit whether the overall market goes up or down, because you're long one stock and short another.",
  pvalue:       "The chance the result is just luck. Below 0.05 (5%) is the usual bar for 'statistically real'.",

  // ── Fama-French ──
  fama_french:  "A famous model that splits a stock's return into known 'factors' (market, company size, value) to see if there's any real skill left over.",
  smb:          "Small Minus Big — the return edge of small companies over large ones. A 'size' factor.",
  hml:          "High Minus Low — the return edge of cheap 'value' stocks over pricey 'growth' ones. A 'value' factor.",
  market_beta:  "How much the stock simply rides the overall market. ~1 means it basically tracks the index.",
  r_squared:    "How much of the stock's movement the model explains, 0 to 1. 0.5 = explains half.",
  t_stat:       "How strong a result is relative to noise. Bigger (past ~2) means more reliable.",
  significant:  "'Statistically significant' = unlikely to be random luck (p-value below 5%).",
  factor_exposure:"Return that comes simply from being a certain type of stock (small, cheap, market-following) rather than from skill.",

  // ── Regime ──
  regime:       "What 'mood' the market is in: Bull (rising), Bear (falling), or Sideways (choppy/flat).",
  hmm:          "Hidden Markov Model — an algorithm that figures out the market's hidden mood from its daily ups and downs.",

  // ── Fundamentals ──
  pe_ratio:     "Price-to-Earnings: how many rupees you pay for ₹1 of yearly profit. Lower can mean cheaper.",
  ev_ebitda:    "A valuation measure that accounts for debt — useful for comparing companies fairly.",
  roe:          "Return on Equity: profit earned on shareholders' money. Higher = more efficient.",
  roa:          "Return on Assets: profit earned on everything the company owns.",
  profit_margin:"How many paise of profit the company keeps from each rupee of sales.",
  debt_to_equity:"How much debt the company uses vs its own money. Lower is safer.",
  piotroski:    "A 0-9 health score for a company. 7-9 = strong, 0-3 = weak.",
  dupont:       "A breakdown of WHY a company's return-on-equity is high or low (margins, efficiency, or debt).",
  market_cap:   "The total value of all the company's shares — i.e. how big the company is.",
}
