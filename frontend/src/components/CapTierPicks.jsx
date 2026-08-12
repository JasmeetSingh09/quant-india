import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getUniverseTop } from '../api'
import Spinner from './Spinner'
import { ArrowUpRight, ArrowDownRight, Sparkles } from 'lucide-react'

const FACTORS = [
  ['momentum',  'Momentum'],
  ['quality',   'Quality'],
  ['value',     'Value'],
  ['sentiment', 'Sentiment'],
]

const TIERS = [
  { key: 'large_cap', label: 'Large cap', note: 'Top 100 by market cap' },
  { key: 'mid_cap',   label: 'Mid cap',   note: 'Ranks 101–250' },
  { key: 'small_cap', label: 'Small cap', note: 'Rank 251+' },
]

function dominant(contrib = {}) {
  const e = Object.entries(contrib)
  if (!e.length) return null
  return e.reduce((a, b) => (Math.abs(b[1]) > Math.abs(a[1]) ? b : a))
}

/** Same card treatment as the old Top Picks — score, signal, factor bars. */
function PickCard({ r, buy, onOpen }) {
  const name = r.ticker.replace('.NS', '')
  const score = r.alpha_score
  const dom = dominant(r.contributions)
  return (
    <button
      onClick={() => onOpen(r.ticker)}
      className={`text-left w-full rounded-xl border p-3.5 bg-gray-900/60 transition-colors
                  ${buy ? 'border-green-700/40 hover:border-green-600/70'
                        : 'border-red-700/40 hover:border-red-600/70'}`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          {buy ? <ArrowUpRight className="text-green-400 shrink-0" size={15} />
               : <ArrowDownRight className="text-red-400 shrink-0" size={15} />}
          <span className="font-mono font-bold text-sm truncate">{name}</span>
        </div>
        <span className={`text-base font-bold font-mono shrink-0 ${buy ? 'text-green-400' : 'text-red-400'}`}>
          {score > 0 ? '+' : ''}{score?.toFixed(0)}
        </span>
      </div>
      <div className="flex items-center justify-between text-[11px] mb-2">
        <span className={`badge-${buy ? 'green' : 'red'}`}>{r.signal}</span>
        <span className="text-gray-500">{Math.round((r.confidence || 0) * 100)}% conf.</span>
      </div>
      <div className="space-y-1">
        {FACTORS.map(([k, label]) => {
          const v = r.contributions?.[k] ?? 0
          const pos = v >= 0
          const w = Math.min(Math.abs(v) * 2, 100)
          return (
            <div key={k} className="flex items-center gap-2 text-[10px]">
              <span className="w-14 text-gray-500 shrink-0">{label}</span>
              <div className="flex-1 h-1 bg-gray-800 rounded-full overflow-hidden">
                <div className={`h-full ${pos ? 'bg-green-500' : 'bg-red-500'}`} style={{ width: `${w}%` }} />
              </div>
              <span className={`w-8 text-right font-mono shrink-0 ${pos ? 'text-green-400' : 'text-red-400'}`}>
                {pos ? '+' : ''}{v.toFixed(0)}
              </span>
            </div>
          )
        })}
      </div>
      {dom && (
        <p className="mt-1.5 text-[10px] text-gray-600">
          Driven by <span className="text-gray-400">{dom[0]}</span>
        </p>
      )}
    </button>
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
  const navigate = useNavigate()
  const [tier, setTier] = useState('large_cap')
  const { data, isLoading, isError } = useQuery({
    queryKey: ['universeTop', n],
    queryFn: () => getUniverseTop(n),
    staleTime: 15 * 60 * 1000,
  })

  if (isLoading) return <div className="card"><Spinner size="sm" /></div>
  if (isError) return null

  const open = t => navigate(`/stock?ticker=${encodeURIComponent(t)}`)
  const block = data?.[tier] || { buys: [], avoids: [], scored: 0 }
  const active = TIERS.find(t => t.key === tier)

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="font-semibold flex items-center gap-2">
          <Sparkles size={18} className="text-green-400" />
          Top picks by company size
        </h2>
        <span className="text-xs text-gray-500">
          {(data?.universe_scored ?? 0).toLocaleString('en-IN')} NSE stocks scored
        </span>
      </div>

      {/* Tier selector */}
      <div className="flex gap-1 overflow-x-auto scrollbar-none">
        {TIERS.map(t => (
          <button
            key={t.key}
            onClick={() => setTier(t.key)}
            className={`shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              tier === t.key ? 'bg-green-600 text-white'
                             : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}
          >
            {t.label}
            <span className="ml-1.5 text-[10px] opacity-70">{data?.[t.key]?.scored ?? 0}</span>
          </button>
        ))}
      </div>
      <p className="text-[11px] text-gray-600 -mt-2">{active?.note}</p>

      {block.scored === 0 ? (
        <p className="text-sm text-gray-500 py-4">
          No {active?.label.toLowerCase()} stocks scored yet — this tier fills as the
          universe scan reaches it.
        </p>
      ) : (
        <>
          <div>
            <h3 className="section-title mb-2 text-green-400">
              Top {Math.min(n, block.buys.length)} to consider
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
              {block.buys.map(r => <PickCard key={r.ticker} r={r} buy onOpen={open} />)}
            </div>
          </div>

          {block.avoids.length > 0 && (
            <div>
              <h3 className="section-title mb-2 text-red-400">
                Weakest {block.avoids.length} in this tier
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
                {block.avoids.map(r => <PickCard key={r.ticker} r={r} buy={false} onOpen={open} />)}
              </div>
            </div>
          )}
        </>
      )}

      <p className="text-[11px] text-gray-600">
        Ranked by alpha score within each tier. Tiers follow the SEBI convention —
        by market-cap rank, not fixed rupee cut-offs. Not financial advice.
      </p>
    </div>
  )
}
