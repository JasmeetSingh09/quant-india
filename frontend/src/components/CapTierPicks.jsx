import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ScoreProvenance } from './Evidence'
import { Link } from 'react-router-dom'
import { getUniverseTop } from '../api'
import { signalLabel, SIGNAL_TITLE, rankBadgeClass, scoreTextClass } from '../signalLabel'
import Spinner from './Spinner'

// Each factor's contribution is weight x score x 100, and the weights are not
// equal — so the bars do NOT share one scale. Momentum can reach +/-35 while
// value tops out at +/-15. Printing a single range would be wrong, and a bar
// chart whose rows mean different things is worse than no chart, so each row
// carries its own maximum.
const FACTOR_MAX = { momentum: 35, sentiment: 25, quality: 25, value: 15 }

const FACTORS = [
  ['momentum',  'Momentum'],
  ['quality',   'Quality'],
  ['value',     'Value'],
  ['sentiment', 'Sentiment'],
]

const TIERS = [
  { key: 'large_cap', label: 'Large cap', note: 'Ranks 1–100 by market cap' },
  { key: 'mid_cap',   label: 'Mid cap',   note: 'Ranks 101–250' },
  { key: 'small_cap', label: 'Small cap', note: 'Rank 251+' },
]

function dominant(contrib = {}) {
  const e = Object.entries(contrib)
  if (!e.length) return null
  return e.reduce((a, b) => (Math.abs(b[1]) > Math.abs(a[1]) ? b : a))
}

// Bars grow from the middle: right in sky for a positive contribution, left in
// slate for a negative one. Same scale rule as before: each factor against
// its own maximum.
function FactorCell({ r, k }) {
  // Unmeasured, not zero: the stored 0 is a placeholder the composite weighted.
  if (r.not_measured?.includes(k)) {
    return (
      <span className="hidden min-[1400px]:flex items-center gap-2 pt-1.5 text-xs"
            title="Not measured for this stock (for example, too little price history). It adds nothing to the score.">
        <span className="relative h-1.5 w-[4.5rem] shrink-0 rounded-full bg-gray-800/50" />
        <span className="w-8 shrink-0 text-right font-mono text-gray-400">n/a</span>
      </span>
    )
  }
  const v = r.contributions?.[k] ?? 0
  const pos = v >= 0
  // Signed by the figure shown, so +0.3 prints "0", not "+0".
  const shown = Math.round(v)
  const max = FACTOR_MAX[k] || 25
  const w = Math.min(Math.abs(v) / max * 50, 50)
  return (
    <span className="hidden min-[1400px]:flex items-center gap-2 pt-1.5 text-xs">
      <span className="relative h-1.5 w-[4.5rem] shrink-0 rounded-full bg-gray-800">
        <span className="absolute inset-y-0 left-1/2 w-px bg-gray-600" />
        <span className={`bar-grow absolute inset-y-0 rounded-full ${pos ? 'left-1/2 bg-sky-400 origin-left' : 'right-1/2 bg-slate-500 origin-right'}`}
              style={{ width: `${w}%` }} />
      </span>
      <span className={`w-8 shrink-0 text-right font-mono tabular-nums ${shown === 0 ? 'text-gray-400' : pos ? 'text-sky-300' : 'text-slate-400'}`}>
        {shown > 0 ? '+' : ''}{shown === 0 ? 0 : shown}
      </span>
    </span>
  )
}

// Columns: rank, stock, rank label, score, four factors (from 1400px),
// driven by (from 1024). Every row shares them through subgrid, so the scores
// sit on one right edge and the bars line up down the list.
// Fixed widths for every column but the stock's, so the Top and Lowest lists
// (two separate grids) put the same column in the same place.
const COLS = 'grid-cols-[1.25rem_minmax(0,1fr)_6.75rem_2.75rem] ' +
  'lg:grid-cols-[1.5rem_minmax(0,1fr)_7.5rem_3rem_11rem] ' +
  'min-[1400px]:grid-cols-[1.5rem_minmax(0,1fr)_7.5rem_3rem_repeat(4,7.5rem)_10rem]'

/**
 * One ranked list. Rows, not cards (18 Nov 2026): the model orders stocks,
 * and a list in that order says so better than twenty green and red cards,
 * which read as buy and sell. The whole row opens the stock's page; "Why
 * this signal" says what is there.
 */
