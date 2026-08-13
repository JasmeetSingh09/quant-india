import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { advisePortfolio, portfolioScenarios, portfolioWhatIf } from '../api'
import Spinner from './Spinner'
import { Lightbulb, AlertTriangle, Info, Check, Plus, X } from 'lucide-react'

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
  // User-driven tweak, distinct from the preset scenarios: they answer "what
  // could I change?", this answers "what if I change it like THIS?".
  const nHold = Object.keys(holdings || {}).length
  const minCap = Math.ceil(100 / Math.max(nHold, 1))
  const [cap, setCap] = useState(Math.max(minCap, 30))
  const [hz, setHz]   = useState(horizonMonths)
  const whatIf = useMutation({ mutationFn: portfolioWhatIf })
  // Per-stock editing: change any weight, drop a name, add a new one. Seeded
  // from the current portfolio the first time the panel is opened.
  const [edit, setEdit] = useState(null)
  const [newTicker, setNewTicker] = useState('')
  const rows = edit ?? holdings
  const editTotal = Object.values(rows).reduce((a, b) => a + (Number(b) || 0), 0)
  const setW = (t, v) => setEdit({ ...rows, [t]: v })
  const dropT = t => { const n = { ...rows }; delete n[t]; setEdit(n) }
  const addT = () => {
    let t = newTicker.trim().toUpperCase()
    if (!t) return
    if (!t.endsWith('.NS') && !t.endsWith('.BO')) t += '.NS'
    if (rows[t]) return
    setEdit({ ...rows, [t]: 10 })
    setNewTicker('')
  }
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
          What to fix — and why
        </h2>
        <button onClick={run} disabled={busy} className="btn-ghost text-xs">
          {busy ? 'Analysing…' : advice.data ? 'Re-analyse' : 'Analyse my portfolio'}
        </button>
      </div>

      {!advice.data && !busy && (
        <p className="text-sm text-gray-500">
          Checks your holdings against the alpha model, measures where the risk
          actually sits, and simulates the downside. Every finding comes with the
          principle behind it, so you can spot the same problem yourself next time.
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
                    {/* The principle behind the finding. Fixing this portfolio is
                        worth less than recognising the same mistake unaided next
                        time, so the lesson sits alongside every warning. */}
                    {s.lesson && (
                      <p className="text-[11px] text-gray-500 mt-2 pl-2 border-l-2 border-gray-700 leading-relaxed">
                        {s.lesson}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="text-[11px] text-gray-600">{advice.data.basis}</p>
        </>
      )}

      {/* Your own tweak */}
      {advice.data && (
        <div className="pt-2 border-t border-gray-800">
          <h3 className="section-title mb-2">Or change it yourself</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Cut concentration — max per stock</label>
              <input type="range" min={minCap} max="100" step="5" className="w-full"
                     value={cap} onChange={e => setCap(Number(e.target.value))} />
              <p className="text-[11px] text-gray-600 mt-1">
                No holding above {cap}%
                {cap <= minCap && ` (lowest possible with ${nHold} stocks)`}
              </p>
            </div>
            <div>
              <label className="label">Hold for longer</label>
              <input type="range" min="3" max="60" step="3" className="w-full"
                     value={hz} onChange={e => setHz(Number(e.target.value))} />
              <p className="text-[11px] text-gray-600 mt-1">
                {hz} months{hz >= 12 && ` (${(hz / 12).toFixed(1)} years)`}
              </p>
            </div>
          </div>

          {/* Per-stock control: exact weights, remove, add */}
          <div className="mt-4 pt-3 border-t border-gray-800/70">
            <p className="label mb-2">Or set each stock yourself</p>
            <div className="space-y-1.5">
              {Object.entries(rows).map(([t, v]) => (
                <div key={t} className="flex items-center gap-2">
                  <span className="font-mono text-xs w-24 truncate">{t.replace('.NS', '')}</span>
                  <input type="range" min="0" max="100" step="1" className="flex-1"
                         value={Number(v) || 0} onChange={e => setW(t, Number(e.target.value))} />
                  <input type="number" min="0" max="100" step="1"
                         className="input w-16 text-right py-1 text-xs"
                         value={Number(v) || 0} onChange={e => setW(t, Number(e.target.value))} />
                  <span className="text-xs text-gray-500">%</span>
                  <button onClick={() => dropT(t)} title="Remove"
                          className="text-gray-600 hover:text-red-400 shrink-0"><X size={13} /></button>
                </div>
              ))}
            </div>

            <div className="flex items-center gap-2 mt-2">
              <input className="input flex-1 py-1 text-xs" placeholder="Add a stock — e.g. ITC"
                     value={newTicker} onChange={e => setNewTicker(e.target.value)}
                     onKeyDown={e => e.key === 'Enter' && addT()} />
              <button onClick={addT} className="btn-ghost text-xs flex items-center gap-1">
                <Plus size={12} /> Add
              </button>
            </div>

            <p className={`text-[11px] mt-2 ${Math.abs(editTotal - 100) < 0.5 ? 'text-gray-600' : 'text-yellow-400'}`}>
              Total {editTotal.toFixed(1)}%
              {Math.abs(editTotal - 100) >= 0.5 && ' — will be scaled to 100% when tested'}
            </p>

            <button
              onClick={() => whatIf.mutate({ holdings, initial_value: initialValue,
                                             horizon_months: hz, new_holdings: rows })}
              disabled={whatIf.isPending || Object.keys(rows).length < 2}
              className="btn-ghost text-xs mt-2">
              {whatIf.isPending ? 'Testing…' : 'Test my edits'}
            </button>
            {edit && (
              <button onClick={() => setEdit(null)} className="btn-ghost text-xs mt-2 ml-2">
                Reset
              </button>
            )}
          </div>

          <button
            onClick={() => whatIf.mutate({ holdings, initial_value: initialValue,
                                           horizon_months: hz, max_weight_pct: cap })}
            disabled={whatIf.isPending}
            className="btn-ghost text-xs mt-3">
            {whatIf.isPending ? 'Testing…' : 'Test this change'}
          </button>

          {whatIf.isError && <p className="banner-error mt-3">{String(whatIf.error)}</p>}

          {whatIf.data && (
            <div className="mt-3 p-3 rounded-lg border border-gray-700 bg-gray-900/40 space-y-2">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-[11px] text-gray-500">Typical outcome</p>
                  <p className="font-mono">
                    {pctStr(whatIf.data.base.return_pct)} → {pctStr(whatIf.data.after.return_pct)}
                    <span className={`ml-2 text-xs ${whatIf.data.delta_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {pctStr(whatIf.data.delta_return_pct)}
                    </span>
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-gray-500">Worst 5%</p>
                  <p className="font-mono">
                    {pctStr(whatIf.data.base.downside_pct)} → {pctStr(whatIf.data.after.downside_pct)}
                    <span className={`ml-2 text-xs ${whatIf.data.delta_downside_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {pctStr(whatIf.data.delta_downside_pct)}
                    </span>
                  </p>
                </div>
              </div>
              {whatIf.data.changed ? (
                <button onClick={() => { onApply?.(whatIf.data.weights); setApplied('your change') }}
                        className="btn-ghost text-xs">
                  {applied === 'your change' ? 'Applied' : 'Apply these weights'}
                </button>
              ) : (
                <p className="text-[11px] text-gray-500">
                  This cap changes nothing — no holding is above {cap}% already.
                </p>
              )}
            </div>
          )}
        </div>
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
