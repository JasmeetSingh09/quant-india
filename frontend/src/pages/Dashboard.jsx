import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getMCX, getRegime, getMarketNews, getPrice, getTopPicks, getPredictionTrack } from '../api'
import Spinner from '../components/Spinner'
import RegimeBadge from '../components/RegimeBadge'
import Explainer from '../components/Explainer'
import { TrendingUp, TrendingDown, Sparkles, ArrowUpRight, ArrowDownRight, RefreshCw, History } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

const NIFTY_STOCKS = ['RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS','ICICIBANK.NS']

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
    <div className={`rounded-xl border p-3.5 bg-gray-900/60 ${buy ? 'border-green-700/40' : 'border-red-700/40'}`}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          {buy
            ? <ArrowUpRight className="text-green-400 shrink-0" size={15} />
            : <ArrowDownRight className="text-red-400 shrink-0" size={15} />}
          <span className="font-mono font-bold text-sm">{name}</span>
        </div>
        <span className={`text-base font-bold font-mono ${buy ? 'text-green-400' : 'text-red-400'}`}>
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
    </div>
  )
}

function PriceTag({ ticker }) {
  const { data, isLoading } = useQuery({
    queryKey: ['price', ticker],
    queryFn: () => getPrice(ticker),
    // only poll while the delayed feed is active (stops ~15 min after market close)
    refetchInterval: q => (q.state.data?.feed_active ? 60000 : false),
  })
  if (isLoading) return (
    <div className="card-sm h-[72px] animate-pulse bg-gray-800/40" />
  )
  const pos = (data?.change_pct ?? 0) >= 0
  return (
    <div className="card-sm">
      <p className="text-xs text-gray-500">{ticker.replace('.NS', '')}</p>
      <p className="text-lg font-bold font-mono leading-tight mt-0.5">
        {data?.price != null ? `₹${data.price.toLocaleString('en-IN')}` : '—'}
      </p>
      <p className={`text-xs font-medium flex items-center gap-1 mt-1 ${pos ? 'text-green-400' : 'text-red-400'}`}>
        {pos ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
        {pos ? '+' : ''}{data?.change_pct?.toFixed(2) ?? '0.00'}%
      </p>
    </div>
  )
}

function CommodityRow({ c }) {
  const up = c.change_pct >= 0
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-800 last:border-0">
      <div>
        <p className="text-sm font-medium">{c.name}</p>
        <p className="text-xs text-gray-500">{c.unit}</p>
      </div>
      <div className="text-right">
        <p className="text-sm font-mono font-semibold">₹{c.price_inr?.toLocaleString('en-IN')}</p>
        <p className={`text-xs font-medium ${up ? 'text-green-400' : 'text-red-400'}`}>
          {up ? '+' : ''}{c.change_pct?.toFixed(2)}%
        </p>
      </div>
    </div>
  )
}

function NewsCard({ article }) {
  const mins = article.published_minutes_ago
  const timeStr = mins == null ? '' : mins < 60 ? `${mins}m ago` : `${Math.floor(mins / 60)}h ago`
  return (
    <a href={article.url} target="_blank" rel="noreferrer"
      className="block p-3 rounded-lg hover:bg-gray-800 transition-colors border border-transparent hover:border-gray-700">
      <p className="text-sm font-medium leading-snug line-clamp-2">{article.title}</p>
      <div className="flex items-center gap-2 mt-1.5">
        <span className="text-xs text-gray-500">{article.source}</span>
        <span className="text-gray-700">·</span>
        <span className="text-xs text-gray-500">{timeStr}</span>
        {article.macro_impacts?.length > 0 && (
          <span className="badge-yellow ml-auto">Macro Impact</span>
        )}
      </div>
    </a>
  )
}

