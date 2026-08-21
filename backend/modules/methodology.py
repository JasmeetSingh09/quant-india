"""
methodology.py — what each tool computes, on what data, under what assumptions,
and what you must NOT conclude from it.

The risk this module exists to address is not lack of sophistication. The app
already has Sharpe, CVaR, HRP, Black-Litterman, Monte Carlo, drawdown, regime
detection and a factor model. The risk is FALSE sophistication: a dashboard can
look thoroughly quantitative while its assumptions stay invisible, and invisible
assumptions are how a number gets trusted further than it deserves.

So every major tool answers the same four questions in the same order, and the
fourth is the one that matters most. Anything the tool cannot support is stated
as a limitation rather than left for a reader to discover — including the
limitations that are unflattering, of which there are several here.

Written as data rather than prose scattered through components so that a claim
lives in exactly one place and cannot drift out of step with the code.
"""

TOOLS = {
    "realtime_simulator": {
        "name": "Paper trading (real-time)",
        "calculates": (
            "The value of a hypothetical portfolio you construct, marked to the "
            "latest available price, and its gain or loss versus the capital you "
            "put in."),
        "data": (
            "Yahoo Finance quotes, with NSE's official end-of-day bhavcopy as "
            "fallback. Quotes are not guaranteed to be live — Yahoo's NSE feed is "
            "typically delayed, so treat prices as recent rather than real-time."),
        "assumes": [
            "Your order fills instantly at the displayed price, in full.",
            "Brokerage, STT, stamp duty, exchange and GST are deducted at "
            "published rates, and price impact is estimated from the stock's own "
            "daily traded value. Whole shares only — the remainder stays as "
            "uninvested cash.",
            "There is a real cash balance. Deposits, withdrawals and sale "
            "proceeds all move through it, buying with existing cash refuses to "
            "overspend, and money that could not buy a whole share stays "
            "uninvested rather than vanishing. Uninvested cash counts toward "
            "portfolio value, so idle money shows up as drag exactly as it "
            "would in a real account.",
            "Dividends ARE credited as cash since the purchase date, so this "
            "reports total return and agrees with the historical backtest. They "
            "are not reinvested, because cash landing in an account is what "
            "actually happens.",
        ],
        "do_not_conclude": (
            "That these returns are achievable exactly. Costs and estimated impact "
            "are now deducted, but there is no order book here — the fill price is "
            "modelled, not quoted, and no bid/ask spread is charged. Treat the "
            "figure as close, not exact."),
    },

    "historic_simulator": {
        "name": "Historical backtest",
        "calculates": (
            "How a portfolio you specify would have performed over a past period, "
            "rebalanced at your chosen frequency, split into in-sample and "
            "out-of-sample halves."),
        "data": (
            "Split- and dividend-adjusted daily closes from Yahoo over the "
            "requested window."),
        "assumes": [
            "Indian transaction costs ARE deducted on rebalance dates — brokerage "
            "0.10%, slippage 0.05%, STT 0.10%, stamp duty 0.015%.",
            "The stock existed and was tradeable for the whole period. Companies "
            "that were delisted, merged or went bankrupt are absent from the "
            "universe entirely, which flatters any historical result — this is "
            "survivorship bias and it is not corrected here.",
            "Fills happen at the quoted price regardless of size, but holdings "
            "that would be a large share of their own daily turnover are now "
            "flagged with the figure — so a backtest that could not have been "
            "executed says so instead of reporting a clean return.",
            "You chose these stocks without knowing what happened next. The app "
            "cannot enforce that, and picking names you already know did well is "
            "the easiest way to produce a meaningless backtest.",
        ],
        "do_not_conclude": (
            "That a good backtest predicts a good future. It uses no fundamentals, "
            "so there is no point-in-time data problem — but survivorship bias and "
            "your own hindsight both remain, and both push results the same way: "
            "too good."),
    },

    "optimizer": {
        "name": "Portfolio optimiser",
        "calculates": (
            "Weights that are optimal for a stated objective — maximum Sharpe, "
            "minimum variance, risk parity, maximum diversification or minimum "
            "CVaR — given estimates of return and risk."),
        "data": (
            "Historical daily returns over the lookback window. Covariance uses "
            "Ledoit-Wolf shrinkage; Black-Litterman uses He-Litterman priors."),
        "assumes": [
            "Past returns and correlations are informative about future ones. They "
            "are the only estimates available and they are not stable — correlations "
            "in particular converge in a crisis, exactly when diversification is "
            "supposed to help.",
            "Expected returns come from history unless you supply views. Optimisers "
            "are famously sensitive to this input: a difference of a fraction of a "
            "percent in expected return can swing weights dramatically, which is why "
            "shrinkage and weight caps exist.",
            "A turnover penalty is available and off by default, so suggested "
            "weights ignore the cost of trading into them unless you enable it.",
            "Per-stock and per-sector caps are both available. They stop "
            "different things: capping each stock at 10% still permits a "
            "portfolio that is 90% financials.",
            "Black-Litterman starts from the market's own implied returns and "
            "shifts them toward your 'views' — a view being a statement that one "
            "stock will beat another by some amount. The confidence slider "
            "decides how far the weights move toward that view; at zero "
            "confidence you get the market portfolio back.",
        ],
        "do_not_conclude": (
            "That this is THE optimal portfolio. It is optimal for one objective "
            "under one set of estimates. Change the window or the objective and the "
            "weights change — sometimes a lot. Treat large single-stock weights as a "
            "warning about the estimates, not a conviction signal."),
    },

    "monte_carlo": {
        "name": "Monte Carlo simulation",
        "calculates": (
            "A distribution of possible portfolio values at your horizon, by "
            "simulating thousands of return paths and reporting percentiles."),
        "data": (
            "Historical daily returns for your holdings, weighted as you specified."),
        "assumes": [
            "The method you chose: normal returns, Student-t (fatter tails), i.i.d. "
            "bootstrap (resamples history, no serial structure), or block bootstrap "
            "(resamples runs of days, preserving some volatility clustering).",
            "Volatility and correlation stay as they were over the lookback. Real "
            "markets change regime; a simulation drawn from a calm period will "
            "understate a turbulent one.",
            "Each path is a draw from the past, not a forecast of the future.",
            "Correlations between your holdings are whatever they were over the "
            "lookback, and are held there. This matters most exactly when it is "
            "least true: correlations converge toward 1 in a crash, so a "
            "diversified portfolio behaves like a concentrated one on the days "
            "the simulation is supposed to be warning you about.",
        ],
        "do_not_conclude": (
            "That the 5th percentile is your worst case. It is the worst case IN "
            "THIS SIMULATION, under these assumptions. Real outcomes have been worse "
            "than models like this expected, repeatedly and famously."),
    },

    "coach": {
        "name": "Portfolio coach",
        "calculates": (
            "Specific, measurable problems in a portfolio: concentration of money, "
            "concentration of risk, sector overlap, correlated holdings, illiquid "
            "positions, simulated downside, and performance versus the index."),
        "data": (
            "Your weights, the latest universe scan's alpha scores, 400 days of "
            "returns for risk and correlation, bhavcopy volume for liquidity."),
        "assumes": [
            "Every finding cites the number that triggered it. Nothing here is "
            "generated prose about 'considering diversification'.",
            "Rules of thumb are rules of thumb: 40% in one stock and 5 holdings are "
            "reasonable thresholds, not laws.",
        ],
        "do_not_conclude": (
            "That this portfolio is right or wrong FOR YOU. The app does not know "
            "your horizon, your income, your other assets or what you would do in a "
            "40% drawdown. It can measure that a portfolio is concentrated or "
            "volatile. It cannot tell you whether that is appropriate."),
    },

    "alpha_model": {
        "name": "Alpha model and signals",
        "calculates": (
            "A composite score from -100 to +100 combining momentum (35%), "
            "sentiment (25%), quality (25%) and value (15%), mapped to a signal."),
        "data": (
            "Prices for momentum, FinBERT on recent headlines for sentiment, "
            "reported fundamentals for quality and value."),
        "assumes": [
            "Current fundamentals, not point-in-time. Fine for a signal issued "
            "today; it is why the model is not used to generate historical signals, "
            "and why only momentum can be walk-forward tested at all.",
            "A roughly 21-trading-day horizon.",
            "Data coverage measures how many inputs were available — not the "
            "probability the call is right.",
        ],
        "do_not_conclude": (
            "That a high score predicts a return. Momentum — the only factor "
            "tested on this universe — has not demonstrated a statistically "
            "significant edge in our tested configurations. This does not prove "
            "that momentum cannot work; it means those configurations did not "
            "provide sufficient evidence of predictive power. The score expresses "
            "the model's preference; the track record is the only evidence about "
            "whether that preference is worth anything, and it is not yet "
            "conclusive either."),
    },
}


def for_tool(key: str) -> dict | None:
    t = TOOLS.get(key)
    if not t:
        return None
    return {"tool": key, **t,
            "four_questions": ["What does it calculate?", "What data does it use?",
                               "What does it assume?", "What should I not conclude?"]}


def all_tools() -> dict:
    return {"tools": {k: for_tool(k) for k in TOOLS},
            "why": ("Stated so the assumptions are visible. A dashboard can look "
                    "thoroughly quantitative while its assumptions stay hidden, and "
                    "hidden assumptions are how a number gets trusted further than "
                    "it deserves.")}
