import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getUniverseTop } from '../api'
import Spinner from './Spinner'
import { ArrowUpRight, ArrowDownRight } from 'lucide-react'

const TIERS = [
  { key: 'large_cap', label: 'Large cap',  note: 'Top 100 by market cap' },
  { key: 'mid_cap',   label: 'Mid cap',    note: 'Ranks 101–250' },
  { key: 'small_cap', label: 'Small cap',  note: 'Rank 251+' },
]

function Row({ r }) {
  const name = r.ticker.replace('.NS', '')
  const pos  = (r.alpha_score ?? 0) >= 0
  return (
    <Link
      to={`/stock?ticker=${encodeURIComponent(r.ticker)}`}
      className="flex items-center justify-between py-2 px-2 -mx-2 rounded-lg
                 hover:bg-gray-800/60 transition-colors"
    >
      <div className="flex items-center gap-2 min-w-0">
        {pos ? <ArrowUpRight size={13} className="text-green-400 shrink-0" />
             : <ArrowDownRight size={13} className="text-red-400 shrink-0" />}
        <span className="font-mono text-sm truncate">{name}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          r.signal?.includes('BUY')  ? 'bg-green-900/50 text-green-400' :
          r.signal?.includes('SELL') ? 'bg-red-900/50 text-red-400'
                                     : 'bg-gray-800 text-gray-400'}`}>
          {r.signal}
        </span>
        <span className={`font-mono text-sm w-12 text-right ${pos ? 'text-green-400' : 'text-red-400'}`}>
          {pos ? '+' : ''}{Math.round(r.alpha_score)}
        </span>
      </div>
    </Link>
  )
}

/**
 * CapTierPicks — top names per cap tier from the full 2,401-stock scan.
 *
 * Deliberately silent about scan progress: it renders whatever the last
 * completed pass produced. A tier that is still filling shows its own empty
 * note rather than a global "scanning" banner.
 */
export default function CapTierPicks({ n = 10 }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['universeTop', n],
    queryFn: () => getUniverseTop(n),
    staleTime: 15 * 60 * 1000,
  })

  if (isLoading) return <div className="card"><Spinner size="sm" /></div>
  if (isError)   return null

  const scored = data?.universe_scored ?? 0

  return (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2 mb-4">
        <h2 className="font-semibold">Top picks by company size</h2>
        <span className="text-xs text-gray-500">
          {scored.toLocaleString('en-IN')} NSE stocks scored
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {TIERS.map(({ key, label, note }) => {
          const rows = data?.[key] ?? []
          return (
            <div key={key} className="min-w-0">
              <div className="flex items-baseline justify-between mb-1.5">
                <h3 className="text-sm font-semibold text-gray-200">{label}</h3>
                <span className="text-[10px] text-gray-600">{note}</span>
              </div>
              <div className="border-t border-gray-800 pt-1">
                {rows.length === 0 ? (
                  <p className="text-xs text-gray-600 py-3">
                    Not enough of this tier scored yet — fills as the scan progresses.
                  </p>
                ) : rows.map(r => <Row key={r.ticker} r={r} />)}
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-[11px] text-gray-600 mt-4">
        Ranked by alpha score within each tier. Tiers follow the SEBI convention —
        by market-cap rank, not fixed rupee cut-offs. Not financial advice.
      </p>
    </div>
  )
}
