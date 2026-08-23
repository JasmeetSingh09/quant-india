import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFactorDivergence } from '../api'
import Spinner from './Spinner'

/**
 * FactorChange — what moved, and what did not.
 *
 * This is deliberately not a score. A single composite number would imply
 * the app can tell which changes matter, and it cannot: the one factor tested
 * end to end here, momentum, did not survive walk-forward. So this reports the
 * change and stops, which is a claim the data actually supports.
 *
 * The empty states matter more than the populated one. History only starts
 * accumulating from the first scan after this shipped and cannot be
 * backfilled, so for a while most stocks will have nothing to show. Rendering
 * zeros in that case would say "nothing is changing" when the truth is "we
 * have not been watching long enough" — opposite claims, and the wrong one is
 * the reassuring one.
 */
const WINDOWS = [7, 30, 90]

const arrow = c => c > 0.5 ? '↑' : c < -0.5 ? '↓' : '→'
const tone = c => c > 0.5 ? 'text-green-400' : c < -0.5 ? 'text-red-400' : 'text-gray-500'
const pretty = f => f.replace(/_/g, ' ')

export default function FactorChange({ ticker }) {
  const [days, setDays] = useState(30)
  const { data, isLoading } = useQuery({
    queryKey: ['factorChange', ticker, days],
    queryFn: () => getFactorDivergence(ticker, days),
    enabled: !!ticker,
    staleTime: 10 * 60 * 1000,
    retry: false,
  })

  if (!ticker) return null
  if (isLoading) return <div className="card"><Spinner size="sm" /></div>
  if (!data) return null

  const notReady = data.status === 'no_history' || data.status === 'too_short'
  const factors = Object.entries(data.factors || {})
    .sort(([, a], [, b]) => Math.abs(b.change) - Math.abs(a.change))

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">What&rsquo;s changing?</h2>
        <div className="flex gap-1">
          {WINDOWS.map(w => (
            <button key={w} onClick={() => setDays(w)}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                days === w ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'}`}>
              {w}d
            </button>
          ))}
        </div>
      </div>

      {/* "We haven't been watching long enough" is a different statement from
          "nothing is happening", and it is the honest one right now. */}
      {notReady && (
        <p className="text-xs text-gray-500 leading-relaxed">
          {data.note}
        </p>
      )}

      {data.status === 'ok' && (
        <>
          <div className="space-y-1">
            {factors.map(([name, d]) => (
              <div key={name} className="flex items-center gap-2 text-xs">
                <span className="w-24 shrink-0 text-gray-400 capitalize">{pretty(name)}</span>
                <span className={`w-6 text-center ${tone(d.change)}`}>{arrow(d.change)}</span>
                <span className={`font-mono w-12 text-right ${tone(d.change)}`}>
                  {d.change > 0 ? '+' : ''}{d.change}
                </span>
                <span className="font-mono text-gray-600 text-[11px]">
                  {d.from} → {d.to}
                </span>
              </div>
            ))}
          </div>

          {data.price_change_pct != null && (
            <p className="text-xs text-gray-400 border-t border-gray-800 pt-2">
              Price over the same period:{' '}
              <span className={`font-mono ${tone(data.price_change_pct)}`}>
                {data.price_change_pct > 0 ? '+' : ''}{data.price_change_pct}%
              </span>
            </p>
          )}

          {data.divergences?.length > 0 && (
            <div className="space-y-2">
              {data.divergences.map((dv, i) => (
                <div key={i} className="p-2.5 rounded-lg border border-blue-900/60 bg-blue-950/20">
                  <p className="text-xs font-medium text-blue-200">{dv.label}</p>
                  <p className="text-[11px] text-gray-400 mt-0.5 leading-relaxed">{dv.detail}</p>
                </div>
              ))}
              <p className="text-[11px] text-gray-500 leading-relaxed">
                {data.why_excluded}
              </p>
            </div>
          )}

          {data.divergences?.length === 0 && (
            <p className="text-xs text-gray-500">
              Nothing is moving far enough out of step to be worth pointing at.
            </p>
          )}

          {data.window_note && (
            <p className="text-[11px] text-gray-500">{data.window_note}</p>
          )}

          {/* The label that keeps this a research tool. */}
          <p className="text-[11px] text-amber-200/80 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
            {data.not_a_signal}
          </p>
        </>
      )}
    </div>
  )
}
