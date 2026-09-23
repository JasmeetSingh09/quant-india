// Plain-English definitions for every piece of jargon on the site.
// Used by <Term> and <InfoTip> to show a tooltip on hover.
//
// Each definition must match how THIS app computes the number (Sharpe and
// Sortino as in backend/modules/risk_metrics.py, momentum as in alpha_model.py),
// not a textbook's. LIMITS says, in one line, what the number cannot tell you.
// Every key in GLOSSARY must have a LIMITS entry; backend/tests/glossary_test.py
// checks both, and checks the wording never promises a return.

export const GLOSSARY = {
  // ── Alpha model ──
  alpha_score:  "One score from -100 to +100 combining momentum, quality, value and news sentiment. Higher means the model ranks the stock higher. It is not a predicted return.",
  signal:       "Where the score ranks the stock: Top ranked, Ranked high, Middle, Ranked low or Bottom ranked. A ranking, not a recommendation.",
  confidence:   "Data coverage: how much of the model's input data was available for this stock.",
  momentum:     "The stock's own return over the past year, skipping the latest month, divided by how bumpy the ride was.",
  quality:      "The model's financial-health score: return on equity, free cash flow and the Piotroski test, with penalties for signs of distress such as negative book value or weak interest cover.",
  value:        "How cheap the stock is on price-to-earnings and price-to-book, compared with similar companies.",
  sentiment:    "Whether recent news headlines about the stock read positive or negative, as scored by FinBERT, a language model trained on financial text.",

  // ── Risk / performance metrics ──
  sharpe:       "Average return above the risk-free rate, divided by how much returns swing, scaled to a year. Higher means more return per unit of swing.",
  sortino:      "Like Sharpe, but only swings below the risk-free rate count as risk, measured across all periods. Higher is better.",
  calmar:       "Yearly growth rate divided by the worst peak-to-bottom fall. Higher means more growth for the worst pain endured.",
  cagr:         "Compound annual growth rate: the steady yearly rate that would turn the starting value into the ending value.",
  max_drawdown: "The worst fall from a previous high to a later low. -30% means it once dropped 30% from its peak.",
  volatility:   "How much returns swing, as a yearly standard deviation. Higher means a bumpier ride.",
  var95:        "Value at Risk: on the worst 5% of days, the loss was at least this much.",
  cvar95:       "Conditional Value at Risk: the average loss on the worst 5% of days.",
  win_days:     "The share of days the portfolio went up.",
  alpha:        "Return left over after accounting for what the market (or the factors) explain.",
  beta:         "How much the stock tended to move when the market moved. 1 means in step, below 1 calmer, above 1 wilder.",
  information_ratio: "Average return above the benchmark, divided by how much that difference swings.",

  // ── Backtest concepts ──
  backtest:     "Replaying a strategy on past prices to see how it would have done.",
  in_sample:    "The stretch of history used to design or tune a strategy.",
  out_of_sample:"A later stretch of history the strategy never saw while it was designed. The honest test of whether it works.",
  overfitting:  "When a strategy fits past data so closely that it fails on new data.",
  benchmark:    "The yardstick a result is compared with. The point-in-time backtest uses every eligible stock, equal-weighted; some tools use the Nifty 50 price index.",
  nifty:        "The Nifty 50: an index of 50 large Indian companies. The version used here is price-only; it excludes dividends.",

  // ── Optimizer ──
  markowitz:    "The classic mean-variance method (1952) for mixing stocks to balance expected return against risk.",
  mvo:          "Mean-variance optimisation: picks the mix with the best expected return for its risk, using past returns as the estimate.",
  hrp:          "Hierarchical Risk Parity (2016): spreads money by first grouping stocks that move together, then balancing risk across groups.",
  black_litterman: "Starts from the mix implied by each company's market size, then shifts it toward any views supplied.",
  efficient_frontier: "The curve of the best expected return for each level of risk, given the estimates used.",
  equilibrium_weights: "The starting mix implied by each company's size in the market, before any views.",
  max_weight:   "A cap on how much of the portfolio any one stock can be.",
  hedge_ratio_w:"How the optimiser splits money across the chosen stocks.",

  // ── Monte Carlo ──
  monte_carlo:  "Simulating thousands of possible futures to show a range of outcomes rather than one guess.",
  bootstrap:    "A simulation that reshuffles real past returns, so real crashes and calm spells are kept.",
  fat_tails:    "Real markets have more extreme days than a bell curve predicts.",
  percentile:   "A cut-off in the simulated outcomes. The 5th percentile means 5% of simulated futures ended worse.",
  prob_loss:    "The share of simulated futures that ended below the starting value.",

  // ── Pairs trading ──
  pairs_trading:"Buying one stock and short-selling a related one, betting that the gap between them returns to normal.",
  cointegration:"A statistical test of whether two prices have tended to keep a stable long-run gap.",
  hedge_ratio:  "How many shares of one stock are traded against each share of the other so the two sides balance.",
  zscore:       "How stretched the current gap is from its average, in standard deviations.",
  spread:       "The price gap between the two paired stocks.",
  half_life:    "How many days the gap has typically taken to close halfway back to its average.",
  market_neutral:"A position built so that a general market rise or fall affects both sides roughly equally.",
  pvalue:       "If there were no real effect, the chance of seeing a result at least this strong. Below 0.05 is the usual bar.",

  // ── Fama-French ──
  fama_french:  "A model that splits a stock's return into known factors (market, company size, value) to see what is left over.",
  smb:          "Small Minus Big: the return of small companies minus large ones. The size factor.",
  hml:          "High Minus Low: the return of cheap (high book-to-market) stocks minus expensive ones. The value factor.",
  market_beta:  "How much the stock moved with the market in the factor model. About 1 means it tracked the index.",
  r_squared:    "How much of the stock's movement the model explains, from 0 to 1.",
  t_stat:       "How large a result is compared with its noise. Beyond about 2 is usually called significant.",
  significant:  "Unlikely to appear by chance if there were no real effect, usually meaning a p-value below 0.05.",
  factor_exposure:"Return that comes from being a certain type of stock (small, cheap, market-following).",

  // ── Regime ──
  regime:       "The market's mood as the regime model labels it: Bull (rising), Bear (falling) or Sideways.",
  hmm:          "Hidden Markov Model: a statistical model that infers hidden states, here the market's mood, from daily returns.",

  // ── Fundamentals ──
  pe_ratio:     "Price-to-earnings: rupees paid for each rupee of yearly profit.",
  ev_ebitda:    "Company value including debt, divided by operating profit before depreciation. Lets companies with different debt be compared.",
  roe:          "Return on equity: yearly profit as a share of shareholders' money.",
  roa:          "Return on assets: yearly profit as a share of everything the company owns.",
  profit_margin:"The share of each rupee of sales kept as profit.",
  debt_to_equity:"Debt compared with shareholders' money. Higher means more borrowed.",
  piotroski:    "A 0-9 score counting nine yes/no tests of profitability, leverage and efficiency.",
  dupont:       "Splits return on equity into margin, asset efficiency and borrowing, to show where it comes from.",
  market_cap:   "The total value of all the company's shares.",
}

