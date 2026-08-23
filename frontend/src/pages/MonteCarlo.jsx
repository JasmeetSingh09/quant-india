import { useState } from 'react'
import usePersistentState from '../usePersistentState'
import { useMutation } from '@tanstack/react-query'
import { runMonteCarlo, compareMonteCarlo, trackEvent } from '../api'
import Spinner from '../components/Spinner'
import PortfolioCoach from '../components/PortfolioCoach'
import Methodology from '../components/Methodology'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend
} from 'recharts'
import { Plus, Trash2, Dices } from 'lucide-react'
import { InfoTip } from '../components/Term'
import Explainer from '../components/Explainer'

const fmt = n => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })

function HoldingsInput({ holdings, setHoldings }) {
  const [ticker, setTicker] = useState('')
  const [pct, setPct] = useState('')
  const total = Object.values(holdings).reduce((a, b) => a + b, 0)
  const add = () => {
    if (!ticker || !pct) return
    const t = ticker.toUpperCase().endsWith('.NS') ? ticker.toUpperCase() : `${ticker.toUpperCase()}.NS`
    setHoldings(h => ({ ...h, [t]: Number(pct) }))
    setTicker(''); setPct('')
  }
  return (
    <div>
      <div className="flex gap-2 mb-2">
        <input className="input" placeholder="Ticker e.g. HDFCBANK" value={ticker}
               onChange={e => setTicker(e.target.value)} onKeyDown={e => e.key==='Enter'&&add()} />
        <input className="input w-24" type="number" placeholder="%" value={pct}
               onChange={e => setPct(e.target.value)} />
        <button onClick={add} className="btn-primary"><Plus size={14}/></button>
      </div>
      <div className="space-y-1">
        {Object.entries(holdings).map(([t, p]) => (
          <div key={t} className="flex items-center justify-between bg-gray-800 rounded px-3 py-1.5">
            <span className="font-mono text-green-400 text-sm">{t.replace('.NS','')}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold">{p}%</span>
              <button onClick={() => setHoldings(h => { const n={...h}; delete n[t]; return n })}
                className="text-gray-600 hover:text-red-400"><Trash2 size={12}/></button>
            </div>
          </div>
        ))}
        {Object.keys(holdings).length > 0 && (
          <p className={`text-xs mt-1 ${Math.abs(total-100)<0.01?'text-green-400':'text-yellow-400'}`}>
            Total: {total.toFixed(1)}% {Math.abs(total-100)<0.01 ? '✓' : '(must equal 100%)'}
          </p>
        )}
      </div>
    </div>
  )
}

