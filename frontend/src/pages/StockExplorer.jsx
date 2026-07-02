import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { getPrice, getMetrics, getAlphaScore, getSentiment, getStockNews, searchStocks, explainAlpha, getIntraday, getVolForecast } from '../api'
import Spinner from '../components/Spinner'
import AlphaMeter from '../components/AlphaMeter'
import StatCard from '../components/StatCard'
import { Search, TrendingUp, TrendingDown } from 'lucide-react'
import { InfoTip } from '../components/Term'
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts'

function SearchBar({ onSelect }) {
  const [q, setQ] = useState('')
  const { data, isFetching } = useQuery({
    queryKey: ['search', q],
    queryFn: () => searchStocks(q),
    enabled: q.length > 1,
    staleTime: 10000,
  })

  return (
    <div className="relative">
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          className="input pl-9"
          placeholder="Search any NSE stock — e.g. HDFC Bank, Reliance, TCS..."
          value={q}
          onChange={e => setQ(e.target.value)}
        />
      </div>
      {q.length > 1 && data?.results?.length > 0 && (
        <div className="absolute top-full mt-1 w-full bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
          {data.results.slice(0, 8).map(r => (
            <button
              key={r.ticker || r.symbol}
              onClick={() => { onSelect(r.yf_ticker || `${r.symbol}.NS`); setQ('') }}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-700 text-left transition-colors"
            >
              <span className="font-mono text-green-400 text-sm w-28 shrink-0">{r.symbol || r.ticker}</span>
              <span className="text-sm text-gray-300 truncate">{r.company_name}</span>
              <span className="ml-auto text-xs text-gray-500">{r.exchange}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function SentimentBar({ label, pct, color }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">{label}</span>
        <span style={{ color }}>{pct?.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

export default function StockExplorer() {
  const [ticker, setTicker] = useState('RELIANCE.NS')
  const explain = useMutation({ mutationFn: explainAlpha })

  const { data: price,   isLoading: priceLoading }   = useQuery({ queryKey: ['price',   ticker], queryFn: () => getPrice(ticker),      enabled: !!ticker, refetchInterval: (q) => (q.state.data?.feed_active ? 30000 : false) })
  const { data: metrics, isLoading: metricsLoading }  = useQuery({ queryKey: ['metrics', ticker], queryFn: () => getMetrics(ticker),    enabled: !!ticker, staleTime: 300000 })
  const { data: alpha,   isLoading: alphaLoading }    = useQuery({ queryKey: ['alpha',   ticker], queryFn: () => getAlphaScore(ticker), enabled: !!ticker, staleTime: 120000 })
  const { data: sent,    isLoading: sentLoading }     = useQuery({ queryKey: ['sent',    ticker], queryFn: () => getSentiment(ticker),  enabled: !!ticker, staleTime: 120000 })
  const { data: newsD,   isLoading: newsLoading }     = useQuery({ queryKey: ['news',    ticker], queryFn: () => getStockNews(ticker),  enabled: !!ticker, staleTime: 60000 })
  // Intraday chart — auto-refreshes every 30s ONLY while NSE is open (9:15-15:30 IST).
  // When the market is closed the price is frozen, so we stop polling (no more
  // phantom movement after 3:30pm from the delayed feed jittering).
  const { data: intraday } = useQuery({
    queryKey: ['intraday', ticker],
    queryFn: () => getIntraday(ticker, '5m', '1d'),
    enabled: !!ticker,
    refetchInterval: price?.feed_active ? 30000 : false,
  })
  // GARCH volatility forecast (validated to beat naive)
  const { data: vol } = useQuery({
    queryKey: ['vol', ticker],
    queryFn: () => getVolForecast(ticker),
    enabled: !!ticker,
    staleTime: 300000,
  })

  const pos = (price?.change_pct ?? 0) >= 0
  const m   = metrics?.metrics || {}
  const h   = metrics?.health  || {}
  const s   = sent?.summary    || {}

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Stock Explorer</h1>

      <SearchBar onSelect={setTicker} />

      {priceLoading ? <Spinner /> : price && (
        <>
          {/* Price header */}
          <div className="card">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-gray-400 text-sm">{m.company_name || ticker}</p>
                <p className="text-4xl font-bold font-mono mt-1">
                  ₹{price.price?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </p>
                <div className={`flex items-center gap-2 mt-1 ${pos ? 'text-green-400' : 'text-red-400'}`}>
                  {pos ? <TrendingUp size={16}/> : <TrendingDown size={16}/>}
                  <span className="font-semibold">{pos?'+':''}{price.change?.toFixed(2)}</span>
                  <span>({pos?'+':''}{price.change_pct?.toFixed(2)}%)</span>
                  <span className="text-gray-500 text-sm">today</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500">{m.sector}</p>
                <p className="text-xs text-gray-500 mt-0.5">{m.industry}</p>
                <p className="text-xs text-gray-500 mt-0.5">Mkt Cap: {m.market_cap_fmt}</p>
              </div>
            </div>
          </div>

          {/* Intraday chart (auto-refreshes every 30s) */}
          {intraday?.candles?.length > 0 && (
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold text-sm">Price Chart <span className="text-xs text-gray-500 font-normal">({intraday.resolution}{price?.market_open ? ' · updates every 30s' : ''})</span></h2>
                {price?.market_open ? (
                  <span className="text-xs text-gray-500">
                    <span className="inline-block w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse mr-1"></span>
                    live · {intraday.fetched_at} · ~15 min delayed
                  </span>
                ) : (
                  <span className="text-xs text-gray-500">
                    <span className="inline-block w-1.5 h-1.5 bg-gray-500 rounded-full mr-1"></span>
                    Market closed · showing last close
                  </span>
                )}
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={intraday.candles}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="time" stroke="#6b7280" fontSize={9} minTickGap={50}
                         tickFormatter={t => t.split(' ')[1] || t} />
                  <YAxis stroke="#6b7280" fontSize={10} domain={['auto','auto']}
                         tickFormatter={v => `₹${v}`} />
                  <Tooltip contentStyle={{ background:'#111827', border:'1px solid #374151', borderRadius:8 }}
                           formatter={v => [`₹${v}`, 'Price']} />
                  <Line type="monotone" dataKey="price" stroke={pos ? '#22c55e' : '#ef4444'}
                        dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="grid grid-cols-3 gap-6">
            {/* Metrics */}
            <div className="space-y-3">
              <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">Valuation</h2>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['P/E Ratio',   m.pe_ratio?.toFixed(1), 'pe_ratio'],
                  ['Forward P/E', m.forward_pe?.toFixed(1), 'pe_ratio'],
                  ['EV/EBITDA',   m.ev_ebitda?.toFixed(1), 'ev_ebitda'],
                  ['Enterprise Value', m.enterprise_value_fmt || null, null],
                  ['EBITDA',      m.ebitda_fmt || null, null],
                  ['P/B Ratio',   m.price_to_book?.toFixed(2), null],
                  ['ROE',         m.roe ? `${(m.roe*100).toFixed(1)}%` : null, 'roe'],
                  ['ROA',         m.roa ? `${(m.roa*100).toFixed(1)}%` : null, 'roa'],
                  ['Profit Margin', m.profit_margin ? `${(m.profit_margin*100).toFixed(1)}%` : null, 'profit_margin'],
                  ['D/E Ratio',   m.debt_to_equity?.toFixed(2), 'debt_to_equity'],
                ].map(([l, v, tip]) => (
                  <StatCard key={l} label={l} value={v} tip={tip} />
                ))}
              </div>
              {/* Health score */}
              {h.health_score != null && (
                <div className="card-sm">
                  <div className="flex justify-between items-center">
                    <p className="text-sm font-medium">Financial Health</p>
                    <span className={`text-2xl font-bold font-mono ${
                      h.grade==='A'?'text-green-400':h.grade==='B'?'text-blue-400':
                      h.grade==='C'?'text-yellow-400':'text-red-400'
                    }`}>{h.grade}</span>
                  </div>
                  <div className="mt-2 h-2 bg-gray-800 rounded-full">
                    <div className="h-full bg-green-500 rounded-full" style={{ width: `${h.health_score}%` }} />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{h.health_score}/100</p>
                </div>
              )}
              {/* GARCH volatility forecast */}
              {vol?.forecast_annual_vol_pct != null && (
                <div className="card-sm">
                  <div className="flex justify-between items-center">
                    <p className="text-sm font-medium">Risk Forecast <span className="text-xs text-gray-500 font-normal">GARCH</span></p>
                    <span className="text-2xl font-bold font-mono text-yellow-400">{vol.forecast_annual_vol_pct}%</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Expected annual volatility · current daily {vol.current_daily_vol_pct}%
                  </p>
                </div>
              )}
            </div>

            {/* Alpha score */}
            <div className="space-y-3">
              <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">Alpha Score<InfoTip k="alpha_score" /></h2>
              {alphaLoading ? <Spinner size="sm" /> : alpha && (
                <div className="card">
                  <AlphaMeter score={alpha.alpha_score} />
                  <div className="mt-5 space-y-3">
                    {Object.entries(alpha.contributions || {}).map(([factor, contrib]) => (
                      <div key={factor}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-gray-400 capitalize">{factor}<InfoTip k={factor} /></span>
                          <span className={contrib >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {contrib > 0 ? '+' : ''}{contrib?.toFixed(1)} pts
                          </span>
                        </div>
                        <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${contrib >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                            style={{ width: `${Math.min(100, Math.abs(contrib) * 2)}%` }}
                          />
                        </div>
                        <p className="text-xs text-gray-600 mt-0.5">
                          {alpha.factors?.[factor]?.interpretation}
                        </p>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-gray-600 mt-3">
                    Confidence: {(alpha.confidence * 100)?.toFixed(0)}%
                  </p>
                  <button
                    onClick={() => explain.mutate(ticker)}
                    disabled={explain.isPending}
                    className="btn-ghost w-full mt-3 text-xs">
                    {explain.isPending ? 'Analysing (30-60s)…' : '🔍 Why this signal?'}
                  </button>
                </div>
              )}

              {/* Reasoned explanation panel */}
              {explain.data && explain.data.ticker === ticker && (
                <div className="card space-y-3">
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider">Verdict</p>
                    <p className="text-sm text-gray-200 mt-1 leading-relaxed">{explain.data.verdict}</p>
                  </div>

                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Reasons</p>
                    <div className="space-y-1.5">
                      {explain.data.reasons?.map((r, i) => (
                        <div key={i} className="flex gap-2 text-xs">
                          <span className={r.direction === 'positive' ? 'text-green-400' : 'text-red-400'}>
                            {r.direction === 'positive' ? '▲' : '▼'}
                          </span>
                          <span className="text-gray-300 leading-snug">{r.text}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {explain.data.factor_validation && (
                    <div className={`p-3 rounded-lg border text-xs leading-relaxed ${
                      explain.data.factor_validation.status === 'confirmed' ? 'border-green-700 bg-green-900/20 text-green-200' :
                      explain.data.factor_validation.status === 'warning'   ? 'border-red-700 bg-red-900/20 text-red-200' :
                      'border-gray-700 bg-gray-800 text-gray-300'
                    }`}>
                      <p className="font-semibold mb-1">Fama-French reality check</p>
                      {explain.data.factor_validation.text}
                    </div>
                  )}
                </div>
              )}
              {explain.isError && (
                <p className="text-xs text-red-400">{String(explain.error)}</p>
              )}
            </div>

            {/* Sentiment */}
            <div className="space-y-3">
              <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">News Sentiment</h2>
              {sentLoading ? <Spinner size="sm" /> : s.total_articles > 0 && (
                <div className="card space-y-4">
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Overall</p>
                    <span className={`text-lg font-bold capitalize ${
                      s.overall_sentiment==='positive'?'text-green-400':
                      s.overall_sentiment==='negative'?'text-red-400':'text-gray-400'
                    }`}>{s.overall_sentiment}</span>
                    <span className="text-xs text-gray-500 ml-2">({s.total_articles} articles)</span>
                  </div>
                  <div className="space-y-2">
                    <SentimentBar label="Positive" pct={s.positive_pct} color="#22c55e" />
                    <SentimentBar label="Neutral"  pct={s.neutral_pct}  color="#6b7280" />
                    <SentimentBar label="Negative" pct={s.negative_pct} color="#ef4444" />
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Trend</p>
                    <p className={`text-sm font-medium capitalize mt-0.5 ${
                      s.trend==='improving'?'text-green-400':
                      s.trend==='worsening'?'text-red-400':'text-gray-400'
                    }`}>{s.trend}</p>
                  </div>
                  {s.most_negative_headline && (
                    <div>
                      <p className="text-xs text-gray-500">Most negative headline</p>
                      <p className="text-xs text-red-300 mt-0.5 leading-relaxed">"{s.most_negative_headline}"</p>
                    </div>
                  )}
                </div>
              )}

              {/* News list */}
              <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider pt-2">Latest Headlines</h2>
              {newsLoading ? <Spinner size="sm" /> : (
                <div className="space-y-2">
                  {newsD?.articles?.slice(0, 5).map((a, i) => (
                    <a key={i} href={a.url} target="_blank" rel="noreferrer"
                      className="block card-sm hover:border-gray-600 transition-colors">
                      <p className="text-xs text-gray-300 leading-snug">{a.title}</p>
                      <p className="text-xs text-gray-600 mt-1">
                        {a.source} · {a.published_minutes_ago}m ago
                      </p>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
