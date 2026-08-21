import { useNavigate } from 'react-router-dom'
import {
  Zap, Wand2, Shuffle, Lightbulb, SlidersHorizontal, PlayCircle, History, LineChart,
} from 'lucide-react'

// Written as steps a user takes, not tools we own. The old list named the
// machinery ("4-Factor Alpha Model", "FinBERT Sentiment"), which sold a
// stock-picking edge the track record does not support. Same technology
// underneath — described by what it lets someone learn.
const FEATURES = [
  { icon: Wand2, title: '1. Build a portfolio in five answers',
    desc: 'Tell us how much, for how long, and the worst loss you could live with. You get real NSE stocks with sensible position sizes — a starting point to learn from, not a tip sheet.' },
  { icon: Shuffle, title: '2. See what could actually happen',
    desc: 'Thousands of simulated futures from years of real NSE history. Typical outcome, best case, and the one that matters: how bad the worst 5% looks.' },
  { icon: Lightbulb, title: '3. Find out what is wrong with it',
    desc: 'Every warning cites the number behind it — "this stock is 55% of your money", "these two move together 0.85, so they are one bet, not two".' },
  { icon: SlidersHorizontal, title: '4. Change it and watch the effect',
    desc: 'Cut concentration, add or drop a stock, hold for longer. Each change shows what it does to BOTH your expected return and your worst case — because most improvements are trades, not free wins.' },
  { icon: PlayCircle, title: '5. Paper-trade it, risk-free',
    desc: 'Track your portfolio against real prices with no real money. Come back in a week and find out what actually happened.' },
  { icon: History, title: 'And we show our own scorecard',
    desc: "Our model's past calls are published with their real returns — including the periods where it has not demonstrated a statistically significant edge. Nobody else does this, and it is the reason you can trust the other numbers." },
]

export default function Landing() {
  const navigate = useNavigate()
  const goSignIn = () => navigate('/login')

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-4 max-w-6xl mx-auto">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center">
            <Zap size={15} className="text-white" />
          </div>
          <span className="font-bold text-white tracking-tight">Quant India</span>
        </div>
        <button onClick={goSignIn} className="btn-primary text-sm">Sign in</button>
      </header>

      {/* Hero */}
      <section className="max-w-3xl mx-auto text-center px-6 pt-16 pb-12">
        <p className="text-xs font-semibold tracking-widest text-green-400 uppercase mb-4">
          Quantitative portfolio research for the NSE
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight">
          The maths quant desks use, on all 2,400 NSE stocks
        </h1>
        <p className="mt-5 text-lg text-gray-400">
          A four-factor alpha model scoring the entire NSE daily. Nine portfolio
          optimisers — Markowitz, Black-Litterman, HRP, Min-CVaR. Monte Carlo,
          GARCH volatility, Fama-French factors and a three-state regime model.
          Build a portfolio with them, see exactly what could go wrong, and
          paper-trade it before risking a rupee.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <button onClick={goSignIn} className="btn-primary">Get started — it's free</button>
          <a href="#features" className="btn-ghost">See what's inside</a>
        </div>
        <p className="mt-4 text-xs text-gray-600">Signals &amp; research only — not financial advice.</p>
      </section>

      {/* Hard numbers. Each one is verifiable in the app or the repo — this is
          the technical credibility the honest positioning has to sit on. */}
      <section className="max-w-6xl mx-auto px-6 pt-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            ['2,401', 'NSE stocks scored daily'],
            ['9', 'portfolio optimisers'],
            ['168,389', 'test assertions passing'],
            ['4', 'factors per alpha score'],
          ].map(([n, l]) => (
            <div key={l} className="card-sm text-center">
              <p className="text-2xl font-bold font-mono text-green-400">{n}</p>
              <p className="text-[11px] text-gray-500 mt-1">{l}</p>
            </div>
          ))}
        </div>
      </section>


      {/* Features */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-12">
        <div className="text-center mb-8">
          <h2 className="text-2xl sm:text-3xl font-bold text-white">How it works</h2>
          <p className="text-gray-400 mt-2">
            Five steps, about ten minutes, no money at risk.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="card space-y-3">
              <div className="w-9 h-9 rounded-lg bg-green-600/15 flex items-center justify-center">
                <Icon size={18} className="text-green-400" />
              </div>
              <h3 className="font-semibold text-white">{title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Under the hood */}
      <section className="max-w-6xl mx-auto px-6 py-12">
        <div className="text-center mb-8">
          <h2 className="text-2xl sm:text-3xl font-bold text-white">Under the hood</h2>
          <p className="text-gray-400 mt-2">
            Textbook methods, implemented and tested — not a black box.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            ['Alpha model', 'Momentum (12-1, volatility-adjusted), quality (Piotroski F-score, ROE, FCF yield), value (P/E and P/B z-scores vs peers) and FinBERT news sentiment — combined into one score with every contribution shown.'],
            ['Portfolio optimisation', 'Markowitz mean-variance with Ledoit-Wolf shrinkage, Black-Litterman with He-Litterman equilibrium, Hierarchical Risk Parity, Equal Risk Contribution, Maximum Diversification and Min-CVaR via linear programming.'],
            ['Risk & simulation', 'Monte Carlo by normal, Student-t, i.i.d. and block bootstrap. VaR and CVaR, GARCH(1,1) volatility forecasting, risk decomposition by contribution, and Kelly-based position sizing.'],
            ['Factor research', 'Fama-French three-factor regressions with t-stats, cointegration testing for pairs, seasonality studies and a three-state Gaussian HMM for market regime.'],
            ['Options', 'Black-Scholes-Merton pricing with the full Greeks and risk-neutral probabilities — verified against the textbook case at 10.4506 versus 10.45.'],
            ['Honesty by construction', 'Momentum backtested point-in-time: a 23%/yr edge collapsed to 11.7% (t 3.78 to 1.50) once survivorship was removed. We publish the corrected number, and the live scorecard, including where the model has not demonstrated a statistically significant edge.'],
          ].map(([title, desc]) => (
            <div key={title} className="card space-y-2">
              <h3 className="font-semibold text-white text-sm">{title}</h3>
              <p className="text-xs text-gray-400 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>


      {/* Closing CTA */}
      <section className="max-w-3xl mx-auto text-center px-6 py-16">
        <div className="flex items-center justify-center gap-2 text-green-400 mb-4">
          <LineChart size={20} />
        </div>
        <h2 className="text-2xl font-bold text-white">Build a private watchlist, portfolio &amp; get alerts</h2>
        <p className="mt-3 text-gray-400">
          Create a free account to track your holdings, run simulations, and receive
          price &amp; sentiment alerts by email.
        </p>
        <button onClick={goSignIn} className="btn-primary mt-6">Create your account</button>
      </section>

      <footer className="border-t border-gray-800 py-6 text-center text-xs text-gray-600">
        Quant India · Data via NSE &amp; NewsAPI · Not financial advice
      </footer>
    </div>
  )
}