export default function MonteCarlo() {
  const [holdings, setHoldings] = usePersistentState('mc.holdings', { 'HDFCBANK.NS': 40, 'TCS.NS': 35, 'RELIANCE.NS': 25 })
  const [capital, setCapital]   = usePersistentState('mc.capital', 100000)
  const [years, setYears]       = usePersistentState('mc.years', 1)
  const [method, setMethod]     = usePersistentState('mc.method', 'bootstrap')
  // A value the user is aiming at. Answered as a share of simulations,
  // never as the chance of reaching it.
  const [target, setTarget]     = usePersistentState('mc.target', '')

  const sim = useMutation({ mutationFn: runMonteCarlo })
  const cmp = useMutation({ mutationFn: compareMonteCarlo })

  const body = () => ({
    holdings, initial_value: Number(capital),
    horizon_days: Math.round(years * 252), n_simulations: 10000, method,
    target_value: target ? Number(target) : null,
  })

  // Both endpoints require allocations to sum to 100% — gate the buttons on it
  // so the user gets a clear hint instead of a silent/blank result.
  const allocTotal = Object.values(holdings).reduce((a, b) => a + Number(b), 0)
  const allocOk = Math.abs(allocTotal - 100) < 0.01

  const d = sim.data
  const fanData = d?.fan_chart?.map(b => ({
    day: b.day, p5: b.p5, p25: b.p25, p50: b.p50, p75: b.p75, p95: b.p95,
    band_low: b.p5, band_mid: b.p50 - b.p5, band_high: b.p95 - b.p50,
  }))

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Dices size={24} className="text-green-400"/> Monte Carlo Simulation</h1>
        <p className="text-gray-400 text-sm mt-0.5">
          10,000 simulated futures — what <em>might</em> happen, not what did. Bootstrap method resamples real NSE history.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Controls */}
        <div className="card col-span-1 space-y-4">
          <div>
            <label className="label">Portfolio</label>
            <HoldingsInput holdings={holdings} setHoldings={setHoldings} />
          </div>
          <div>
            <label className="label">Starting Capital (₹)</label>
            <input className="input" type="number" value={capital} onChange={e => setCapital(e.target.value)} />
          </div>
          <div>
            <label className="label">Horizon: {years} year(s)</label>
            <input type="range" min="0.5" max="10" step="0.5" value={years}
                   onChange={e => setYears(Number(e.target.value))} className="w-full accent-green-500" />
          </div>
          <div>
            <label className="label">Method</label>
            <select className="input" value={method} onChange={e => setMethod(e.target.value)}>
              <option value="bootstrap">Bootstrap (resample real history)</option>
              <option value="t">Fat-tailed (Student's t)</option>
              <option value="normal">Normal distribution</option>
            </select>
          </div>

          <div>
            <label className="label">Target value (optional)</label>
            <input type="number" className="input" placeholder="e.g. 125000"
                   value={target} onChange={e => setTarget(e.target.value)} />
            <p className="text-[10px] text-gray-600 mt-1">
              Answered as the share of simulations that reach it, not the chance it happens.
            </p>
          </div>
          <button className="btn-primary w-full" onClick={() => { trackEvent('montecarlo_run', { n_stocks: Object.keys(holdings).length })
                           sim.mutate(body()) }} disabled={sim.isPending || !allocOk}>
            {sim.isPending ? 'Simulating 10,000 paths…' : 'Run Simulation'}
          </button>
          <button className="btn-ghost w-full" onClick={() => cmp.mutate(body())} disabled={cmp.isPending || !allocOk}>
            {cmp.isPending ? 'Comparing…' : 'Compare All 3 Methods'}
          </button>
          {!allocOk && (
            <p className="text-xs text-yellow-400 text-center">
              Allocations total {allocTotal.toFixed(1)}% — adjust to 100% to run.
            </p>
          )}
        </div>

        {/* Results */}
        <div className="col-span-2 space-y-6">
          {sim.isPending && <div className="card"><Spinner /></div>}
          {sim.isError && <div className="card text-red-400 text-sm">{String(sim.error)}</div>}
          {cmp.isPending && <div className="card"><Spinner /></div>}
          {cmp.isError && <div className="card text-red-400 text-sm">{String(cmp.error)}</div>}

          {d && (
            <>
              {/* Key stats */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="card-sm">
                  <p className="stat-label">Median Outcome</p>
                  <p className="stat-value">{fmt(d.median_value)}</p>
                  <p className={`text-xs mt-0.5 ${d.expected_return_pct>=0?'positive':'negative'}`}>
                    {d.expected_return_pct>0?'+':''}{d.expected_return_pct}%
                  </p>
                </div>
                <div className="card-sm">
                  <p className="stat-label">Paths ending below start<InfoTip k="prob_loss" /></p>
                  <p className="stat-value text-red-400">{d.probability_of_loss_pct}%</p>
                </div>
                <div className="card-sm">
                  <p className="stat-label">Paths that more than doubled</p>
                  <p className="stat-value text-green-400">{d.probability_of_doubling_pct}%</p>
                </div>
                <div className="card-sm">
                  <p className="stat-label">Worst-case (bottom 5%)<InfoTip k="percentile" /></p>
                  <p className="stat-value text-red-400">{fmt(d.percentiles.p5)}</p>
                </div>
              </div>

              {/* Fan chart */}
              <div className="mb-3 rounded-lg border border-gray-700 bg-gray-900/60 p-3">
                <p className="text-[11px] uppercase tracking-widest text-gray-500 mb-1">
                  What this does and does not tell you
                </p>
                <p className="text-xs text-gray-300 leading-relaxed">
                  This is a <b>risk analysis</b> — not a guarantee, and not a
                  personalised investment recommendation.
                </p>
                <p className="text-xs text-gray-400 leading-relaxed mt-1.5">
                  Simulations describe what could have happened under the stated
                  assumptions. They do not predict future returns. Real execution
                  costs, liquidity and bid/ask spreads may differ from the simulation.
                </p>
              </div>

              {/* What the ending value cannot show: how far the path fell on the
                  way. That is the part a person has to sit through, and the part
                  that makes them sell at the bottom. */}
              {d.drawdown?.median_max_drawdown_pct != null && (
                <div className="mb-3">
                  <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
                    How far it fell along the way
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[['Typical worst fall', `${d.drawdown.median_max_drawdown_pct}%`],
                      ['1 in 20 paths fell', `${d.drawdown.p95_max_drawdown_pct}%`],
                      ['Worst path fell', `${d.drawdown.worst_max_drawdown_pct}%`],
                      ['Fell over 20%', `${d.drawdown.share_over_20pct_fall}% of paths`]]
                      .map(([label, val]) => (
                      <div key={label} className="card-sm">
                        <p className="text-[11px] text-gray-500">{label}</p>
                        <p className="text-sm font-mono text-red-400">{val}</p>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-gray-600 mt-1.5 leading-relaxed">
                    {d.drawdown.note}
                  </p>
                </div>
              )}

              {d.target?.share_of_simulations_pct != null && (
                <p className="mb-3 text-xs text-gray-300 leading-relaxed border-l-2 border-gray-700 pl-2.5">
                  {d.target.note}
                </p>
              )}

              <p className="mb-2 text-xs text-gray-400 leading-relaxed">
                Each line is one simulated path. The band shows where most paths
                end up: half finish above {fmt(d.percentiles.p50)}, and in the worst
                one-in-twenty they finish near {fmt(d.percentiles.p5)}. The chart is
                the evidence for those numbers, not a forecast of any one line.
              </p>

              <div className="card">
                <h2 className="font-semibold mb-3">Projected Portfolio Value — Outcome Range</h2>
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={fanData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="day" stroke="#6b7280" fontSize={11}
                           label={{ value: 'Trading Days', position: 'insideBottom', offset: -2, fill: '#6b7280', fontSize: 11 }} />
                    <YAxis stroke="#6b7280" fontSize={11} tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                    <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                             formatter={(v, n) => [fmt(v), n]} />
                    <Area type="monotone" dataKey="p95" stackId="0" stroke="#16a34a" fill="#16a34a" fillOpacity={0.08} name="95th %ile" />
                    <Area type="monotone" dataKey="p75" stackId="1" stroke="#22c55e" fill="#22c55e" fillOpacity={0.12} name="75th %ile" />
                    <Area type="monotone" dataKey="p50" stackId="2" stroke="#eab308" fill="#eab308" fillOpacity={0.18} name="Median" />
                    <Area type="monotone" dataKey="p25" stackId="3" stroke="#f97316" fill="#f97316" fillOpacity={0.12} name="25th %ile" />
                    <Area type="monotone" dataKey="p5"  stackId="4" stroke="#dc2626" fill="#dc2626" fillOpacity={0.08} name="5th %ile" />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </AreaChart>
                </ResponsiveContainer>
                <Explainer>
                  <p><b>What we just did:</b> instead of guessing one future, we rolled the dice
                    <b> 10,000 times</b> — simulating 10,000 possible futures for your portfolio based on
                    how these stocks have actually behaved.</p>
                  <p><b>How to read the chart:</b> the green band is the lucky outcomes, the red band the
                    unlucky ones, and the middle line is the typical (median) result. The wider the spread,
                    the more uncertain your outcome.</p>
                  <p><b>The result:</b> the most likely outcome is around <b>{fmt(d.median_value)}</b>, with
                    <b>{d.probability_of_loss_pct}%</b> of simulated paths finishing below what you put
                    in. The worst 5% of paths ended around <b>{fmt(d.percentiles.p5)}</b>. Those are
                    shares of these simulations under their assumptions, not the chance of it happening.</p>
                </Explainer>
              </div>

              {/* Histogram */}
              <div className="card">
                <h2 className="font-semibold mb-3">Distribution of Final Values ({d.method_label})</h2>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={d.histogram}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="value" stroke="#6b7280" fontSize={10} tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                    <YAxis stroke="#6b7280" fontSize={11} />
                    <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                             formatter={(v) => [`${v} paths`, 'Count']} labelFormatter={v => fmt(v)} />
                    <Bar dataKey="count" fill="#22c55e" fillOpacity={0.6} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}

          {/* Method comparison */}
          {cmp.data && (
            <div className="card">
              <h2 className="font-semibold mb-3">Method Comparison — Tail-Risk Study</h2>
              <div className="table-wrap">
                <table className="w-full min-w-[34rem] text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs border-b border-gray-800">
                    <th className="text-left py-2">Method</th>
                    <th className="text-right">Median</th>
                    <th className="text-right">5% Worst</th>
                    <th className="text-right">1% Worst</th>
                    <th className="text-right">P(Loss)</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(cmp.data.comparison).map(([k, v]) => (
                    <tr key={k} className="border-b border-gray-800 last:border-0">
                      <td className="py-2 text-gray-300">{v.method_label}</td>
                      <td className="text-right font-mono">{fmt(v.median_value)}</td>
                      <td className="text-right font-mono text-orange-400">{fmt(v.p5_worst_case)}</td>
                      <td className="text-right font-mono text-red-400">{fmt(v.worst_case_p1)}</td>
                      <td className="text-right font-mono">{v.probability_of_loss_pct}%</td>
                    </tr>
                  ))}
                </tbody>
                </table>
              </div>
              <div className="mt-3 p-3 bg-yellow-900/20 border border-yellow-800/40 rounded-lg">
                <p className="text-xs text-yellow-300 leading-relaxed">💡 {cmp.data.key_insight}</p>
              </div>
            </div>
          )}

          {!d && !sim.isPending && (
            <div className="card text-center py-16 text-gray-500">
              <Dices size={40} className="mx-auto mb-3 opacity-40" />
              <p className="text-sm">Configure a portfolio and run the simulation.</p>
              <p className="text-xs mt-1">Make sure the backend is running on port 8000.</p>
            </div>
          )}
        </div>
      </div>

      {/* Suggestions + tweakable what-ifs. Holdings here ARE weights, so an
          applied scenario maps directly onto this page's state. */}
      <PortfolioCoach
          focus="risk"
        holdings={holdings}
        initialValue={capital}
        horizonMonths={Math.round(years * 12)}
        onApply={w => setHoldings(w)}
      />
      <Methodology tool="monte_carlo" />
    </div>
  )
}
