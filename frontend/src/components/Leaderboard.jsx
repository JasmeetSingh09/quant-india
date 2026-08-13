import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getLeaderboard } from '../api'
import { Trophy, ChevronDown, ChevronRight } from 'lucide-react'

const medal = r => r === 1 ? 'text-yellow-400' : r === 2 ? 'text-gray-300' : r === 3 ? 'text-amber-600' : 'text-gray-600'

/**
 * Leaderboard — anonymous top paper portfolios.
 *
 * Renders nothing until at least one simulation qualifies, so a fresh install
 * shows no empty scaffolding. Identities never reach the client: the backend
 * sends a hashed label, a return, a duration and a position count, and nothing
 * else — with a pilot of a dozen classmates, a holdings list or a user-typed
 * name would identify someone immediately.
 */
export default function Leaderboard({ n = 5 }) {
  const [open, setOpen] = useState(null)
  const { data, isLoading } = useQuery({
    queryKey: ['leaderboard', n],
    queryFn: () => getLeaderboard(n),
    staleTime: 10 * 60 * 1000,
  })

  const rows = data?.top ?? []
  if (isLoading || rows.length === 0) return null

  return (
    <div className="card">
      <div className="flex items-baseline justify-between flex-wrap gap-2 mb-3">
        <h2 className="font-semibold flex items-center gap-2">
          <Trophy size={18} className="text-yellow-400" />
          Best paper portfolios
        </h2>
        <span className="text-xs text-gray-500">
          {data.total_qualifying} qualifying
        </span>
      </div>

      <div className="space-y-1">
        {rows.map(r => (
          <div key={r.label} className="border-b border-gray-900 last:border-0">
          <div
            onClick={() => r.holdings && setOpen(open === r.label ? null : r.label)}
            className={`flex items-center justify-between py-2 ${r.holdings ? 'cursor-pointer hover:bg-gray-800/40 -mx-2 px-2 rounded' : ''}`}>
            <div className="flex items-center gap-3 min-w-0">
              <span className={`font-mono text-sm w-6 shrink-0 ${medal(r.rank)}`}>#{r.rank}</span>
              <div className="min-w-0">
                <p className="text-sm text-gray-200 truncate flex items-center gap-1.5">
                  {r.label}
                  {r.is_demo && (
                    <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded
                                     bg-gray-800 text-gray-400 border border-gray-700 shrink-0">
                      example
                    </span>
                  )}
                </p>
                <p className="text-[11px] text-gray-600">
                  {r.n_positions} stocks · {r.days_running} days
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`font-mono text-sm ${r.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {r.return_pct > 0 ? '+' : ''}{r.return_pct.toFixed(1)}%
              </span>
              {r.holdings && (open === r.label
                ? <ChevronDown size={14} className="text-gray-500" />
                : <ChevronRight size={14} className="text-gray-600" />)}
            </div>
          </div>

          {/* Holdings appear for examples only — a real user's mix is never shown */}
          {r.holdings && open === r.label && (
            <div className="pb-2 pl-9 space-y-1">
              {r.holdings.map(h => (
                <div key={h.ticker} className="flex items-center justify-between text-xs">
                  <span className="font-mono text-gray-300">{h.name}</span>
                  <div className="flex items-center gap-3 font-mono">
                    <span className="text-gray-500 w-12 text-right">{h.weight_pct}%</span>
                    <span className={`w-16 text-right ${h.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {h.return_pct > 0 ? '+' : ''}{h.return_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between gap-2 mt-3 flex-wrap">
        <p className="text-[11px] text-gray-600">{data.privacy}</p>
        <Link to="/build" className="text-xs text-green-400 hover:text-green-300">
          Build one →
        </Link>
      </div>
      <p className="text-[11px] text-gray-600 mt-1">{data.rules}</p>
    </div>
  )
}
