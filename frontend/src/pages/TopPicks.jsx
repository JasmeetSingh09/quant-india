import { useQuery } from '@tanstack/react-query'
import { getTopPicks } from '../api'
import Spinner from '../components/Spinner'
import Explainer from '../components/Explainer'
import { Sparkles, TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight } from 'lucide-react'

const FACTORS = [
  ['momentum',  'Momentum'],
  ['quality',   'Quality'],
  ['value',     'Value'],
  ['sentiment', 'Sentiment'],
]

function dominant(contrib = {}) {
  const e = Object.entries(contrib)
  if (!e.length) return null
  return e.reduce((a, b) => (Math.abs(b[1]) > Math.abs(a[1]) ? b : a))
}

function PickCard({ r, buy }) {
  const name = r.ticker.replace('.NS', '')
  const score = r.alpha_score
  const dom = dominant(r.contributions)
  return (
    <div className={`card-sm border ${buy ? 'border-green-700/50' : 'border-red-700/50'}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {buy ? <ArrowUpRight className="text-green-400" size={18} />
               : <ArrowDownRight className="text-red-400" size={18} />}
          <span className="font-mono font-bold">{name}</span>
        </div>
        <span className={`text-xl font-bold font-mono ${buy ? 'text-green-400' : 'text-red-400'}`}>
          {score > 0 ? '+' : ''}{score?.toFixed(0)}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between text-xs">
        <span className={`badge-${buy ? 'green' : 'red'}`}>{r.signal}</span>
        <span className="text-gray-500">{Math.round((r.confidence || 0) * 100)}% confidence</span>
      </div>
      {/* factor breakdown */}
      <div className="mt-2 space-y-1">
        {FACTORS.map(([k, label]) => {
          const v = r.contributions?.[k] ?? 0
          const pos = v >= 0
          const w = Math.min(Math.abs(v) * 2, 100)
          return (
            <div key={k} className="flex items-center gap-2 text-[11px]">
              <span className="w-16 text-gray-500">{label}</span>
              <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div className={`h-full ${pos ? 'bg-green-500' : 'bg-red-500'}`} style={{ width: `${w}%` }} />
              </div>
              <span className={`w-10 text-right font-mono ${pos ? 'text-green-400' : 'text-red-400'}`}>
                {pos ? '+' : ''}{v.toFixed(0)}
              </span>
            </div>
          )
        })}
      </div>
      {dom && (
        <p className="mt-2 text-xs text-gray-500">
          Driven mainly by <span className="text-gray-300">{dom[0]}</span> ({dom[1] > 0 ? '+' : ''}{dom[1].toFixed(0)} pts)
        </p>
      )}
    </div>
  )
}

export default function TopPicks() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['topPicks'],
    queryFn: getTopPicks,
    staleTime: 25 * 60 * 1000,
    retry: 1,
  })

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Sparkles size={24} className="text-green-400" /> Top Picks
        </h1>
        <p className="text-gray-400 text-sm mt-0.5">
          Stocks ranked by our 4-factor alpha model right now — an idea screen, not a guarantee.
        </p>
      </div>

      {isLoading && (
        <div className="card"><Spinner /><p className="text-center text-xs text-gray-500 mt-2">
          Scanning the universe… (first load can take ~30–60s)</p></div>
      )}
      {isError && <div className="card text-red-400 text-sm">{String(error)} — try again in a moment (data source may be busy).</div>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-3">
              <h2 className="font-semibold flex items-center gap-2 text-green-400">
                <TrendingUp size={18} /> Looks strong ({data.buys?.length || 0})
              </h2>
              {data.buys?.length ? data.buys.map(r => <PickCard key={r.ticker} r={r} buy />)
                : <p className="text-sm text-gray-500">Nothing scoring positive right now.</p>}
            </div>
            <div className="space-y-3">
              <h2 className="font-semibold flex items-center gap-2 text-red-400">
                <TrendingDown size={18} /> Looks weak ({data.avoids?.length || 0})
              </h2>
              {data.avoids?.length ? data.avoids.map(r => <PickCard key={r.ticker} r={r} buy={false} />)
                : <p className="text-sm text-gray-500">Nothing scoring negative right now.</p>}
            </div>
          </div>

          <div className="card">
            <Explainer>
              <p><b>What this is:</b> we score {data.universe_size} large liquid stocks on four factors —
                <i> momentum</i> (is it outperforming peers?), <i>quality</i> (healthy business?),
                <i> value</i> (cheap vs peers?), and <i>sentiment</i> (news tone). The bars show how
                each factor pushed the score up (green) or down (red).</p>
              <p><b>How to use it:</b> a high score means a stock looks attractive <i>on these factors today</i> —
                it's a starting point for research, <b>not</b> a buy order.</p>
              <p className="text-yellow-300/90"><b>Honest caveat:</b> {data.disclaimer} Returns aren't
                reliably predictable — treat this as a screen, do your own homework, and never invest
                money you can't afford to lose.</p>
            </Explainer>
            <p className="text-xs text-gray-600 mt-2">Scanned {data.scanned}/{data.universe_size} · as of {data.as_of}</p>
          </div>
        </>
      )}
    </div>
  )
}
