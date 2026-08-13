import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { advisePortfolio, portfolioScenarios } from '../api'
import Spinner from './Spinner'
import { Lightbulb, AlertTriangle, Info, Check } from 'lucide-react'

const sevStyle = s =>
  s === 'high'   ? 'border-red-800/60 bg-red-950/30' :
  s === 'medium' ? 'border-yellow-800/50 bg-yellow-950/20'
                 : 'border-gray-700 bg-gray-900/40'

const sevIcon = s =>
  s === 'high'   ? <AlertTriangle size={14} className="text-red-400 shrink-0 mt-0.5" /> :
  s === 'medium' ? <Info size={14} className="text-yellow-400 shrink-0 mt-0.5" />
                 : <Info size={14} className="text-gray-500 shrink-0 mt-0.5" />

const pctStr = v => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`

/**
 * PortfolioCoach — "what to fix" plus tweakable what-if options.
 *
 * Shared by Monte Carlo (which holds weights) and the Optimizer (which holds a
 * ticker list), so `onApply` receives the full weights object and each page
 * decides what to do with it.
 *
 * Scenarios deliberately show the change in BOTH typical outcome and worst
 * case. Surfacing only the return would push beginners toward whichever option
 * is most concentrated, which is the opposite of what this tool is for.
 */
export default function PortfolioCoach({ holdings, initialValue = 100000,
                                         horizonMonths = 12, maxLossPct = null,
                                         onApply }) {
  const [applied, setApplied] = useState(null)
  const body = { holdings, initial_value: initialValue,
                 horizon_months: horizonMonths, max_loss_pct: maxLossPct }

  const advice = useMutation({ mutationFn: advisePortfolio })
  const scen   = useMutation({ mutationFn: portfolioScenarios })

  const n = Object.keys(holdings || {}).length
  if (n < 2) return null

  const run = () => { advice.mutate(body); scen.mutate(body) }
  const busy = advice.isPending || scen.isPending

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-semibold flex items-center gap-2">
          <Lightbulb size={18} className="text-yellow-400" />
          What to fix
        </h2>
        <button onClick={run} disabled={busy} className="btn-ghost text-xs">
          {busy ? 'Analysing…' : advice.data ? 'Re-analyse' : 'Analyse my portfolio'}
        </button>
      </div>

      {!advice.data && !busy && (
        <p className="text-sm text-gray-500">
          Checks your holdings against the alpha model, measures where the risk
          actually sits, and simulates the downside — then suggests specific changes.
        </p>
      )}

      {busy && <Spinner size="sm" />}

      {advice.isError && <p className="banner-error">{String(advice.error)}</p>}

      {advice.data && (
        <>
          {advice.data.suggestions.length === 0 ? (
            <p className="text-sm text-green-400 flex items-center gap-2">
              <Check size={15} /> {advice.data.headline}
            </p>
          ) : (
            <div className="space-y-2">
              {advice.data.suggestions.map((s, i) => (
                <div key={i} className={`flex gap-2 items-start p-3 rounded-lg border ${sevStyle(s.severity)}`}>
                  {sevIcon(s.severity)}
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-200">{s.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5 leading-relaxed">{s.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="text-[11px] text-gray-600">{advice.data.basis}</p>
        </>
      )}

      {scen.data?.scenarios?.length > 0 && (
        <div className="pt-2 border-t border-gray-800">
          <h3 className="section-title mb-1">Try a change</h3>
          <p className="text-[11px] text-gray-500 mb-3">{scen.data.how_to_read}</p>

          <div className="table-wrap">
            <table className="w-full min-w-[34rem] text-sm">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-gray-800">
                  <th className="text-left py-2 font-medium">Option</th>
                  <th className="text-right font-medium">Typical</th>
                  <th className="text-right font-medium">Worst 5%</th>
                  <th className="text-right font-medium"></th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-gray-900 text-gray-400">
                  <td className="py-2 italic">Your portfolio now</td>
                  <td className="text-right font-mono">{pctStr(scen.data.base.return_pct)}</td>
                  <td className="text-right font-mono">{pctStr(scen.data.base.downside_pct)}</td>
                  <td></td>
                </tr>
                {scen.data.scenarios.map((s, i) => (
                  <tr key={i} className="border-b border-gray-900 last:border-0">
                    <td className="py-2">
                      <p className="text-gray-200">{s.name}</p>
                      <p className="text-[11px] text-gray-500 leading-snug">{s.why}</p>
                    </td>
                    <td className="text-right font-mono whitespace-nowrap">
                      {pctStr(s.after.return_pct)}
                      <span className={`block text-[10px] ${s.delta_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {pctStr(s.delta_return_pct)}
                      </span>
                    </td>
                    <td className="text-right font-mono whitespace-nowrap">
                      {pctStr(s.after.downside_pct)}
                      <span className={`block text-[10px] ${s.delta_downside_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {pctStr(s.delta_downside_pct)}
                      </span>
                    </td>
                    <td className="text-right">
                      <button
                        onClick={() => { onApply?.(s.weights); setApplied(s.name) }}
                        className="btn-ghost text-xs whitespace-nowrap"
                      >
                        {applied === s.name ? 'Applied' : 'Apply'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {applied && (
            <p className="text-xs text-green-400 mt-3">
              Applied “{applied}” — run the simulation again to see it.
            </p>
          )}
          <p className="text-[11px] text-gray-600 mt-3">{scen.data.disclaimer}</p>
        </div>
      )}
    </div>
  )
}