export const LIMITS = {
  alpha_score:  "The combined score has not been tested against future returns.",
  signal:       "A rank today, not a forecast. The labels have no tested track record.",
  confidence:   "Not the chance the ranking is right; a full set of inputs can still give a wrong call.",
  momentum:     "Tested and held on 2011-2026 prices, but not among the largest, most liquid stocks. Can reverse sharply in crashes.",
  quality:      "Our quality score has not been tested; it uses Yahoo's current figures, not the figures as first reported.",
  value:        "Our value score has not been tested. Cheap can stay cheap for good reasons.",
  sentiment:    "Not yet tested against returns. Headlines can report a move that has already happened.",

  sharpe:       "Uses past swings. Says nothing about a crash that has not happened, and treats upside swings as risk.",
  sortino:      "Built from past returns; a short or calm history can make it look far better than it is.",
  calmar:       "Depends heavily on the single worst fall in the window chosen.",
  cagr:         "Hides the path: two investments with the same CAGR can have very different falls along the way.",
  max_drawdown: "Only the worst fall so far; a future fall can be deeper.",
  volatility:   "Counts rises and falls alike, and past swings do not fix future ones.",
  var95:        "Says nothing about how bad the worst 5% of days get beyond the cut-off.",
  cvar95:       "Measured on past days only; the next crash can be worse than any day in the sample.",
  win_days:     "A high share of up days can still lose money if the down days are large.",
  alpha:        "Can be luck, and changes with the benchmark or factors chosen.",
  beta:         "Measured on the past; it shifts over time and in crashes.",
  information_ratio: "Depends on the benchmark chosen and the period measured.",

  backtest:     "Past results do not guarantee future results, and a backtest can be tuned to look good.",
  in_sample:    "Results here are expected to look better than they will later.",
  out_of_sample:"Only honest if the strategy was fixed before this period was examined.",
  overfitting:  "Hard to see from inside a single backtest; testing rules written down in advance help.",
  benchmark:    "A different benchmark can change whether something looks good.",
  nifty:        "Price-only, so it understates the total return an investor would have earned.",

  markowitz:    "Very sensitive to its return estimates, and tends to over-concentrate.",
  mvo:          "Past returns are a poor estimate of future returns, so the chosen mix can be unstable.",
  hrp:          "Still built from past correlations, which can change in a crisis.",
  black_litterman: "Only as good as the views supplied; with none, it stays close to the market's own mix.",
  efficient_frontier: "Drawn from estimates; the real frontier is unknown.",
  equilibrium_weights: "Assumes the market's current prices are a sensible starting point.",
  max_weight:   "A cap limits concentration but does not measure the risk left.",
  hedge_ratio_w:"The split reflects the method's estimates, not a guarantee of balance.",

  monte_carlo:  "Only as realistic as the assumptions fed in; it cannot produce a kind of event it never saw.",
  bootstrap:    "Can only replay history; a crash unlike any in the sample is not represented.",
  fat_tails:    "Knowing tails are fat does not say when the next extreme day comes.",
  percentile:   "A simulated range, not a guaranteed floor or ceiling.",
  prob_loss:    "A share of simulated paths, not a forecast of what will happen.",

  pairs_trading:"The gap can widen further or never close, and shorting can lose more than the stake.",
  cointegration:"A past relationship; it can break, often when it matters most.",
  hedge_ratio:  "Estimated from the past and drifts over time.",
  zscore:       "A stretched gap can keep stretching.",
  spread:       "The gap's past average may not be its future average.",
  half_life:    "An average from the past; the next gap may take far longer to close.",
  market_neutral:"Only roughly neutral; the two sides can still move against each other.",
  pvalue:       "Not the chance the result is true or false. Testing many ideas makes some look significant by luck.",

  fama_french:  "Explains past returns; the leftover can still be luck.",
  smb:          "Near zero in India over 1993-2025 on the IIMA factor library.",
  hml:          "Positive in India over 1993-2025 on the IIMA library, but noisy, with long losing stretches.",
  market_beta:  "Changes over time and depends on the window.",
  r_squared:    "A high value explains the past; it does not make a forecast reliable.",
  t_stat:       "Assumes independent observations; overlapping periods inflate it.",
  significant:  "Not the same as large or useful, and not proof the effect will continue.",
  factor_exposure:"Exposure can change as a stock or portfolio changes.",

  regime:       "The model is fitted on the full history, so past labels use later data; treat them as a description, not a signal.",
  hmm:          "The states are statistical groupings, not official market phases.",

  pe_ratio:     "Yahoo's current figure. Profits can be one-off or about to fall, and a low P/E can be a warning.",
  ev_ebitda:    "Ignores capital spending and tax, which differ a lot between industries.",
  roe:          "Can be inflated by heavy borrowing.",
  roa:          "Hard to compare between banks and other industries.",
  profit_margin:"Differs so much by industry that it is only comparable within one.",
  debt_to_equity:"Normal levels differ by industry; banks run far higher.",
  piotroski:    "Some of the nine tests cannot run when Yahoo lacks the data, so check how many ran before reading the score.",
  dupont:       "Uses reported figures, which can be restated later.",
  market_cap:   "Moves with the share price every day.",
}
