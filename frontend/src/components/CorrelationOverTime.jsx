import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from 'recharts'
import { getCorrelationOverTime, getPortfolio } from '../api'
import Spinner from './Spinner'

/**
 * CorrelationOverTime — does diversification hold up when the market falls?
 *
 * One correlation matrix averages calm and stressed months together and hides
 * the moment that matters: holdings that looked unrelated falling together.
 * This shows correlation through time, and calm months against months the
 * Nifty 50 fell 5% or more. It never scores the portfolio or suggests a change.
 * Spec: docs/PROPOSAL_PRODUCT_ADDITIONS_2026-09-23.md (#1).
 */
const PAIR_COLOURS = ['#f59e0b', '#38bdf8', '#a78bfa']
const fmt = v => (v == null ? 'not available' : Number(v).toFixed(2))

export default function CorrelationOverTime() {
  // Ten years by default: over 3 or 5 years the Nifty fell 5% or more in only
  // 3 months to 2026-09, too few for the comparison, which needs 6.
  const [months, setMonths] = useState(120)
  const [custom, setCustom] = useState('')
  const run = useMutation({ mutationFn: getCorrelationOverTime })
  const { data: pf, isLoading: pfLoading } = useQuery({ queryKey: ['portfolio'], queryFn: getPortfolio })

  const saved = (pf?.holdings || []).map(h => h.ticker)
  const typed = custom.split(/[\s,]+/).map(t => t.trim().toUpperCase()).filter(Boolean)
    .map(t => (t.includes('.') || t.startsWith('^') ? t : `${t}.NS`))
  const tickers = typed.length ? typed : saved
  const ready = tickers.length >= 2 && tickers.length <= 15
  const d = run.data

  // One row per month, with the average and each top pair as columns.
  const chart = (d?.rolling_avg_correlation || []).map(r => {
    const row = { month: r.month, average: r.avg_correlation }
    ;(d.top_pairs || []).forEach((p, i) => {
      const hit = p.rolling.find(x => x.month === r.month)
      row[`pair${i}`] = hit?.correlation ?? null
    })
    return row
  })
  const split = d?.calm_vs_falling

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="font-semibold text-sm">Does diversification hold when the market falls?</h2>
        <p className="text-xs text-gray-400 mt-1 leading-relaxed max-w-3xl">
          How closely your holdings moved together, month by month, and whether they moved
          more together in months the Nifty 50 fell 5% or more. Correlation near 1 means they
          rise and fall together; near 0, unrelated.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[16rem]">
          <label className="label">Stocks (leave empty to use your saved Portfolio)</label>
          <input className="input" value={custom} onChange={e => setCustom(e.target.value)}
                 placeholder="e.g. TCS, INFY, HDFCBANK, RELIANCE" />
        </div>
        <div>
          <label className="label">Period</label>
          <select className="input" value={months} onChange={e => setMonths(Number(e.target.value))}>
            {[[36, '3 years'], [60, '5 years'], [120, '10 years']].map(([m, l]) => <option key={m} value={m}>{l}</option>)}
          </select>
        </div>
        <button className="btn-primary text-sm" disabled={!ready || run.isPending || (pfLoading && !typed.length)}
                onClick={() => run.mutate({ tickers, months })}>
          {run.isPending ? 'Measuring…' : 'Measure'}
        </button>
      </div>
      <p className="text-[11px] text-gray-500 font-mono break-words">
        {tickers.length
          ? tickers.map(t => t.replace('.NS', '')).join(' · ')
          : pfLoading ? 'Loading your saved Portfolio…' : 'No stocks yet: type some, or save a Portfolio.'}
        {tickers.length > 15 && <span className="text-red-400"> (at most 15)</span>}
      </p>

      {run.isPending && <Spinner size="sm" />}
      {run.isError && (
        <p className="banner-error text-xs">{run.error?.response?.data?.detail || String(run.error)}</p>
      )}

      {d && (
        <>
          <div>
            <p className="text-xs text-gray-400 mb-1">
              Rolling {d.window_months}-month correlation, {d.first_month} to {d.last_month}
            </p>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={chart} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid stroke="#1f2937" />
                <XAxis dataKey="month" stroke="#6b7280" fontSize={10} minTickGap={30} />
                <YAxis domain={[-1, 1]} stroke="#6b7280" fontSize={10} />
                <ReferenceLine y={0} stroke="#374151" />
                <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 12 }}
                         formatter={v => (v == null ? 'not available' : Number(v).toFixed(2))} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="average" name="Average across all pairs"
                      stroke="#22c55e" strokeWidth={2.5} dot={false} connectNulls={false} />
                {(d.top_pairs || []).map((p, i) => (
                  <Line key={i} type="monotone" dataKey={`pair${i}`}
                        name={p.pair.map(t => t.replace('.NS', '')).join(' / ')}
                        stroke={PAIR_COLOURS[i]} strokeWidth={1.2} strokeDasharray="4 3" dot={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <p className="text-[11px] text-gray-500">Dashed lines: the three most correlated pairs.</p>
          </div>

          {split?.available ? (
            <div className="table-wrap">
              <table className="w-full text-sm min-w-[28rem]">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wide text-gray-500">
                    <th className="text-left py-1">Months</th>
                    <th className="text-right py-1">How many</th>
                    <th className="text-right py-1">Average correlation</th>
                  </tr>
                </thead>
                <tbody>
                  {[['Calm months', split.calm], ['Nifty fell 5% or more', split.falling]].map(([l, g]) => (
                    <tr key={l} className="border-t border-gray-800">
                      <td className="py-1.5">{l}</td>
                      <td className="py-1.5 text-right font-mono">{g.months}</td>
                      <td className="py-1.5 text-right font-mono">
                        {g.avg_correlation == null
                          ? <span className="text-gray-500 text-xs">{g.note || 'not available'}</span>
                          : fmt(g.avg_correlation)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {split.falling.month_list?.length > 0 && (
                <p className="text-[11px] text-gray-500 mt-1">
                  Falling months: {split.falling.month_list.join(', ')}
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-gray-500">{split?.reason}</p>
          )}

          {d.excluded?.length > 0 && (
            <p className="text-[11px] text-amber-200/85">
              Left out: {d.excluded.map(e => `${e.ticker.replace('.NS', '')} (${e.reason})`).join('; ')}.
            </p>
          )}

          <div className="text-[11px] text-gray-400 border-l-2 border-amber-700/70 pl-2.5 space-y-1 leading-relaxed">
            {(d.notes || []).map((n, i) => <p key={i}>{n}</p>)}
          </div>
        </>
      )}
    </div>
  )
}
