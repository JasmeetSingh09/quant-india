import { useQuery } from '@tanstack/react-query'
import { getAlphaScore, getSignalHistory, getPredictionTrack } from '../api'
import Spinner from './Spinner'

/**
 * WhySignal — everything behind a BUY or SELL badge, on one screen.
 *
 * A badge on its own asks to be trusted. This panel exists so it can be
 * checked instead: what the score is and what it is not, how complete the
 * inputs were, which factor actually drove it, over what horizon, and how
 * signals like it have performed — including when that record is too thin to
 * mean anything.
 *
 * Every number here is one the model already computed. Nothing is generated
 * prose: if a figure is unavailable it is left out rather than filled in.
 */

// Each factor's contribution is weight x score x 100, and the weights are not
// equal. Momentum can reach +/-35 while value tops out at +/-15, so the bars
// are scaled per factor — a chart whose rows share a length but not a scale
// invites exactly the wrong comparison.
const FACTOR_MAX = { momentum: 35, sentiment: 25, quality: 25, value: 15 }
const FACTOR_LABEL = { momentum: 'Momentum', quality: 'Quality',
                       value: 'Value', sentiment: 'Sentiment' }

const pct = v => v == null ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`

export default function WhySignal({ ticker }) {
  const { data: alpha, isLoading } = useQuery({
    queryKey: ['alphaScore', ticker],
    queryFn: () => getAlphaScore(ticker),
    staleTime: 15 * 60 * 1000,
    retry: false,
  })
  const { data: hist } = useQuery({
    queryKey: ['signalHistory', ticker],
    queryFn: () => getSignalHistory(ticker, 30),
    staleTime: 15 * 60 * 1000,
    retry: false,
  })
  // The horizon here MUST match the one the signal advertises, or the record
  // shown under the badge answers a different question than the badge asks.
  const { data: track } = useQuery({
    queryKey: ['predTrack', 21],
    queryFn: () => getPredictionTrack(21),
    staleTime: 30 * 60 * 1000,
    retry: false,
  })

  if (isLoading) return <div className="card"><Spinner size="sm" /></div>
  if (!alpha || alpha.error) return null

  const contrib = alpha.contributions || {}
  const entries = Object.entries(contrib)
    .filter(([, v]) => v != null)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
  const driver = entries[0]
  const buy = (alpha.alpha_score ?? 0) > 0
  const horizon = alpha.horizon_days ?? 21

  const side = buy ? track?.scorecard?.by_signal?.buy : track?.scorecard?.by_signal?.sell
  const indep = track?.scorecard?.independence
  // /alpha/signal-history returns {ticker, history: [...]}, not a bare array.
  // `hist || []` therefore handed back the OBJECT, and .slice on an object threw
  // "(a || []).slice is not a function" — killing this panel on every stock.
  // SignalHistory.jsx reads the same endpoint correctly; only this one did not.
  // Both shapes are accepted so a cached older response cannot bring it back.
  const rows = (Array.isArray(hist) ? hist : (hist?.history ?? [])).slice(0, 4)

  return (
    <div className="card space-y-4">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold">Why this signal?</h2>
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">
          {horizon}-day horizon
        </span>
      </div>

      {/* The decision, stated before the numbers that produced it. */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[10px] uppercase tracking-widest text-gray-500">Current signal</span>
        <span className={`px-2 py-0.5 rounded text-sm font-bold tracking-wide ${
          buy ? 'bg-green-900/40 text-green-300 border border-green-800'
              : 'bg-red-900/40 text-red-300 border border-red-800'}`}>
          {alpha.signal}{!buy && (alpha.signal || '').includes('SELL') ? ' · avoid' : ''}
        </span>
        <span className="text-xs text-gray-500">over {horizon} trading days</span>
      </div>

      {/* The same warning the six-factor panel carries. A signal shown without
          it reads as a tested recommendation, which this is not. */}
      <p className="text-[11px] text-amber-200/85 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
        <b>Experimental.</b> This model has not been shown to predict returns. Its
        only tested factor has not demonstrated a statistically significant edge
        across 12 walk-forward configurations after correcting for multiple
        testing — a result about this implementation, not about the factor.
      </p>

      {/* What the score is, stated with what it is not. */}
      <p className="text-[10px] uppercase tracking-widest text-gray-500">Model context</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="card-sm">
          <p className="stat-label">Alpha score</p>
          <p className={`stat-value ${buy ? 'text-green-400' : 'text-red-400'}`}>
            {alpha.alpha_score > 0 ? '+' : ''}{alpha.alpha_score?.toFixed(0)}
            <span className="text-sm text-gray-500 font-normal"> / 100</span>
          </p>
          <p className="text-[11px] text-gray-500 mt-1">
            Scale −100 to +100. Not a predicted return.
          </p>
        </div>
        <div className="card-sm">
          <p className="stat-label">{alpha.confidence_label || 'Data coverage'}</p>
          <p className="stat-value text-gray-200">
            {Math.round((alpha.confidence || 0) * 100)}%
          </p>
          <p className="text-[11px] text-gray-500 mt-1">
            How complete the inputs were — not the odds of being right.
          </p>
        </div>
      </div>

      {/* Which factor actually drove it. */}
      <div>
        <div className="flex items-baseline justify-between gap-2 mb-2">
          <p className="text-[11px] uppercase tracking-wide text-gray-500">Factor contributions</p>
          {driver && (
            <p className="text-[11px] text-gray-400">
              Driven by <span className="text-gray-200">{FACTOR_LABEL[driver[0]] || driver[0]}</span>
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          {entries.map(([k, v]) => {
            const max = FACTOR_MAX[k] || 25
            const w = Math.min(Math.abs(v) / max * 100, 100)
            const up = v >= 0
            return (
              <div key={k} className="flex items-center gap-2 text-xs">
                <span className="w-20 shrink-0 text-gray-500">{FACTOR_LABEL[k] || k}</span>
                <div className="flex-1 h-2 bg-gray-800 rounded-sm overflow-hidden flex">
                  <div className="w-1/2 flex justify-end">
                    {!up && <div className="bg-red-500 h-full" style={{ width: `${w}%` }} />}
                  </div>
                  <div className="w-1/2">
                    {up && <div className="bg-green-500 h-full" style={{ width: `${w}%` }} />}
                  </div>
                </div>
                <span className={`w-14 text-right font-mono shrink-0 ${up ? 'text-green-400' : 'text-red-400'}`}>
                  {up ? '+' : ''}{Number(v).toFixed(1)}
                </span>
                <span className="w-12 text-right text-gray-600 shrink-0 text-[10px]">±{max}</span>
              </div>
            )
          })}
        </div>
        <p className="text-[10px] text-gray-600 mt-1.5">
          Each bar is scaled to its own maximum, because the factor weights differ.
        </p>
      </div>

      {/* This stock's own recent signals. */}
      {rows.length > 1 && (
        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
            This stock's recent signals
          </p>
          <div className="flex flex-wrap gap-2">
            {rows.map((h, i) => (
              <span key={i} className="text-[11px] text-gray-400 bg-gray-900/60 border border-gray-800 rounded px-2 py-1">
                {h.date} · <span className={h.alpha_score >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {h.alpha_score >= 0 ? '+' : ''}{h.alpha_score?.toFixed(0)}
                </span>
                {h.since_pct != null && <span className="text-gray-500"> · since {pct(h.since_pct)}</span>}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* How signals of this kind have actually done — including when the
          answer is that we cannot tell yet. */}
      {side && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1.5">
            Historical track record — {buy ? 'BUY' : 'SELL'} signals
          </p>
          {/* Labelled as history, deliberately. A hit rate sitting under a live
              badge is read as the odds for THIS call unless it is named as the
              past, which it is not and cannot be. */}
          <p className="text-[10px] text-gray-600 mb-1.5">
            How signals like this one have done before. Not the probability that
            today's call is right.
          </p>
          <div className="table-wrap">
            <table className="w-full text-sm">
              <tbody>
                <tr className="border-b border-gray-800">
                  <td className="py-1 text-gray-500">Observations</td>
                  <td className="py-1 text-right font-mono">{side.signals}</td>
                </tr>
                <tr className="border-b border-gray-800">
                  <td className="py-1 text-gray-500">
                    Hit rate <span className="text-gray-600 text-xs">(share that {side.hit_means})</span>
                  </td>
                  <td className={`py-1 text-right font-mono ${
                    side.hit_rate_pct >= 55 ? 'text-green-400'
                    : side.hit_rate_pct >= 45 ? 'text-gray-200' : 'text-red-400'}`}>
                    {side.hit_rate_pct}%
                    {side.significance && (
                      <span className="block text-[10px] text-gray-500 font-normal">
                        95% CI {side.significance.ci95_low_pct}–{side.significance.ci95_high_pct}%
                        {!side.significance.significant_at_5pct && ' · not significant'}
                      </span>
                    )}
                  </td>
                </tr>
                <tr className="border-b border-gray-800">
                  <td className="py-1 text-gray-500">Average return</td>
                  <td className="py-1 text-right font-mono">{pct(side.avg_return_pct)}</td>
                </tr>
                <tr className="border-b border-gray-800">
                  <td className="py-1 text-gray-500">Median return</td>
                  <td className="py-1 text-right font-mono">{pct(side.median_return_pct)}</td>
                </tr>
                <tr>
                  <td className="py-1 text-gray-500">Average excess vs Nifty</td>
                  <td className="py-1 text-right font-mono">{pct(side.avg_excess_vs_nifty_pct)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* The limitation, next to the numbers rather than in a footnote. */}
      {indep?.note && (
        <p className="text-[11px] text-amber-200/80 leading-relaxed border-l-2 border-amber-800/60 pl-2">
          <b>Methodology:</b> {indep.note}
        </p>
      )}

      <p className="text-[11px] text-gray-600 leading-relaxed">
        {alpha.horizon_note ||
          `This signal applies to the stated ${horizon}-day horizon and is not a long-term investment recommendation.`}
      </p>
      <p className="text-[11px] text-gray-600 leading-relaxed">
        {alpha.action_note || (buy
          ? 'The model expects outperformance over this horizon.'
          : 'The model expects underperformance — read as avoid or reduce.')}
        {' '}Signal model only. Not financial advice.
      </p>
    </div>
  )
}
