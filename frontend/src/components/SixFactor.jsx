import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getAlphaV2 } from '../api'
import Spinner from './Spinner'

/**
 * SixFactor — the model's reasoning, readable in about fifteen seconds.
 *
 * A row of six numbers asks the reader to do the synthesis themselves, and most
 * will not: they will read the headline score and stop. So the sentence comes
 * first, the bars support it, and the methodology waits behind a click for the
 * people who want it.
 *
 * Every factor is scored against its OWN maximum, because the weights differ —
 * momentum can reach 25 points and low-risk only 10. A shared axis would make
 * momentum look dominant by construction rather than by evidence.
 */

const TONE = v =>
  v > 0.6 ? 'bg-green-500' : v > 0.15 ? 'bg-green-600/70'
  : v < -0.6 ? 'bg-red-500' : v < -0.15 ? 'bg-red-600/70' : 'bg-gray-600'

export default function SixFactor({ ticker }) {
  const [openFactor, setOpenFactor] = useState(null)
  const [showMethod, setShowMethod] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['alphaV2', ticker],
    queryFn: () => getAlphaV2(ticker),
    staleTime: 15 * 60 * 1000,
    retry: false,
  })

  if (isLoading) return <div className="card"><Spinner size="sm" /></div>
  if (isError || !data || data.error) return null

  const e = data.explanation
  if (!e?.rows?.length) return null
  const buy = (data.alpha_score ?? 0) > 0

  return (
    <div className="card space-y-4">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold">Six-factor view</h2>
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">
          {data.horizon_days}-day horizon
        </span>
      </div>

      {/* The decision and the score, before any of the working. */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`px-2 py-0.5 rounded text-sm font-bold tracking-wide ${
          buy ? 'bg-green-900/40 text-green-300 border border-green-800'
              : 'bg-red-900/40 text-red-300 border border-red-800'}`}>
          {data.signal}
        </span>
        <span className="text-lg font-bold text-gray-100">
          {data.alpha_score > 0 ? '+' : ''}{data.alpha_score}
          <span className="text-sm text-gray-500 font-normal"> / 100</span>
        </span>
        <span className="text-[11px] text-gray-500">
          Model preference, not a predicted return
        </span>
      </div>

      {/* The sentence. This is the part that actually gets read. */}
      <p className="text-sm text-gray-200 leading-relaxed">{e.sentence}</p>

      {e.lesson && (
        <p className="text-xs text-amber-200/85 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
          {e.lesson}
        </p>
      )}

      {/* Agreement at a glance, before the detail. */}
      <div className="flex items-center gap-3 flex-wrap text-[11px]">
        <span className="text-gray-400">
          <b className="text-gray-100">{e.n_positive} of {e.n_total}</b> factors support this
        </span>
        {e.strongest && <span className="text-green-400">Strongest: {e.strongest}</span>}
        {e.biggest_concern && <span className="text-red-400">Concern: {e.biggest_concern}</span>}
      </div>

      {/* Each bar scaled to its own maximum. Click for what it means and what
          would break it — the methodology stays one level deeper. */}
      <div className="space-y-1.5">
        {e.rows.map(r => {
          const frac = r.max_points ? r.points / r.max_points : 0
          const isOpen = openFactor === r.factor
          return (
            <div key={r.factor}>
              <button onClick={() => setOpenFactor(isOpen ? null : r.factor)}
                      aria-expanded={isOpen}
                      className="w-full flex items-center gap-2 text-xs text-left hover:bg-gray-800/40 rounded px-1 py-0.5 transition-colors">
                <span className="w-36 shrink-0 text-gray-400 truncate">{r.label}</span>
                <div className="flex-1 h-2 bg-gray-800 rounded-sm overflow-hidden flex">
                  <div className="w-1/2 flex justify-end">
                    {r.points < 0 && (
                      <div className={`${TONE(frac)} h-full`}
                           style={{ width: `${Math.min(Math.abs(frac) * 100, 100)}%` }} />
                    )}
                  </div>
                  <div className="w-1/2">
                    {r.points >= 0 && (
                      <div className={`${TONE(frac)} h-full`}
                           style={{ width: `${Math.min(frac * 100, 100)}%` }} />
                    )}
                  </div>
                </div>
                <span className={`w-16 text-right font-mono shrink-0 ${
                  r.points > 0 ? 'text-green-400' : r.points < 0 ? 'text-red-400' : 'text-gray-500'}`}>
                  {r.points > 0 ? '+' : ''}{r.points}
                </span>
                <span className="w-12 text-right text-gray-600 shrink-0 text-[10px]">
                  /{r.max_points}
                </span>
              </button>

              {isOpen && (
                <div className="ml-1 mt-1 mb-2 pl-3 border-l-2 border-gray-700 space-y-1.5">
                  <p className="text-[11px] text-gray-400 leading-relaxed">
                    {data.factors?.[r.factor]?.reason || r.label}
                  </p>
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    <b className="text-gray-400">Why this weight:</b>{' '}
                    {data.weight_reasons?.[r.factor]}
                  </p>
                  <p className="text-[11px] text-amber-200/70 leading-relaxed">
                    <b>What could go wrong:</b> {r.risk_note}
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <p className="text-[10px] text-gray-600">
        Each factor is scored against its own maximum, because the weights differ.
        Click any factor for what it measures and what would break it.
      </p>

      {/* Liquidity sits outside the score deliberately, and says so. */}
      {data.liquidity?.tier && (
        <p className="text-[11px] text-gray-500">
          <b className="text-gray-400">Tradeability:</b> {data.liquidity.tier}
          {data.liquidity.daily_value_label ? ` · ${data.liquidity.daily_value_label}` : ''}
          <span className="text-gray-600"> — kept out of the score on purpose. Being
          liquid is not attractiveness; being illiquid is a cost.</span>
        </p>
      )}

      {/* Both models, side by side. The comparison is the point of running two. */}
      <div className="pt-2 border-t border-gray-800">
        <button onClick={() => setShowMethod(m => !m)}
                aria-expanded={showMethod}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
          {showMethod ? 'Hide' : 'Show'} model comparison and weights
        </button>
        {showMethod && (
          <div className="mt-2 space-y-2">
            <div className="flex items-center gap-4 text-xs">
              <span className="text-gray-400">
                4-factor: <span className="font-mono text-gray-200">
                  {data.v1_score > 0 ? '+' : ''}{data.v1_score}</span>
                <span className="text-gray-600"> ({data.v1_signal})</span>
              </span>
              <span className="text-gray-400">
                6-factor: <span className="font-mono text-gray-200">
                  {data.alpha_score > 0 ? '+' : ''}{data.alpha_score}</span>
                <span className="text-gray-600"> ({data.signal})</span>
              </span>
              <span className={`font-mono ${
                Math.abs(data.disagreement) > 10 ? 'text-amber-400' : 'text-gray-500'}`}>
                {data.disagreement > 0 ? '+' : ''}{data.disagreement} apart
              </span>
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {Object.entries(data.weights_used || {}).map(([k, w]) => (
                <span key={k} className="text-[11px] text-gray-500">
                  {k.replace(/_/g, ' ')} <span className="font-mono text-gray-300">
                    {Math.round(w * 100)}%</span>
                </span>
              ))}
            </div>
            <p className="text-[10px] text-gray-600 leading-relaxed">{data.note}</p>
          </div>
        )}
      </div>

      <p className="text-[11px] text-gray-600 leading-relaxed">{e.caveat}</p>
    </div>
  )
}
