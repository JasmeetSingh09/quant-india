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
    desc: "Our model's past calls are published with their real returns — including the periods where it showed no edge at all. Nobody else does this, and it is the reason you can trust the other numbers." },
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
          Learn investing by doing it
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight">
          Build a portfolio. See what could go wrong. Learn why.
        </h1>
        <p className="mt-5 text-lg text-gray-400">
          Quant India is a free learning tool for Indian investors. Build an NSE
          portfolio, simulate thousands of possible futures, find out how much you
          could actually lose, and paper-trade it with no real money at risk —
          using the same maths real quant desks use, explained in plain English.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <button onClick={goSignIn} className="btn-primary">Get started — it's free</button>
          <a href="#features" className="btn-ghost">See what's inside</a>
        </div>
        <p className="mt-4 text-xs text-gray-600">Signals &amp; research only — not financial advice.</p>
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
