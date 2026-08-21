import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { advisePortfolio, portfolioScenarios, portfolioWhatIf, trackEvent } from '../api'
import Spinner from './Spinner'
import { Lightbulb, AlertTriangle, Info, Check, Plus, X } from 'lucide-react'
import Methodology from './Methodology'
import { horizonLabel } from '../horizonLabel'

const sevStyle = s =>
  s === 'high'   ? 'border-red-800/60 bg-red-950/30' :
  s === 'medium' ? 'border-yellow-800/50 bg-yellow-950/20'
                 : 'border-gray-700 bg-gray-900/40'

const sevIcon = s =>
  s === 'high'   ? <AlertTriangle size={14} className="text-red-400 shrink-0 mt-0.5" /> :
  s === 'medium' ? <Info size={14} className="text-yellow-400 shrink-0 mt-0.5" />
                 : <Info size={14} className="text-gray-500 shrink-0 mt-0.5" />

// Each module asks a different question, so the coach answers a different one.
// The Optimizer is designing a portfolio that has not returned anything yet;
// telling it that it "trails the index" would compare a simulation to reality
// and call the difference performance. Monte Carlo is about the shape of the
// downside, not about which stock the model dislikes. Only a live portfolio has
// a real return, a real holding period and therefore a real tax position.
const MODES = {
  live: {
    heading: 'How you are really doing',
    intro: 'Compares your portfolio to the index, checks what you hold against ' +
           'the model, and shows what the gain is worth after tax. Every finding ' +
           'comes with the principle behind it.',
    showEditor: true, showScenarios: true, showTax: true,
  },
  design: {
    heading: 'Is this portfolio well built?',
    intro: 'Checks the structure of the portfolio you are designing — ' +
           'concentration, sector overlap, correlation and whether you could ' +
           'actually trade what is in it. No performance claims: this portfolio ' +
           'has not run yet.',
    showEditor: true, showScenarios: true, showTax: false,
  },
  risk: {
    heading: 'How bad can it get?',
    intro: 'Focuses on the downside: where risk is concentrated, which holdings ' +
           'move together, and how much the worst case improves if you change ' +
           'the shape of the portfolio.',
    showEditor: true, showScenarios: true, showTax: false,
  },
}

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
// currentReturnPct is how the portfolio is ACTUALLY doing, when the caller
// knows. Passing it turns on the index comparison. The optimizer and Monte
// Carlo deal in hypothetical portfolios that have not returned anything yet,
// so they correctly leave it out rather than comparing a simulation to a real
// index and calling the difference performance.
export default function PortfolioCoach({ holdings, initialValue = 100000,
                                         horizonMonths = 12, maxLossPct = null,
                                         currentReturnPct = null, daysHeld = null,
                                         focus = 'live', onApply }) {
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
                 horizon_months: horizonMonths, max_loss_pct: maxLossPct,
                 current_return_pct: currentReturnPct,
                 focus, days_held: daysHeld }

  const mode = MODES[focus] || MODES.live
  const advice = useMutation({ mutationFn: advisePortfolio })
  const scen   = useMutation({ mutationFn: portfolioScenarios })

  const n = Object.keys(holdings || {}).length

  // A single holding used to hide the coach entirely, which meant the one
  // person who most needs to hear "this is one company's outcome, not a
  // portfolio" was the only person never told. There is nothing to correlate
  // or optimise with one stock, so the panel says the one true thing instead of
  // running numbers that would all be about that stock.
  if (n === 1) {
    const only = Object.keys(holdings)[0].replace('.NS', '')
    return (
      <div className="card space-y-2">
        <h2 className="font-semibold flex items-center gap-2">
          <Lightbulb size={18} className="text-yellow-400" />
          One holding is not a portfolio
        </h2>
        <p className="text-sm text-gray-300">
          Everything that happens here is {only}'s result. You can be completely
          right about the company and still lose the year to one bad quarter, one
          regulator, or one fire.
        </p>
        <p className="text-xs text-gray-500 leading-relaxed">
          Add a second holding from a different sector and the coach can start
          measuring something — how the two move together, where the risk actually
          sits, and how much the worst case improves. Most of the benefit of
          diversifying arrives by 8&ndash;12 names, and almost all of it is gone by 3.
        </p>
      </div>
    )
  }
  if (n < 1) return null

  // Only the advice runs on click. Scenarios cost ~45s of simulation against
  // ~7s for the findings, and firing both meant the panel sat spinning long
  // after the answers had arrived. They now load when someone asks for them.
  const run = () => { trackEvent('advice_requested', { n_stocks: n })
                      advice.mutate(body) }
  const busy = advice.isPending

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-semibold flex items-center gap-2">
          <Lightbulb size={18} className="text-yellow-400" />
          {mode.heading}
        </h2>
        <button onClick={run} disabled={busy} className="btn-ghost text-xs">
          {busy ? 'Analysing…' : advice.data ? 'Re-analyse' : 'Analyse my portfolio'}
        </button>
      </div>

      {!advice.data && !busy && (
        <p className="text-sm text-gray-500">
          {mode.intro}
        </p>
      )}

      {busy && <Spinner size="sm" />}

      {advice.isError && <p className="banner-error">{String(advice.error)}</p>}

      {advice.data && (
        <>
          {/* The comparison most apps leave out. Shown before the findings
              because "you are behind the index" reframes everything below it,
              and shown in red when it is bad rather than quietly in grey. */}
          {advice.data.benchmark?.verdict && (
            <div className={`p-3 rounded-lg border text-sm ${
              advice.data.benchmark.verdict === 'behind'
                ? 'border-red-800 bg-red-950/30'
                : advice.data.benchmark.verdict === 'ahead'
                ? 'border-green-800 bg-green-950/30'
                : 'border-gray-700 bg-gray-900/40'}`}>
              <div className="flex items-baseline justify-between gap-3 flex-wrap">
                <span className="font-medium text-gray-200">
                  You {advice.data.benchmark.portfolio_return_pct >= 0 ? '+' : ''}
                  {advice.data.benchmark.portfolio_return_pct}%
                  <span className="text-gray-500 mx-2">vs</span>
                  {advice.data.benchmark.benchmark} {advice.data.benchmark.benchmark_return_pct >= 0 ? '+' : ''}
                  {advice.data.benchmark.benchmark_return_pct}%
                </span>
                <span className={`font-mono text-xs ${
                  advice.data.benchmark.difference_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {advice.data.benchmark.difference_pct >= 0 ? '+' : ''}
                  {advice.data.benchmark.difference_pct} pts
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-1 leading-relaxed">
                {advice.data.benchmark.plain}
              </p>
            </div>
          )}

          {/* What the gain is actually worth. Only a live portfolio has a real
              holding period, so this never appears on a designed one. */}
          {mode.showTax && advice.data.tax && !advice.data.tax.error && (
            <div className="p-3 rounded-lg border border-gray-700 bg-gray-900/40">
              <div className="flex items-baseline justify-between gap-3 flex-wrap">
                <span className="text-sm font-medium text-gray-200">
                  After tax: {advice.data.tax.net_return_pct >= 0 ? '+' : ''}
                  {advice.data.tax.net_return_pct}%
                  <span className="text-gray-500 text-xs ml-2">
                    (gross {advice.data.tax.gross_return_pct >= 0 ? '+' : ''}
                    {advice.data.tax.gross_return_pct}%)
                  </span>
                </span>
                <span className="text-[11px] text-gray-500 uppercase tracking-wide">
                  {advice.data.tax.kind} · {advice.data.tax.rate_pct}%
                </span>
              </div>
              {advice.data.tax.boundary_note && (
                <p className="text-xs text-amber-300/90 mt-1.5 leading-relaxed">
                  {advice.data.tax.boundary_note}
                </p>
              )}
              <p className="text-[10px] text-gray-600 mt-1.5">{advice.data.tax.disclaimer}</p>
            </div>
          )}

          {/* Where the money actually sits by sector. Counting holdings hides
              five banks; this makes it impossible to miss. */}
          {advice.data.sector_exposure && Object.keys(advice.data.sector_exposure).length > 1 && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">Sector exposure</p>
              <div className="flex h-2 rounded-full overflow-hidden bg-gray-800">
                {Object.entries(advice.data.sector_exposure).map(([sec, pct], i) => (
                  <div key={sec} title={`${sec} ${pct}%`} style={{ width: `${pct}%` }}
                       className={['bg-green-500','bg-blue-500','bg-amber-500','bg-purple-500',
                                   'bg-pink-500','bg-cyan-500'][i % 6]} />
                ))}
                {/* Not every listed company maps to a known sector. Naming the
                    remainder is better than leaving a gap that reads as a bug —
                    and better than scaling it away, which would quietly overstate
                    how much of the portfolio we actually classified. */}
                {(() => {
                  const known = Object.values(advice.data.sector_exposure)
                                      .reduce((a, b) => a + b, 0)
                  const rest = Math.max(0, 100 - known)
                  return rest > 0.5
                    ? <div title={`Unclassified ${rest.toFixed(0)}%`}
                           style={{ width: `${rest}%` }} className="bg-gray-600" />
                    : null
                })()}
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
                {Object.entries(advice.data.sector_exposure).slice(0, 6).map(([sec, pct], i) => (
                  <span key={sec} className="text-[11px] text-gray-400 flex items-center gap-1">
                    <span className={`w-2 h-2 rounded-sm ${['bg-green-500','bg-blue-500','bg-amber-500',
                      'bg-purple-500','bg-pink-500','bg-cyan-500'][i % 6]}`} />
                    {sec.replace(/_/g, ' & ')} {pct}%
                  </span>
                ))}
              </div>
            </div>
          )}

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
                    {/* The size of the prize. A warning without a number is a
                        lecture; this turns it into a decision the user can weigh. */}
                    {s.payoff && (
                      <p className="text-xs mt-2 font-mono text-green-400">
                        cap {s.payoff.cap_pct}% → worst case {s.payoff.downside_before}%
                        {' '}to {s.payoff.downside_after}%
                        <span className="text-green-300"> ({s.payoff.improvement_pts} pts better)</span>
                      </p>
                    )}
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
                {horizonLabel(hz)}
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
              onClick={() => { trackEvent('scenario_tested', { source: 'per_stock' })
                               whatIf.mutate({ holdings, initial_value: initialValue,
                                              horizon_months: hz, new_holdings: rows }) }}
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
            onClick={() => { trackEvent('scenario_tested', { source: 'cap' })
                             whatIf.mutate({ holdings, initial_value: initialValue,
                                            horizon_months: hz, max_weight_pct: cap }) }}
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
                <button onClick={() => { trackEvent('allocation_changed', { source: 'custom' })
                                         onApply?.(whatIf.data.weights); setApplied('your change') }}
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

      {/* Loaded on request rather than with the findings. Comparing several
          whole portfolios means simulating each one, which takes far longer than
          the advice itself — and most people read the findings first anyway. */}
      {advice.data && !scen.data && (
        <div className="pt-2 border-t border-gray-800 flex items-center gap-3 flex-wrap">
          <button onClick={() => { trackEvent('scenarios_requested', { n_stocks: n })
                                   scen.mutate(body) }}
                  disabled={scen.isPending} className="btn-ghost text-xs">
            {scen.isPending ? 'Simulating…' : 'Compare ways to change it'}
          </button>
          <span className="text-[11px] text-gray-500">
            {scen.isPending
              ? 'Simulating each version of the portfolio — around a minute.'
              : 'Runs a full simulation of several alternatives. Takes about a minute.'}
          </span>
        </div>
      )}

      {scen.isError && <p className="banner-error text-xs">{String(scen.error)}</p>}

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
                        onClick={() => { trackEvent('allocation_changed', { source: 'scenario' })
                                         onApply?.(s.weights); setApplied(s.name) }}
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
      <Methodology tool="coach" />
    </div>
  )
}
