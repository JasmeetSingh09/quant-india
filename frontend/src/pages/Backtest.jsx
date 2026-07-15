import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { getMomentumBacktest, getLowVolBacktest } from '../api'
import Spinner from '../components/Spinner'

function Row({ label, strat, bench, fmt = v => v }) {
  return (
    <tr className="border-t border-gray-800">
      <td className="py-2 text-gray-400">{label}</td>
      <td className="py-2 text-right text-white font-medium">{fmt(strat)}</td>
      <td className="py-2 text-right text-gray-300">{fmt(bench)}</td>
    </tr>
  )
}

export default function Backtest() {
  const [top, setTop] = useState(0.2)
  const [factor, setFactor] = useState('momentum')   // 'momentum' | 'lowvol'
  const { data: d, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['factorBacktest', factor, top],
    queryFn: () => (factor === 'lowvol' ? getLowVolBacktest(top) : getMomentumBacktest(top)),
    staleTime: 6 * 3600 * 1000,
    retry: 0,
  })

  const s = d?.strategy_stats, b = d?.benchmark_stats

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Factor Backtest — Honest Out-of-Sample</h1>
        <p className="text-sm text-gray-400 mt-1 max-w-3xl">
          A walk-forward test of a single factor ({factor === 'lowvol' ? 'low volatility' : '12-1 momentum'})
          on an NSE universe, benchmarked against the Nifty. No look-ahead (every position is
          chosen before the return it earns), transaction costs included, with a
          significance t-test. The result is reported as-is — including when there's
          no edge.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <label className="text-sm text-gray-400">Factor</label>
        <select className="input" value={factor} onChange={e => setFactor(e.target.value)}>
          <option value="momentum">Momentum (12-1)</option>
          <option value="lowvol">Low volatility</option>
        </select>
        <label className="text-sm text-gray-400">{factor === 'lowvol' ? 'Hold lowest' : 'Hold top'}</label>
        <select className="input" value={top} onChange={e => setTop(Number(e.target.value))}>
          <option value={0.1}>10%</option>
          <option value={0.2}>20%</option>
          <option value={0.3}>30%</option>
        </select>
        <button className="btn-ghost text-sm" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? 'Running…' : 'Re-run'}
        </button>
        <span className="text-xs text-gray-500">First run downloads the universe — up to a minute.</span>
      </div>

      {isLoading && <div className="card"><Spinner /><p className="text-xs text-gray-500 mt-2 text-center">Running walk-forward backtest…</p></div>}
      {isError && <div className="card text-red-400 text-sm">{String(error)} — the data source may be busy; try Re-run.</div>}

      {d && s && b && (
        <>
          {/* Verdict banner */}
          <div className={`card border ${d.significant_5pct && d.excess_cagr_pct > 0
              ? 'border-green-700/50 bg-green-950/30' : 'border-gray-700 bg-gray-900/40'}`}>
            <p className="text-sm text-gray-200">{d.verdict}</p>
            <p className="text-xs text-gray-500 mt-2">
              {d.strategy} · {d.period} · {d.universe_size} stocks · costs {d.cost_roundtrip_pct}% round-trip
            </p>
          </div>

          <div className="grid grid-cols-3 gap-6">
            {/* Stats table */}
            <div className="card col-span-1">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 uppercase">
                    <th className="text-left font-medium">Metric</th>
                    <th className="text-right font-medium">Momentum</th>
                    <th className="text-right font-medium">Nifty</th>
                  </tr>
                </thead>
                <tbody>
                  <Row label="CAGR" strat={s.cagr_pct} bench={b.cagr_pct} fmt={v => `${v}%`} />
                  <Row label="Volatility" strat={s.vol_pct} bench={b.vol_pct} fmt={v => `${v}%`} />
                  <Row label="Sharpe" strat={s.sharpe} bench={b.sharpe} />
                  <Row label="Sortino" strat={s.sortino} bench={b.sortino} />
                  <Row label="Max drawdown" strat={s.max_drawdown_pct} bench={b.max_drawdown_pct} fmt={v => `${v}%`} />
                  <Row label="Hit rate" strat={s.hit_rate_pct} bench={b.hit_rate_pct} fmt={v => `${v}%`} />
                </tbody>
              </table>
              <div className="mt-4 pt-3 border-t border-gray-800 text-xs space-y-1">
                <p className="text-gray-400">Excess CAGR: <span className="text-white">{d.excess_cagr_pct}%/yr</span></p>
                <p className="text-gray-400">Monthly excess t-stat: <span className={Math.abs(d.t_stat_excess) > 1.96 ? 'text-green-400' : 'text-gray-300'}>{d.t_stat_excess}</span> {d.significant_5pct ? '(significant)' : '(not significant)'}</p>
              </div>
            </div>

            {/* Equity curve */}
            <div className="card col-span-2">
              <h3 className="text-sm font-semibold text-white mb-2">Growth of ₹1 (net of costs)</h3>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={d.equity_curve} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="date" stroke="#6b7280" fontSize={10} minTickGap={40} />
                  <YAxis stroke="#6b7280" fontSize={11} tickFormatter={v => `₹${v.toFixed(1)}`} />
                  <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                           formatter={v => `₹${Number(v).toFixed(3)}`} />
                  <Legend />
                  <Line type="monotone" dataKey="strategy" name="Momentum" stroke="#22c55e" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="nifty" name="Nifty" stroke="#9ca3af" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Caveats — the honesty */}
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-300 mb-2">Honest caveats</h3>
            <ul className="text-xs text-gray-500 space-y-1 list-disc pl-4">
              {d.caveats.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
