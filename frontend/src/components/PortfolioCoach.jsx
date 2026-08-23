import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { advisePortfolio, portfolioScenarios, portfolioWhatIf, suggestFix, trackEvent } from '../api'
import Spinner from './Spinner'
import { Lightbulb, AlertTriangle, Info, Check, Plus, X } from 'lucide-react'
import Methodology from './Methodology'
import { horizonLabel } from '../horizonLabel'
import usePersistentState from '../usePersistentState'

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

/**
 * Verdict — the judgement, before the numbers.
 *
 * This panel used to open with profit and loss, which answers a question nobody
 * was asking. P&L says how the market moved; it does not say whether the thing
 * you built is sound. A portfolio can be up 12% and badly constructed, or down
 * 8% and completely fine, and leading with the number teaches the reader to
 * confuse the two.
 *
 * So the call comes first, then what is good, then what is not. Strengths are
 * measured the same way the concerns are — when nothing clears the bar the
 * section says so rather than reaching for something encouraging.
 */
function Verdict({ v }) {
  if (!v) return null
  const bad = v.concerns.some(c => c.severity === 'high')
  const tone = bad ? 'border-red-800/70 bg-red-950/25'
             : v.concerns.length ? 'border-yellow-800/60 bg-yellow-950/15'
             : 'border-green-800/70 bg-green-950/20'

  return (
    <div className={`p-3.5 rounded-lg border ${tone} space-y-3`}>
      <div>
        <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">The verdict</p>
        <p className="text-base font-semibold text-gray-100 leading-snug">{v.call}</p>
        <p className="text-xs text-gray-400 mt-1 leading-relaxed">{v.because}</p>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-green-500/90 mb-1.5">
            What&rsquo;s good
          </p>
          {v.strengths.length === 0 ? (
            <p className="text-xs text-gray-500 leading-relaxed">{v.no_strengths_note}</p>
          ) : (
            <ul className="space-y-1.5">
              {v.strengths.map((st, i) => (
                <li key={i} className="text-xs">
                  <span className="text-gray-200">{st.title}</span>
                  <span className="block text-gray-500 mt-0.5 leading-relaxed">{st.evidence}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-wide text-red-400/90 mb-1.5">
            What concerns me
          </p>
          {v.concerns.length === 0 ? (
            <p className="text-xs text-gray-500 leading-relaxed">
              Nothing crossed a threshold. The checks it passed are the ones listed
              here, and no others.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {v.concerns.map((c, i) => (
                <li key={i} className="text-xs">
                  <span className={c.severity === 'high' ? 'text-red-300' : 'text-yellow-200/90'}>
                    {c.title}
                  </span>
                  {/* The estimated effect, or an honest statement of which kind
                      of "no number" this is. "We did not check" and "we checked
                      and it does not help" mean opposite things to someone
                      deciding whether to place a trade. */}
                  {c.effect?.improved ? (
                    <span className="block font-mono text-green-400 mt-0.5">
                      fixing this: worst case {c.effect.downside_before}% →
                      {' '}{c.effect.downside_after}% ({c.effect.improvement_pts} pts better)
                    </span>
                  ) : (
                    <span className="block text-gray-500 mt-0.5 leading-relaxed">
                      {c.effect_note}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <p className="text-[10px] text-gray-600 leading-relaxed">{v.scope}</p>
    </div>
  )
}


/**
 * Finding — the headline always, the reasoning on request.
 *
 * Each warning previously showed its title, its detail, its payoff and its
 * transferable lesson all at once. Three of those stacked is a paragraph, and a
 * reader facing three paragraphs reads none of them — the density defeated the
 * teaching it was there to do.
 *
 * The number that triggered it stays visible, because that is the finding. The
 * explanation opens when someone wants it, which is also when they will actually
 * read it. Advanced mode opens them by default, since choosing advanced IS the
 * request.
 */
function Finding({ s, i, openByDefault }) {
  const [open, setOpen] = useState(!!openByDefault)
  return (
    <div className={`flex gap-2 items-start p-3 rounded-lg border ${sevStyle(s.severity)}`}>
      <span className="text-[11px] font-mono text-gray-500 shrink-0 mt-0.5 w-3">{i + 1}</span>
      {sevIcon(s.severity)}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-200">{s.title}</p>

        {/* The size of the prize stays visible: a warning without a number is a
            lecture, and this is the part that turns it into a decision.

            When the simulation says the fix does NOT help, that is reported in
            the same place rather than hidden. Painting a worse outcome green
            because it came from the "improvement" field would be the single
            most misleading thing this panel could do. */}
        {s.payoff && (
          <p className={`text-xs mt-1 font-mono ${
            s.payoff.improved ? 'text-green-400' : 'text-yellow-400/90'}`}>
            cap {s.payoff.cap_pct}% → worst case {s.payoff.downside_before}%
            {' '}to {s.payoff.downside_after}%
            {s.payoff.improved
              ? <span className="text-green-300"> ({s.payoff.improvement_pts} pts better)</span>
              : <span className="text-yellow-300/90"> (no improvement — this fix does not pay)</span>}
          </p>
        )}

        {(s.detail || s.lesson) && (
          <button onClick={() => setOpen(o => !o)}
                  aria-expanded={open}
                  className="text-[11px] text-gray-500 hover:text-gray-300 mt-1.5 transition-colors">
            {open ? 'Hide explanation' : 'Why does this matter?'}
          </button>
        )}

        {open && (
          <div className="mt-1.5 space-y-2">
            {s.detail && (
              <p className="text-xs text-gray-400 leading-relaxed">{s.detail}</p>
            )}
            {s.lesson && (
              <p className="text-[11px] text-gray-500 pl-2 border-l-2 border-gray-700 leading-relaxed">
                {s.lesson}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Limits — what this is, and what it is not, beside the recommendation itself.
 *
 * The methodology panel is collapsed by default, which is right for how a
 * number was computed and wrong for what it can support. A reader who never
 * opens it should still be unable to mistake a risk analysis for a forecast, so
 * this is always visible and sits next to the recommendation rather than at the
 * foot of the page.
 *
 * Deliberately short. A long disclaimer is skipped, and a skipped disclaimer
 * protects nobody.
 */
function Limits() {
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900/60 p-3">
      <p className="text-[11px] uppercase tracking-widest text-gray-500 mb-1">
        What this does and does not tell you
      </p>
      <p className="text-xs text-gray-300 leading-relaxed">
        This is a <b>risk analysis</b> — not a guarantee, and not a personalised
        investment recommendation.
      </p>
      <p className="text-xs text-gray-400 leading-relaxed mt-1.5">
        Historical returns and simulations describe what has happened, or what
        could have happened under the stated assumptions. They do not predict
        future returns. Real execution costs, liquidity and bid/ask spreads may
        differ from the simulation.
      </p>
    </div>
  )
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
  // Beginner by default. Someone who wants the covariance detail will go
  // looking for it; someone who does not should never have to scroll past it
  // to reach the finding. The numbers are identical either way — this changes
  // what is shown, never what is computed.
  // Three levels, because two forced a bad choice. "Simple" hid the benchmark
  // and the tax position, which are not advanced ideas - they are the two
  // numbers that decide whether the portfolio is working. "Advanced" then had
  // to carry those alongside risk decomposition and sector attribution, so
  // anyone who wanted to know how they were doing against the index got a page
  // of factor mathematics with it.
  //
  // Beginner answers "is this all right". Intermediate adds the measurements
  // behind that answer. Advanced adds the attribution behind the measurements.
  // Nothing is removed at a lower level that changes the conclusion - the
  // verdict and its concerns are identical at all three, which is the property
  // that makes graduated disclosure honest rather than a filtered story.
  const [detail, setDetail] = usePersistentState('coach.detail', 'beginner')
  // 'simple' was the old default and is still in people's localStorage.
  const level = detail === 'simple' ? 'beginner' : detail
  const isAdvanced = level === 'advanced'
  const isIntermediate = level === 'intermediate' || isAdvanced
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
  const fix    = useMutation({ mutationFn: suggestFix })

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
        <div className="flex items-center gap-2">
          <div className="flex rounded-md overflow-hidden border border-gray-700 text-[10px]">
            {['beginner', 'intermediate', 'advanced'].map(m => (
              <button key={m} onClick={() => setDetail(m)}
                title={m === 'beginner' ? 'The verdict and what drives it'
                     : m === 'intermediate' ? 'Adds the index comparison, tax and every finding'
                     : 'Adds risk attribution, sector exposure and the method'}
                className={`px-2 py-1 capitalize transition-colors ${
                  level === m ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-gray-200'}`}>
                {m}
              </button>
            ))}
          </div>
        <button onClick={run} disabled={busy} className="btn-ghost text-xs">
          {busy ? 'Analysing…' : advice.data ? 'Re-analyse' : 'Analyse my portfolio'}
        </button>
        </div>
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
          {/* First, before the score and long before the P&L. */}
          <Verdict v={advice.data.verdict} />

          {/* One number the reader can act on, with the five that produced it
              underneath. Labelled by CHARACTER, not quality: a concentrated
              portfolio is aggressive, not bad, and calling it bad would import
              a risk preference the app does not know. */}
          {advice.data.health?.score != null && (
            <div className={`p-3 rounded-lg border ${
              advice.data.health.score >= 60 ? 'border-green-800 bg-green-950/25'
              : advice.data.health.score >= 40 ? 'border-yellow-800 bg-yellow-950/20'
              : 'border-red-800 bg-red-950/25'}`}>
              <div className="flex items-baseline justify-between gap-3 flex-wrap">
                <span className="text-lg font-bold text-gray-100">
                  {advice.data.health.score}<span className="text-sm text-gray-500 font-normal"> / 100</span>
                  <span className="ml-2 text-sm font-semibold uppercase tracking-wide text-gray-300">
                    {advice.data.health.label}
                  </span>
                </span>
                {advice.data.health.biggest_lever && (
                  <span className="text-[11px] text-gray-400">
                    Biggest lever: {advice.data.health.biggest_lever.factor.replace(/_/g, ' ')}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-1">{advice.data.health.band_note}</p>
              {/* The five factors behind the score. The score itself stays at
                  every level; the arithmetic that produced it is a measurement,
                  which is where intermediate starts. */}
              {isIntermediate && (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1 mt-2">
                {Object.entries(advice.data.health.components)
                  .filter(([, c]) => c.score != null)
                  .map(([k, c]) => (
                  <div key={k} className="text-[11px]" title={c.note}>
                    <span className="text-gray-500">{k.replace(/_/g, ' ')}</span>
                    <span className={`ml-1 font-mono ${
                      c.score >= 60 ? 'text-green-400'
                      : c.score >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
                      {Math.round(c.score)}
                    </span>
                  </div>
                ))}
              </div>
              )}
              <p className="text-[10px] text-gray-600 mt-2 leading-relaxed">
                {advice.data.health.means}
              </p>
            </div>
          )}

          <Limits />

          {/* The comparison most apps leave out. Shown before the findings
              because "you are behind the index" reframes everything below it,
              and shown in red when it is bad rather than quietly in grey. */}
          {isIntermediate && advice.data.benchmark?.verdict && (
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
          {isIntermediate && mode.showTax && advice.data.tax && !advice.data.tax.error && (
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

          {/* Which holding drives the swings. A stock at 10% of the money can
              drive 30% of the movement, and that gap is invisible in a weights
              table — which is the only table most people ever see. */}
          {isAdvanced && advice.data.risk_contributions?.length > 1 && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
                Where the risk comes from
              </p>
              <div className="space-y-1">
                {advice.data.risk_contributions.map(r => (
                  <div key={r.ticker} className="flex items-center gap-2 text-[11px]">
                    <span className="w-20 shrink-0 text-gray-400">{r.ticker.replace('.NS','')}</span>
                    <div className="flex-1 h-1.5 bg-gray-800 rounded-sm overflow-hidden">
                      <div className="bg-blue-500 h-full" style={{ width: `${Math.min(r.risk_pct, 100)}%` }} />
                    </div>
                    <span className="w-24 text-right text-gray-500 shrink-0">
                      {r.weight_pct}% money
                    </span>
                    <span className="w-20 text-right font-mono text-gray-200 shrink-0">
                      {r.risk_pct}% risk
                    </span>
                    <span className={`w-12 text-right font-mono shrink-0 ${
                      r.gap_pts > 5 ? 'text-red-400' : r.gap_pts < -5 ? 'text-green-400' : 'text-gray-600'}`}
                      title={r.gap_pts > 0
                        ? 'Contributes more volatility than its size suggests'
                        : 'Contributes less volatility than its size suggests'}>
                      {r.gap_pts > 0 ? '+' : ''}{r.gap_pts}
                    </span>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-gray-600 mt-1.5">
                Money and risk are different quantities. A volatile holding at 10%
                can drive more of your ups and downs than a stable one at 30%.
              </p>
            </div>
          )}

          {/* Where the money actually sits by sector. Counting holdings hides
              five banks; this makes it impossible to miss. */}
          {isAdvanced && advice.data.sector_exposure && Object.keys(advice.data.sector_exposure).length > 1 && (
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
              {/* Ranked and counted. A list of warnings with no order asks the
                  reader to decide which matters most, which is the judgement
                  they came here to borrow. */}
              <p className="text-xs text-gray-400 font-medium">
                {isIntermediate || advice.data.suggestions.length <= 3
                  ? `${advice.data.suggestions.length} thing${advice.data.suggestions.length === 1 ? '' : 's'} to look at${advice.data.suggestions.length > 1 ? ', biggest first' : ''}`
                  : `Top 3 of ${advice.data.suggestions.length} — switch to Intermediate for the rest`}
              </p>
              {(isIntermediate ? advice.data.suggestions : advice.data.suggestions.slice(0, 3)).map((s, i) => (
                <Finding key={i} s={s} i={i} openByDefault={isAdvanced} />
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

      {/* A concrete allocation, and what changing to it would do. The coach
          says what is wrong; a reader who agrees still has to work out what to
          hold instead, which is the part they came for. */}
      {advice.data && (
        <div className="pt-2 border-t border-gray-800">
          {!fix.data ? (
            <div className="flex items-center gap-3 flex-wrap">
              <button onClick={() => { trackEvent('fix_requested', { n_stocks: n })
                                       fix.mutate({ holdings, initial_value: initialValue,
                                                    horizon_months: horizonMonths }) }}
                      disabled={fix.isPending} className="btn-primary text-xs">
                {fix.isPending ? 'Working it out…' : 'Show me a better allocation'}
              </button>
              <span className="text-[11px] text-gray-500">
                Caps concentration and sector overlap. Does not pick stocks.
              </span>
            </div>
          ) : fix.data.changed === false ? (
            <p className="text-sm text-green-400">{fix.data.note}</p>
          ) : (
            <div className="space-y-3">
              <h3 className="section-title">Suggested allocation</h3>

              <div className="table-wrap">
                <table className="w-full text-sm min-w-[22rem]">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wide text-gray-500">
                      <th className="text-left py-1">Holding</th>
                      <th className="text-right py-1">Now</th>
                      <th className="text-right py-1">Suggested</th>
                      <th className="text-right py-1">Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(fix.data.proposed_pct).map(([t, pv]) => {
                      const cv = fix.data.current_pct[t] ?? 0
                      const d = pv - cv
                      return (
                        <tr key={t} className="border-t border-gray-800">
                          <td className="py-1">{t.replace('.NS','')}</td>
                          <td className="py-1 text-right font-mono text-gray-400">{cv.toFixed(0)}%</td>
                          <td className="py-1 text-right font-mono text-gray-100">{pv.toFixed(0)}%</td>
                          <td className={`py-1 text-right font-mono ${
                            Math.abs(d) < 0.5 ? 'text-gray-600'
                            : d > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {Math.abs(d) < 0.5 ? '—' : `${d > 0 ? '+' : ''}${d.toFixed(0)}%`}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Before and after on the SAME measurements, so the difference is
                  the change rather than the method. */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {[['Health', fix.data.before?.health?.score, fix.data.after?.health?.score, false],
                  ['Worst 5%', fix.data.before?.risk?.downside_pct, fix.data.after?.risk?.downside_pct, true],
                  ['Chance of loss', fix.data.before?.risk?.loss_prob_pct, fix.data.after?.risk?.loss_prob_pct, true]]
                  .map(([label, b, a, lowerBetter]) => (b == null || a == null) ? null : (
                  <div key={label} className="card-sm">
                    <p className="text-[11px] text-gray-500">{label}</p>
                    <p className="text-sm font-mono">
                      <span className="text-gray-400">{Number(b).toFixed(1)}</span>
                      <span className="text-gray-600 mx-1">→</span>
                      <span className={
                        (lowerBetter ? Math.abs(a) < Math.abs(b) : a > b)
                          ? 'text-green-400' : 'text-gray-300'}>
                        {Number(a).toFixed(1)}
                      </span>
                    </p>
                  </div>
                ))}
              </div>

              <ul className="space-y-1">
                {fix.data.steps.map((st, i) => (
                  <li key={i} className="text-xs text-gray-400 pl-3 relative leading-relaxed">
                    <span className="absolute left-0 text-gray-600">·</span>{st.detail}
                  </li>
                ))}
              </ul>

              {/* The cost of the change, as prominent as the benefit. */}
              <p className="text-[11px] text-amber-200/80 border-l-2 border-amber-800/60 pl-2 leading-relaxed">
                {fix.data.cost_note}
              </p>
              <p className="text-[10px] text-gray-600 leading-relaxed">{fix.data.limits}</p>
              <Limits />

              {onApply && (
                <button onClick={() => { onApply(fix.data.proposed_pct); setApplied('suggested allocation') }}
                        className="btn-ghost text-xs">Apply this allocation</button>
              )}
            </div>
          )}
          {fix.isError && <p className="banner-error text-xs mt-2">{String(fix.error)}</p>}
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
      {isAdvanced && <Methodology tool="coach" />}
    </div>
  )
}
