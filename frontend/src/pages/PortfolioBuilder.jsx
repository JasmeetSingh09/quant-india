import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { buildPortfolio, startSimulation } from '../api'
import PageHeader from '../components/PageHeader'
import Spinner from '../components/Spinner'
import { Wand2, ShieldCheck, AlertTriangle, PlayCircle } from 'lucide-react'

const RISKS = [
  { key: 'conservative', label: 'Careful',  note: 'Large companies only' },
  { key: 'balanced',     label: 'Balanced', note: 'Large and mid-sized' },
  { key: 'aggressive',   label: 'Bold',     note: 'Mid and small — higher risk' },
]

const rupee = v => v == null ? '—' : `₹${Math.round(v).toLocaleString('en-IN')}`

export default function PortfolioBuilder() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    amount: 100000, horizon_months: 12, max_loss_pct: 20,
    n_stocks: 5, risk: 'balanced',
  })
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const mut = useMutation({ mutationFn: buildPortfolio })
  const r = mut.data

  // Paper-trade the built portfolio. This closes the loop the whole flow exists
  // for: build -> simulate -> change -> simulate again. The simulator takes
  // {ticker: allocation_pct}, which is exactly what the builder returns once
  // the holdings list is folded into a map.
  const [simName, setSimName] = useState('')
  const sim = useMutation({
    mutationFn: () => startSimulation({
      name: (simName || `My portfolio ${new Date().toLocaleDateString('en-IN')}`).trim(),
      holdings: Object.fromEntries(r.holdings.map(h => [h.ticker, h.weight_pct])),
      initial_value: r.inputs.amount,
    }),
    onSuccess: () => navigate('/simulator'),
  })

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-5xl">
      <PageHeader
        title="Build me a portfolio"
        subtitle="Answer five questions and we'll build you a starting point — then show you honestly how much you could lose, and what to change. A way to learn portfolio construction, not a promise of returns."
      />

      <div className="card space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="label">How much do you want to invest?</label>
            <input type="number" min="1000" step="1000" className="input"
                   value={form.amount}
                   onChange={e => set('amount', Number(e.target.value))} />
            <p className="text-[11px] text-gray-600 mt-1">{rupee(form.amount)}</p>
          </div>

          <div>
            <label className="label">How many stocks?</label>
            <input type="range" min="2" max="15" step="1" className="w-full"
                   value={form.n_stocks}
                   onChange={e => set('n_stocks', Number(e.target.value))} />
            <p className="text-[11px] text-gray-600 mt-1">{form.n_stocks} stocks</p>
          </div>

          <div>
            <label className="label">For how long?</label>
            <input type="range" min="3" max="60" step="3" className="w-full"
                   value={form.horizon_months}
                   onChange={e => set('horizon_months', Number(e.target.value))} />
            <p className="text-[11px] text-gray-600 mt-1">
              {form.horizon_months} months
              {form.horizon_months >= 12 && ` (${(form.horizon_months / 12).toFixed(1)} years)`}
            </p>
          </div>

          <div>
            <label className="label">Worst loss you could live with?</label>
            <input type="range" min="5" max="60" step="5" className="w-full"
                   value={form.max_loss_pct}
                   onChange={e => set('max_loss_pct', Number(e.target.value))} />
            <p className="text-[11px] text-gray-600 mt-1">
              Down {form.max_loss_pct}% — about {rupee(form.amount * (1 - form.max_loss_pct / 100))} left
            </p>
          </div>
        </div>

        <div>
          <label className="label">What kind of investor are you?</label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {RISKS.map(o => (
              <button key={o.key} onClick={() => set('risk', o.key)}
                className={`text-left px-3 py-2 rounded-lg border transition-colors ${
                  form.risk === o.key
                    ? 'border-green-600 bg-green-600/10 text-green-300'
                    : 'border-gray-700 hover:border-gray-600 text-gray-300'}`}>
                <span className="block text-sm font-medium">{o.label}</span>
                <span className="block text-[11px] text-gray-500">{o.note}</span>
              </button>
            ))}
          </div>
        </div>

        <button onClick={() => mut.mutate(form)} disabled={mut.isPending}
                className="btn-primary flex items-center gap-2">
          <Wand2 size={15} />{mut.isPending ? 'Building…' : 'Build my portfolio'}
        </button>

        {mut.isError && <p className="banner-error">{String(mut.error)}</p>}
      </div>

      {mut.isPending && <div className="card"><Spinner /></div>}

      {r && (
        <>
          {/* The verdict leads — it is the reason this flow exists */}
          <div className={r.meets_loss_limit ? 'banner-warn !border-green-800/60 !bg-green-950/40 !text-green-300' : 'banner-error'}>
            {r.meets_loss_limit ? <ShieldCheck size={18} className="shrink-0" />
                                : <AlertTriangle size={18} className="shrink-0" />}
            <span>{r.verdict}</span>
          </div>

          <div className="card space-y-4">
            <div className="flex items-baseline justify-between flex-wrap gap-2">
              <h2 className="font-semibold">Your {r.profile.label.toLowerCase()} portfolio</h2>
              <span className="text-xs text-gray-500">{r.profile.why}</span>
            </div>

            <div className="table-wrap">
              <table className="w-full min-w-[30rem] text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs border-b border-gray-800">
                    <th className="text-left py-2 font-medium">Stock</th>
                    <th className="text-right font-medium">Weight</th>
                    <th className="text-right font-medium">Amount</th>
                    <th className="text-right font-medium">Alpha</th>
                  </tr>
                </thead>
                <tbody>
                  {r.holdings.map(h => (
                    <tr key={h.ticker}
                        onClick={() => navigate(`/stock?ticker=${encodeURIComponent(h.ticker)}`)}
                        className="border-b border-gray-900 last:border-0 cursor-pointer hover:bg-gray-800/50">
                      <td className="py-2 font-mono">{h.name}</td>
                      <td className="text-right font-mono">{h.weight_pct}%</td>
                      <td className="text-right font-mono">{rupee(h.amount)}</td>
                      <td className={`text-right font-mono ${h.alpha_score >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {h.alpha_score > 0 ? '+' : ''}{Math.round(h.alpha_score)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-gray-600">Weighted by {r.profile.weighting}.</p>
          </div>

          {r.outcome && (
            <div className="card">
              <h2 className="font-semibold mb-1">What could happen in {r.inputs.horizon_months} months</h2>
              <p className="text-xs text-gray-500 mb-4">
                From 5,000 simulations using this portfolio's own history.
              </p>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="card-sm">
                  <p className="stat-label">Typical outcome</p>
                  <p className="stat-value">{rupee(r.outcome.median_value)}</p>
                </div>
                <div className="card-sm">
                  <p className="stat-label">Bad case (worst 5%)</p>
                  <p className="stat-value text-red-400">{rupee(r.outcome.p5_value)}</p>
                </div>
                <div className="card-sm">
                  <p className="stat-label">Good case (best 5%)</p>
                  <p className="stat-value text-green-400">{rupee(r.outcome.p95_value)}</p>
                </div>
                <div className="card-sm">
                  <p className="stat-label">Chance of a loss</p>
                  <p className="stat-value">{r.outcome.probability_of_loss_pct}%</p>
                </div>
              </div>
            </div>
          )}

          {/* Paper-trade it — the next step, not an afterthought */}
          <div className="card space-y-3">
            <div>
              <h2 className="font-semibold">Try it with fake money</h2>
              <p className="text-xs text-gray-500 mt-1">
                Track this portfolio against real prices without risking anything.
                Come back in a week and see what actually happened.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                className="input sm:flex-1"
                placeholder="Name it — e.g. My first portfolio"
                value={simName}
                onChange={e => setSimName(e.target.value)}
              />
              <button onClick={() => sim.mutate()} disabled={sim.isPending}
                      className="btn-primary flex items-center justify-center gap-2 shrink-0">
                <PlayCircle size={15} />
                {sim.isPending ? 'Starting…' : 'Paper-trade this'}
              </button>
            </div>
            {sim.isError && <p className="banner-error">{String(sim.error)}</p>}
          </div>

          <p className="text-[11px] text-gray-600">{r.disclaimer}</p>
        </>
      )}
    </div>
  )
}