function TrackRecord() {
  const navigate = useNavigate()
  const [days, setDays] = useState(3)   // shortest window so the record shows as soon as picks mature
  const { data, isLoading } = useQuery({
    queryKey: ['predTrack', days],
    queryFn: () => getPredictionTrack(days),
    staleTime: 10 * 60 * 1000,
  })
  const sc = data?.scorecard
  const rawPreds = data?.predictions || []
  // The model re-logs a snapshot daily, so each stock appears once per snapshot date.
  // Collapse to ONE row per stock — keep the longest-held snapshot (most complete
  // evaluation) — so the table reads as "one line per pick" instead of repeating.
  const preds = Object.values(rawPreds.reduce((acc, r) => {
    const cur = acc[r.ticker]
    if (!cur || (r.days_held ?? 0) > (cur.days_held ?? 0)) acc[r.ticker] = r
    return acc
  }, {}))
  const pct = v => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
  const col = v => v == null ? 'text-gray-400' : v >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-semibold flex items-center gap-2">
          <History size={18} className="text-blue-400" /> Track Record — did past picks actually work?
        </h2>
        <div className="flex items-center gap-1 text-xs">
          <span className="text-gray-500 mr-1">Held for ≥</span>
          {[3, 7, 14].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-2 py-1 rounded ${days === d ? 'bg-blue-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}>
              {d}d
            </button>
          ))}
        </div>
      </div>

      {isLoading ? <Spinner size="sm" /> : !sc ? (
        <p className="text-sm text-gray-500">{data?.status || 'No matured predictions in this window yet — check back as the record accrues.'}</p>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="card-sm">
              <p className="stat-label">BUY-signal avg return</p>
              <p className={`stat-value text-lg ${col(sc.buy_avg_return_pct)}`}>{pct(sc.buy_avg_return_pct)}</p>
            </div>
            <div className="card-sm">
              <p className="stat-label">SELL-signal avg return</p>
              <p className={`stat-value text-lg ${col(sc.sell_avg_return_pct)}`}>{pct(sc.sell_avg_return_pct)}</p>
            </div>
            <div className="card-sm">
              <p className="stat-label">BUY − SELL spread<span className="text-gray-600"> (edge)</span></p>
              <p className={`stat-value text-lg ${col(sc.buy_minus_sell_pct)}`}>{pct(sc.buy_minus_sell_pct)}</p>
            </div>
            <div className="card-sm">
              <p className="stat-label">Avg excess vs Nifty</p>
              <p className={`stat-value text-lg ${col(sc.avg_excess_vs_nifty_pct)}`}>{pct(sc.avg_excess_vs_nifty_pct)}</p>
            </div>
          </div>

          <div className={`rounded-lg p-3 text-sm border ${
            (sc.buy_minus_sell_pct ?? 0) > 0 ? 'border-green-800 bg-green-900/15 text-green-300'
                                             : 'border-yellow-800 bg-yellow-900/15 text-yellow-200'}`}>
            <b>Verdict:</b> {sc.verdict}
            <span className="block text-xs text-gray-400 mt-1">
              {sc.matured_predictions} matured picks · alpha↔return correlation {sc.alpha_vs_return_correlation ?? '—'}
              {' '}(a value near 0 means the score barely predicts returns — expected on small samples).
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-gray-800">
                  <th className="text-left py-2">Stock</th>
                  <th className="text-left">Signal</th>
                  <th className="text-right">Actual return</th>
                  <th className="text-right">vs Nifty</th>
                  <th className="text-right">Held</th>
                  <th className="text-right">Logged</th>
                </tr>
              </thead>
              <tbody>
                {preds.slice().sort((a,b) => (b.forward_return_pct ?? 0) - (a.forward_return_pct ?? 0)).map((r, i) => {
                  const isBuy = r.signal && r.signal.includes('BUY')
                  const isSell = r.signal && r.signal.includes('SELL')
                  return (
                    <tr key={i}
                        onClick={() => navigate(`/stock?ticker=${encodeURIComponent(r.ticker)}`)}
                        className="border-b border-gray-800 last:border-0 hover:bg-gray-800/50 cursor-pointer">
                      <td className="py-1.5 font-mono text-green-400 hover:underline">{r.ticker.replace('.NS','')}</td>
                      <td><span className={`badge-${isBuy ? 'green' : isSell ? 'red' : 'yellow'}`}>{r.signal}</span></td>
                      <td className={`text-right font-mono ${col(r.forward_return_pct)}`}>{pct(r.forward_return_pct)}</td>
                      <td className={`text-right font-mono ${col(r.excess_pct)}`}>{pct(r.excess_pct)}</td>
                      <td className="text-right text-gray-400">{r.days_held}d</td>
                      <td className="text-right text-gray-500 text-xs">{r.date}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-600">
            "Actual return" = how the stock moved from the day it was logged until now. A BUY that went up
            (green) or a SELL that went down was "right." One row per stock (its longest-held snapshot); the
            model re-logs daily, so the headline stats above still use every snapshot. Small samples are noisy.
          </p>
        </>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { data: mcx,    isLoading: mcxLoading,    isError: mcxError    } = useQuery({ queryKey: ['mcx'],     queryFn: getMCX,        refetchInterval: 120000 })
  const { data: regime, isLoading: regimeLoading, isError: regimeError } = useQuery({ queryKey: ['regime'],  queryFn: getRegime,     staleTime: 300000 })
  const { data: news,   isLoading: newsLoading,   isError: newsError   } = useQuery({ queryKey: ['mktNews'], queryFn: getMarketNews, staleTime: 60000 })
  const { data: picks,    isLoading: picksLoading,
          isError: picksError, refetch: refetchPicks } = useQuery({ queryKey: ['topPicks'], queryFn: getTopPicks,   staleTime: 25 * 60 * 1000, retry: 1 })

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Market Dashboard</h1>
          <p className="text-gray-400 text-sm mt-0.5">
            {new Date().toLocaleDateString('en-IN', { weekday:'long', year:'numeric', month:'long', day:'numeric' })}
          </p>
        </div>
        {regime && !regimeLoading && (
          <div className="text-right">
            <p className="text-xs text-gray-500 mb-1">Market Regime</p>
            <RegimeBadge regime={regime.current_regime} proba={regime.current_proba} />
          </div>
        )}
      </div>

      {/* Nifty 50 stocks */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Nifty 50 — Top Holdings</h2>
        <div className="grid grid-cols-5 gap-3">
          {NIFTY_STOCKS.map(t => <PriceTag key={t} ticker={t} />)}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* MCX Commodities */}
        <div className="card col-span-1">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">MCX Commodities</h2>
            <Link to="/markets" className="text-xs text-green-400 hover:text-green-300">View all →</Link>
          </div>
          {mcxLoading ? <Spinner size="sm" /> : mcxError ? (
            <p className="text-xs text-red-400 py-4 text-center">Could not load commodity data.</p>
          ) : (
            <>
              <p className="text-xs text-gray-500 mb-3">
                USD/INR: <span className="text-gray-300 font-mono">{mcx?.usd_inr_rate}</span>
              </p>
              {mcx?.commodities?.map(c => <CommodityRow key={c.key} c={c} />)}
            </>
          )}
        </div>

        {/* Market News */}
        <div className="card col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">Market News</h2>
            <Link to="/markets" className="text-xs text-green-400 hover:text-green-300">View all →</Link>
          </div>
          {newsLoading ? <Spinner size="sm" /> : newsError ? (
            <p className="text-xs text-red-400 py-4 text-center">Could not load news.</p>
          ) : (
            <div className="space-y-1">
              {news?.articles?.slice(0, 6).map((a, i) => <NewsCard key={i} article={a} />)}
            </div>
          )}
        </div>
      </div>

      {/* Top Picks */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-semibold flex items-center gap-2">
              <Sparkles size={17} className="text-green-400" /> Top Picks
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Stocks ranked by our 4-factor alpha model — an idea screen, not a guarantee.
            </p>
          </div>
          {picks && (
            <div className="flex items-center gap-3">
              <p className="text-xs text-gray-600">
                {picks.scanned}/{picks.universe_size} scanned · {picks.as_of}
              </p>
              <button
                onClick={() => refetchPicks()}
                className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
                title="Refresh picks"
              >
                <RefreshCw size={13} />
              </button>
            </div>
          )}
        </div>

        {picksLoading && (
          <div className="flex flex-col items-center py-8 gap-2">
            <Spinner size="sm" />
            <p className="text-xs text-gray-500">Scanning the universe… (first load ~30–60s)</p>
          </div>
        )}

        {picksError && (
          <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-red-950/40 border border-red-900/50">
            <p className="text-sm text-red-400">Could not load picks — data source may be busy.</p>
            <button onClick={() => refetchPicks()} className="text-xs text-red-400 hover:text-red-300 underline">Retry</button>
          </div>
        )}

        {picks && (
          <>
            <div className="grid grid-cols-2 gap-6">
              {/* Buys */}
              <div>
                <h3 className="text-xs font-semibold text-green-400 uppercase tracking-wider flex items-center gap-1.5 mb-3">
                  <TrendingUp size={13} /> Looks strong ({picks.buys?.length || 0})
                </h3>
                {picks.buys?.length ? (
                  <div className="grid grid-cols-2 gap-2">
                    {picks.buys.map(r => <PickCard key={r.ticker} r={r} buy />)}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">Nothing scoring positive right now.</p>
                )}
              </div>
              {/* Avoids */}
              <div>
                <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wider flex items-center gap-1.5 mb-3">
                  <TrendingDown size={13} /> Looks weak ({picks.avoids?.length || 0})
                </h3>
                {picks.avoids?.length ? (
                  <div className="grid grid-cols-2 gap-2">
                    {picks.avoids.map(r => <PickCard key={r.ticker} r={r} buy={false} />)}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">Nothing scoring negative right now.</p>
                )}
              </div>
            </div>

            <div className="mt-4">
              <Explainer>
                <p><b>What this is:</b> we score {picks.universe_size} large liquid stocks on four factors —
                  <i> momentum</i>, <i>quality</i>, <i>value</i>, and <i>sentiment</i>. Bars show how each
                  factor pushed the score up (green) or down (red).</p>
                <p className="text-yellow-300/90"><b>Honest caveat:</b> {picks.disclaimer} This is a screen,
                  do your own homework, and never invest money you can't afford to lose.</p>
              </Explainer>
            </div>
          </>
        )}
      </div>

      {/* Honest track record of past picks */}
      <TrackRecord />

      {/* Regime detail */}
      {regimeError && (
        <p className="text-xs text-red-400 text-center py-2">Could not load market regime data.</p>
      )}
      {regime && !regimeLoading && (
        <div className="card">
          <h2 className="font-semibold mb-4">Market Regime Analysis <span className="text-xs text-gray-500 font-normal ml-2">3-State Gaussian HMM on Nifty 50</span></h2>
          <div className="grid grid-cols-4 gap-4">
            {Object.entries(regime.regime_stats || {}).map(([label, stats]) => (
              <div key={label} className={`card-sm border ${
                label==='Bull'?'border-green-800/50':label==='Bear'?'border-red-800/50':'border-yellow-800/50'
              }`}>
                <p className={`font-semibold text-sm ${
                  label==='Bull'?'text-green-400':label==='Bear'?'text-red-400':'text-yellow-400'
                }`}>{label}</p>
                <p className="text-xs text-gray-500 mt-1">{stats.pct_of_time}% of time</p>
                <p className={`text-sm font-mono mt-1 ${stats.annualised_ret>=0?'text-green-400':'text-red-400'}`}>
                  {stats.annualised_ret>0?'+':''}{stats.annualised_ret}% CAGR
                </p>
              </div>
            ))}
            <div className="card-sm">
              <p className="text-xs text-gray-500">Interpretation</p>
              <p className="text-xs text-gray-300 mt-1 leading-relaxed">{regime.interpretation}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
