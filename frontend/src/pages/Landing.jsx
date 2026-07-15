import { useNavigate } from 'react-router-dom'
import {
  Zap, TrendingUp, Brain, BarChart3, Shuffle, ShieldCheck, Newspaper, LineChart,
} from 'lucide-react'

const FEATURES = [
  { icon: TrendingUp, title: '4-Factor Alpha Model', desc: 'Momentum, quality, value and news sentiment combined into one transparent score — with a breakdown of what drives every call.' },
  { icon: Brain,      title: 'FinBERT Sentiment',    desc: 'A finance-tuned language model reads Indian market news and scores it, so sentiment is measured, not guessed.' },
  { icon: BarChart3,  title: 'Portfolio Optimiser',  desc: 'Markowitz, Black-Litterman and Hierarchical Risk Parity — build portfolios the way quant desks actually do.' },
  { icon: Shuffle,    title: 'Monte Carlo',          desc: '10,000 simulated futures from real NSE history: see the odds of loss, doubling, and worst-case drawdowns.' },
  { icon: ShieldCheck,title: 'Risk Analytics',       desc: 'Kelly sizing, volatility targeting and deflated Sharpe — position sizing that protects you from ruin.' },
  { icon: Newspaper,  title: 'Macro & Market News',  desc: 'Live NSE, macro and commodities news with sector-impact tagging, right next to your holdings.' },
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
          Quant tools for Indian markets
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight">
          Institutional-grade stock intelligence for the NSE
        </h1>
        <p className="mt-5 text-lg text-gray-400">
          Quant India brings the toolkit real quant desks use — a factor alpha model,
          FinBERT news sentiment, portfolio optimisation, Monte Carlo simulation and
          risk analytics — to Indian retail investors, explained in plain English.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <button onClick={goSignIn} className="btn-primary">Get started — it's free</button>
          <a href="#features" className="btn-ghost">See what's inside</a>
        </div>
        <p className="mt-4 text-xs text-gray-600">Signals &amp; research only — not financial advice.</p>
      </section>

      {/* Features */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-12">
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