function PickList({ title, rows }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-200 mb-2">{title}</h3>
      <ol className={`grid ${COLS} gap-x-3 sm:gap-x-4`}>
        <li aria-hidden="true"
            className="col-span-full grid grid-cols-subgrid items-end pb-2 text-xs text-gray-400 border-b border-gray-800">
          <span>#</span>
          <span>Stock</span>
          <span>Rank</span>
          <span className="text-right">Score</span>
          {FACTORS.map(([k, label]) => <span key={k} className="hidden min-[1400px]:block">{label}</span>)}
          <span className="hidden lg:block">Driven by</span>
        </li>
        {rows.map((r, i) => {
          const name = r.ticker.replace('.NS', '')
          const score = r.alpha_score
          const dom = dominant(r.contributions)
          return (
            <li key={r.ticker} className="col-span-full grid grid-cols-subgrid border-b border-gray-800 last:border-0">
              <Link to={`/stock?ticker=${encodeURIComponent(r.ticker)}`}
                    className="group col-span-full grid grid-cols-subgrid items-start py-3 -mx-2 px-2 rounded-lg
                               hover:bg-gray-800/40 focus-visible:bg-gray-800/40 transition-colors">
                <span className="pt-0.5 font-mono text-xs text-gray-400 tabular-nums">{i + 1}</span>
                <span className="min-w-0">
                  <span className="block font-mono font-medium text-sm text-gray-200 truncate">{name}</span>
                  {/* The row already opens the stock page; saying so turns a
                      mystery click into an offer. */}
                  <span className="block mt-1 text-xs text-gray-400 group-hover:text-gray-200 group-focus-visible:text-gray-200">
                    Why this signal →
                  </span>
                </span>
                <span title={SIGNAL_TITLE} className={`${rankBadgeClass(r.signal)} justify-self-start whitespace-nowrap`}>
                  {signalLabel(r.signal)}
                </span>
                <span title="Alpha score, -100 to +100. Composite of momentum, quality, value and sentiment. Higher means the model prefers it more strongly — it is NOT a predicted return."
                      className={`pt-0.5 text-right font-mono font-medium text-sm tabular-nums ${scoreTextClass(score)}`}>
                  {score > 0 ? '+' : ''}{score?.toFixed(0)}
                </span>
                {FACTORS.map(([k]) => <FactorCell key={k} r={r} k={k} />)}
                <span className="hidden lg:block pt-0.5 text-xs text-gray-400"
                      title={dom ? `${dom[0]} contributed ${dom[1] >= 0 ? '+' : ''}${dom[1].toFixed(1)} points — the largest single component of this score. Each factor's bar is scaled to its own maximum, because the weights differ.` : undefined}>
                  {dom && <>{dom[0]} ({dom[1] >= 0 ? '+' : ''}{dom[1].toFixed(0)} pts)</>}
                </span>
              </Link>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

/**
 * CapTierPicks — replaces the single Top Picks list.
 *
 * Ranking happens INSIDE each tier, so a small cap is never judged against a
 * large cap's score, and each tier shows both ends: the 10 best and the 10
 * worst. Deliberately silent about scan progress — it renders the last
 * completed results, and a tier still filling says so on its own.
 */
export default function CapTierPicks({ n = 10 }) {
  const [tier, setTier] = useState('large_cap')
  const { data, isLoading, isError } = useQuery({
    queryKey: ['universeTop', n],
    queryFn: () => getUniverseTop(n),
    staleTime: 15 * 60 * 1000,
  })

  if (isLoading) return <div className="card"><Spinner size="sm" /></div>
  if (isError) return null

  const block = data?.[tier] || { buys: [], avoids: [], scored: 0 }
  const active = TIERS.find(t => t.key === tier)

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-semibold text-white">
          Top picks by company size
        </h2>
        <span className="text-xs text-gray-400">
          {(data?.universe_scored ?? 0).toLocaleString('en-IN')} NSE stocks scored
        </span>
      </div>

      {/* This list serves the last COMPLETED nightly cycle, while Top Picks
          recomputes live. The same stock can legitimately show a different
          score in each; saying which is which is the whole point. */}
      <ScoreProvenance mode="cycle" cycle={data?.serving_cycle}
                       asOf={data?.scan?.finished_at} />

      {/* Tier selector */}
      <div className="flex flex-wrap gap-1">
        {TIERS.map(t => (
          <button
            key={t.key}
            onClick={() => setTier(t.key)}
            aria-pressed={tier === t.key}
            className={`shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              tier === t.key ? 'bg-green-700 text-white'
                             : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}
          >
            {t.label}
            <span className="ml-1.5 font-mono text-xs">{data?.[t.key]?.scored ?? 0}</span>
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-400 -mt-2">{active?.note}</p>

      {/* Momentum carries 35% of the score and usually decides a large cap's
          rank, and its tested edge did not show among the largest, most liquid
          stocks (docs/MOMENTUM_ROBUSTNESS_RESULT_2026-09-18.md). */}
      {tier === 'large_cap' && (
        <p className="text-xs text-amber-200/90 leading-relaxed max-w-[72ch]">
          Large-cap rankings lean mostly on momentum, and momentum&apos;s tested edge
          was not shown among the largest, most liquid stocks. Read these as the
          model&apos;s ordering, not as evidence.
        </p>
      )}

      {block.scored === 0 ? (
        <p className="text-sm text-gray-500 py-4">
          No {active?.label.toLowerCase()} stocks scored yet — this tier fills as the
          universe scan reaches it.
        </p>
      ) : (
        <>
          <PickList title={`Top ${Math.min(n, block.buys.length)} by model score`} rows={block.buys} />
          {block.avoids.length > 0 && (
            <PickList title={`Lowest ${block.avoids.length} by model score`} rows={block.avoids} />
          )}
          {/* The score's range, stated once rather than left to inference. */}
          <p className="hidden min-[1400px]:block text-xs text-gray-400">
            bars scaled per factor · momentum ±35, quality/sentiment ±25, value ±15
          </p>
        </>
      )}

      <p className="text-xs text-gray-400 leading-relaxed">
        Ranked by alpha score within each tier. Only momentum, one of four
        factors, has passed a historical test; the combined score has not been
        tested. Tiers follow the SEBI convention, by market-cap rank. Not
        financial advice.
      </p>
    </div>
  )
}
