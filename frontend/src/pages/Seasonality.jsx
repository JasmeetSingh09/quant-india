import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ReferenceLine,
} from 'recharts'
import { getSeasonality } from '../api'
import Spinner from '../components/Spinner'

export default function Seasonality() {
  const [ticker, setTicker] = useState('^NSEI')
  const { data: d, isLoading, isError, error } = useQuery({
    queryKey: ['seasonality', ticker],
    queryFn: () => getSeasonality(ticker),
    staleTime: 6 * 3600 * 1000, retry: 0,
  })

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Seasonality — Calendar Effects</h1>
        <p className="text-sm text-gray-400 mt-1 max-w-3xl">
          Average return by calendar month over ~20 years, with a per-month
          significance test and the "Sell in May" (winter vs summer) split. Honest
          about multiple-testing: with 12 months tested, a couple will look
          significant by chance.
        </p>
      </div>

      {isLoading && <div className="card"><Spinner /></div>}
      {isError && <div className="card text-red-400 text-sm">{String(error)}</div>}

      {d && (
        <>
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-white">Average monthly return — {d.ticker}</h3>
              <span className="text-xs text-gray-500">{d.years}y · {d.n_months_observed} months</span>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={d.monthly} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="month" stroke="#6b7280" fontSize={11} />
                <YAxis stroke="#6b7280" fontSize={11} tickFormatter={v => `${v}%`} />
                <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                         formatter={(v, n, p) => [`${v}% avg, ${p.payload.hit_rate_pct}% positive, t=${p.payload.t_stat}`, p.payload.month]} />
                <ReferenceLine y={0} stroke="#4b5563" />
                <Bar dataKey="avg_return_pct" radius={[3, 3, 0, 0]}>
                  {d.monthly.map((m, i) => (
                    <Cell key={i} fill={m.avg_return_pct >= 0
                      ? (m.significant ? '#22c55e' : '#166534')
                      : (m.significant ? '#ef4444' : '#7f1d1d')} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <p className="text-[11px] text-gray-500 mt-1">Solid bars = statistically significant (|t|&gt;1.96). Best: {d.best_month} · Worst: {d.worst_month}.</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="card-sm">
              <p className="stat-label">"Sell in May" — winter − summer</p>
              <p className={`stat-value ${d.sell_in_may.winter_minus_summer_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {d.sell_in_may.winter_minus_summer_pct}%/mo
              </p>
              <p className="text-xs text-gray-500">
                winter {d.sell_in_may.winter_avg_pct}% vs summer {d.sell_in_may.summer_avg_pct}% · t={d.sell_in_may.t_stat}
                {d.sell_in_may.significant ? ' (significant)' : ' (not significant)'}
              </p>
            </div>
            <div className="card-sm">
              <p className="stat-label">Interpretation</p>
              <p className="text-xs text-gray-300 mt-1">{d.interpretation}</p>
            </div>
          </div>

          <p className="text-[11px] text-gray-600">{d.caveat}</p>
        </>
      )}
    </div>
  )
}
