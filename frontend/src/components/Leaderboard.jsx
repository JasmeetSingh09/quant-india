import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getLeaderboard } from '../api'
import { Trophy } from 'lucide-react'

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
          <div key={r.label} className="flex items-center justify-between py-2 border-b border-gray-900 last:border-0">
            <div className="flex items-center gap-3 min-w-0">
              <span className={`font-mono text-sm w-6 shrink-0 ${medal(r.rank)}`}>#{r.rank}</span>
              <div className="min-w-0">
                <p className="text-sm text-gray-200 truncate">{r.label}</p>
                <p className="text-[11px] text-gray-600">
                  {r.n_positions} stocks · {r.days_running} days
                </p>
              </div>
            </div>
            <span className={`font-mono text-sm shrink-0 ${r.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {r.return_pct > 0 ? '+' : ''}{r.return_pct.toFixed(1)}%
            </span>
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
