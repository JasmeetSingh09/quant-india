import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  getPrice, getMetrics, getAlphaScore, getSentiment, getStockNews,
  searchStocks, explainAlpha, getIntraday, getVolForecast,
  runScreener, getScreenerSectors, getScreenerStatus,
} from '../api'
import Spinner from '../components/Spinner'
import AlphaMeter from '../components/AlphaMeter'
import StatCard from '../components/StatCard'
import { Search, TrendingUp, TrendingDown, ArrowLeft, ExternalLink, Users, Building2, Filter, RefreshCw } from 'lucide-react'
import { InfoTip } from '../components/Term'
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts'

// ─── helpers ──────────────────────────────────────────────────────────────────
const fmtCap = v => v == null ? '—'
  : v >= 1e12 ? `₹${(v / 1e12).toFixed(2)}L Cr`
  : v >= 1e7  ? `₹${(v / 1e7).toFixed(0)} Cr`
  : `₹${v}`
const num = (v, d = 1) => v == null ? '—' : Number(v).toFixed(d)
const pct = (v, d = 1) => v == null ? '—' : `${(v * 100).toFixed(d)}%`

// ─── SearchBar ────────────────────────────────────────────────────────────────
function SearchBar({ onSelect, placeholder }) {
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
          placeholder={placeholder || 'Search any NSE stock — e.g. HDFC Bank, Reliance, TCS...'}
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

// ─── SentimentBar ─────────────────────────────────────────────────────────────
function SentimentBar({ label, pct: value, color }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">{label}</span>
        <span style={{ color }}>{value?.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full">
        <div className="h-full rounded-full" style={{ width: `${value}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

// ─── 52-week range bar ────────────────────────────────────────────────────────
function WeekRange({ low, high, current }) {
  if (!low || !high || !current) return null
  const pct = Math.min(100, Math.max(0, ((current - low) / (high - low)) * 100))
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 mb-1.5">
        <span>52W Low <span className="text-gray-300 font-mono">₹{num(low, 0)}</span></span>
        <span>52W High <span className="text-gray-300 font-mono">₹{num(high, 0)}</span></span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full relative">
        <div
          className="h-2 rounded-full bg-gradient-to-r from-red-600 via-yellow-500 to-green-500"
          style={{ width: `${pct}%`, minWidth: 8 }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-gray-900 shadow"
          style={{ left: `calc(${pct}% - 6px)` }}
        />
      </div>
      <p className="text-xs text-gray-500 mt-1 text-center">
        Current at <span className="text-gray-300">{pct.toFixed(0)}%</span> of 52-week range
      </p>
    </div>
  )
}

// ─── Balance Sheet card ───────────────────────────────────────────────────────
function BalanceItem({ label, value, highlight }) {
  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-[11px] text-gray-500">{label}</p>
      <p className={`text-sm font-mono font-semibold ${highlight || 'text-gray-200'}`}>{value || '—'}</p>
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// LIST VIEW (Screener)
// ═════════════════════════════════════════════════════════════════════════════
function StocksList({ onSelect }) {
  const navigate = useNavigate()
  const [f, setF]       = useState({ pe_max: '', roe_min: '', market_cap_min: '', sector: '' })
  const [sortBy, setSortBy] = useState('market_cap')
  const set = (k, v) => setF(p => ({ ...p, [k]: v }))

  const { data: sectors } = useQuery({ queryKey: ['scrSectors'], queryFn: getScreenerSectors })
  const { data: status }  = useQuery({ queryKey: ['scrStatus'],  queryFn: getScreenerStatus })
  const scr = useMutation({ mutationFn: runScreener })

  const run = () => {
    const filters = {}
    if (f.pe_max)         filters.pe_max = Number(f.pe_max)
    if (f.roe_min)        filters.roe_min = Number(f.roe_min)
    if (f.market_cap_min) filters.market_cap_min = Number(f.market_cap_min) * 1e7
    if (f.sector)         filters.sector = f.sector
    scr.mutate({ filters, sort_by: sortBy, descending: true, limit: 50 })
  }

  useEffect(() => { run() }, [])

  const rows = scr.data?.results || []

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Stocks</h1>
          <p className="text-gray-400 text-sm mt-0.5">
            NSE universe — filter by fundamentals, click any row to open full analysis.
            {status && <span className="text-gray-600"> · {status.cached_stocks} stocks cached</span>}
          </p>
        </div>
      </div>

      {/* Search */}
      <SearchBar
        onSelect={onSelect}
        placeholder="Jump directly to any stock — e.g. Reliance, HDFC Bank, TCS..."
      />

      {/* Filters */}
      <div className="card grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
        <div>
          <label className="label">Max P/E</label>
          <input className="input" type="number" placeholder="e.g. 25" value={f.pe_max}
            onChange={e => set('pe_max', e.target.value)} />
        </div>
        <div>
          <label className="label">Min ROE %</label>
          <input className="input" type="number" placeholder="e.g. 15" value={f.roe_min}
            onChange={e => set('roe_min', e.target.value)} />
        </div>
        <div>
          <label className="label">Min Mkt Cap (₹ Cr)</label>
          <input className="input" type="number" placeholder="e.g. 50000" value={f.market_cap_min}
            onChange={e => set('market_cap_min', e.target.value)} />
        </div>
        <div>
          <label className="label">Sector</label>
          <select className="input" value={f.sector} onChange={e => set('sector', e.target.value)}>
            <option value="">All sectors</option>
            {(sectors?.sectors || []).map(s => (
              <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>
        <button className="btn-primary h-[42px]" onClick={run} disabled={scr.isPending}>
          {scr.isPending ? 'Screening…' : 'Run Screen'}
        </button>
      </div>

      {/* Sort */}
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <Filter size={12} className="text-gray-600" /> Sort by:
        {[['market_cap','Market Cap'],['pe_ratio','P/E'],['roe','ROE'],['revenue_growth','Rev Growth'],['dividend_yield','Div Yield']].map(([v, l]) => (
          <button key={v} onClick={() => { setSortBy(v); setTimeout(run, 0) }}
            className={`px-2.5 py-1 rounded-md ${sortBy === v ? 'bg-green-600 text-white' : 'bg-gray-800 hover:bg-gray-700'}`}>
            {l}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="card overflow-x-auto">
        {scr.isPending ? (
          <div className="py-8"><Spinner /></div>
        ) : scr.isError ? (
          <p className="text-red-400 text-sm">{String(scr.error)}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs border-b border-gray-800">
                <th className="text-left py-2.5 pr-4">Stock</th>
                <th className="text-left">Sector</th>
                <th className="text-right">Price</th>
                <th className="text-right">Mkt Cap</th>
                <th className="text-right">P/E</th>
                <th className="text-right">ROE %</th>
                <th className="text-right">Margin %</th>
                <th className="text-right">Rev Gr %</th>
                <th className="text-right">Div %</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr
                  key={r.ticker}
                  onClick={() => onSelect(r.ticker)}
                  className="border-b border-gray-800 last:border-0 hover:bg-gray-800/50 cursor-pointer transition-colors group"
                >
                  <td className="py-2.5 pr-4">
                    <span className="font-mono text-green-400 group-hover:underline font-medium">
                      {r.ticker.replace('.NS', '')}
                    </span>
                    <span className="text-gray-500 text-xs block">{r.company_name}</span>
                  </td>
                  <td className="text-gray-400 text-xs">{r.sector?.replace(/_/g, ' ')}</td>
                  <td className="text-right font-mono">{r.price ? `₹${num(r.price, 0)}` : '—'}</td>
                  <td className="text-right font-mono text-gray-300">{fmtCap(r.market_cap)}</td>
                  <td className="text-right font-mono">{num(r.pe_ratio)}</td>
                  <td className="text-right font-mono text-green-400">{num(r.roe)}</td>
                  <td className="text-right font-mono">{num(r.profit_margin)}</td>
                  <td className="text-right font-mono">{num(r.revenue_growth)}</td>
                  <td className="text-right font-mono">{num(r.dividend_yield, 2)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan="9" className="text-center text-gray-500 py-10">
                    No stocks match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        {rows.length > 0 && (
          <p className="text-xs text-gray-600 mt-3">{scr.data?.count} matches</p>
        )}
      </div>
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// DETAIL VIEW
// ═════════════════════════════════════════════════════════════════════════════
function StockDetail({ ticker, onBack }) {
  const explain = useMutation({ mutationFn: explainAlpha })

  const { data: price,   isLoading: priceLoading }  = useQuery({ queryKey: ['price',   ticker], queryFn: () => getPrice(ticker),      enabled: !!ticker, refetchInterval: (q) => (q.state.data?.feed_active ? 30000 : false) })
  const { data: metrics, isLoading: metricsLoading } = useQuery({ queryKey: ['metrics', ticker], queryFn: () => getMetrics(ticker),    enabled: !!ticker, staleTime: 300000 })
  const { data: alpha,   isLoading: alphaLoading }   = useQuery({ queryKey: ['alpha',   ticker], queryFn: () => getAlphaScore(ticker), enabled: !!ticker, staleTime: 120000 })
  const { data: sent,    isLoading: sentLoading }    = useQuery({ queryKey: ['sent',    ticker], queryFn: () => getSentiment(ticker),  enabled: !!ticker, staleTime: 120000 })
  const { data: newsD,   isLoading: newsLoading }    = useQuery({ queryKey: ['news',    ticker], queryFn: () => getStockNews(ticker),  enabled: !!ticker, staleTime: 60000 })
  const { data: intraday } = useQuery({
    queryKey: ['intraday', ticker],
    queryFn: () => getIntraday(ticker, '5m', '1d'),
    enabled: !!ticker,
    refetchInterval: price?.feed_active ? 30000 : false,
  })
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

      {/* Back + title row */}
      <div className="flex items-center gap-4">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-100 transition-colors"
        >
          <ArrowLeft size={15} /> Stocks
        </button>
        <span className="text-gray-700">/</span>
        <span className="font-mono font-bold text-green-400">{ticker.replace('.NS', '')}</span>
        {m.company_name && <span className="text-gray-400 text-sm">{m.company_name}</span>}
      </div>

      {/* Company intro */}
      {!metricsLoading && m.company_name && (
        <div className="card space-y-4">
          <div className="flex items-start justify-between gap-6">
            <div className="flex-1">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-xl font-bold">{m.company_name}</h1>
                <span className="font-mono text-green-400 text-sm font-semibold bg-green-950/40 border border-green-800/50 px-2 py-0.5 rounded">
                  {ticker.replace('.NS', '')}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                {m.sector && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-950/50 border border-blue-800/40 text-blue-300">
                    {m.sector}
                  </span>
                )}
                {m.industry && (
                  <span className="text-xs text-gray-500">{m.industry}</span>
                )}
              </div>
              {m.description && (
                <p className="text-sm text-gray-400 leading-relaxed mt-3 max-w-3xl">
                  {m.description}
                </p>
              )}
            </div>
            <div className="shrink-0 grid grid-cols-2 gap-3 text-right">
              {m.market_cap_fmt && (
                <div>
                  <p className="text-[11px] text-gray-500">Market Cap</p>
                  <p className="text-sm font-semibold font-mono">{m.market_cap_fmt}</p>
                </div>
              )}
              {m.beta != null && (
                <div>
                  <p className="text-[11px] text-gray-500">Beta</p>
                  <p className="text-sm font-semibold font-mono">{num(m.beta, 2)}</p>
                </div>
              )}
              {m.employees && (
                <div>
                  <p className="text-[11px] text-gray-500">Employees</p>
                  <p className="text-sm font-semibold font-mono">{m.employees?.toLocaleString('en-IN')}</p>
                </div>
              )}
              {m.dividend_yield && (
                <div>
                  <p className="text-[11px] text-gray-500">Div Yield</p>
                  <p className="text-sm font-semibold font-mono text-green-400">{pct(m.dividend_yield)}</p>
                </div>
              )}
            </div>
          </div>

          {/* 52-week range */}
          {(m.week_52_low || m.week_52_high) && (
            <div className="pt-3 border-t border-gray-800">
              <WeekRange low={m.week_52_low} high={m.week_52_high} current={price?.price} />
            </div>
          )}

          {/* Website */}
          {m.website && (
            <a
              href={m.website}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-green-400 transition-colors"
            >
              <ExternalLink size={11} /> {m.website.replace(/^https?:\/\//, '')}
            </a>
          )}
        </div>
      )}

      {/* Price header */}
      {priceLoading ? <Spinner /> : price && (
        <>
          <div className="card">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-gray-500 text-xs uppercase tracking-wider mb-1">Current Price</p>
                <p className="text-4xl font-bold font-mono">
                  ₹{price.price?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </p>
                <div className={`flex items-center gap-2 mt-1 ${pos ? 'text-green-400' : 'text-red-400'}`}>
                  {pos ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                  <span className="font-semibold">{pos ? '+' : ''}{price.change?.toFixed(2)}</span>
                  <span>({pos ? '+' : ''}{price.change_pct?.toFixed(2)}%)</span>
                  <span className="text-gray-500 text-sm">today</span>
                </div>
              </div>
              <div className="text-right text-xs text-gray-500 space-y-0.5">
                {m.pe_ratio && <p>P/E <span className="text-gray-300 font-mono">{num(m.pe_ratio)}</span></p>}
                {m.price_to_book && <p>P/B <span className="text-gray-300 font-mono">{num(m.price_to_book, 2)}</span></p>}
                {m.total_revenue_fmt && <p>Revenue <span className="text-gray-300 font-mono">{m.total_revenue_fmt}</span></p>}
              </div>
            </div>
          </div>

          {/* Intraday chart */}
          {intraday?.candles?.length > 0 && (
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold text-sm">
                  Price Chart{' '}
                  <span className="text-xs text-gray-500 font-normal">
                    ({intraday.resolution}{price?.market_open ? ' · updates every 30s' : ''})
                  </span>
                </h2>
                {price?.market_open ? (
                  <span className="text-xs text-gray-500">
                    <span className="inline-block w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse mr-1" />
                    live · {intraday.fetched_at} · ~15 min delayed
                  </span>
                ) : (
                  <span className="text-xs text-gray-500">
                    <span className="inline-block w-1.5 h-1.5 bg-gray-500 rounded-full mr-1" />
                    Market closed · showing last close
                  </span>
                )}
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={intraday.candles}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="time" stroke="#6b7280" fontSize={9} minTickGap={50}
                    tickFormatter={t => t.split(' ')[1] || t} />
                  <YAxis stroke="#6b7280" fontSize={10} domain={['auto', 'auto']}
                    tickFormatter={v => `₹${v}`} />
                  <Tooltip
                    contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                    formatter={v => [`₹${v}`, 'Price']}
                  />
                  <Line type="monotone" dataKey="price" stroke={pos ? '#22c55e' : '#ef4444'}
                    dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Balance sheet strip */}
          {(m.total_revenue_fmt || m.ebitda_fmt || m.total_debt_fmt || m.cash_fmt || m.free_cashflow_fmt) && (
            <div className="card">
              <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">
                Balance Sheet Snapshot
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 divide-x divide-gray-800">
                <BalanceItem label="Total Revenue"  value={m.total_revenue_fmt}  />
                <div className="pl-4"><BalanceItem label="EBITDA"         value={m.ebitda_fmt}         /></div>
                <div className="pl-4"><BalanceItem label="Total Debt"     value={m.total_debt_fmt}     highlight="text-red-300" /></div>
                <div className="pl-4"><BalanceItem label="Cash & Equiv."  value={m.cash_fmt}           highlight="text-green-300" /></div>
                <div className="pl-4"><BalanceItem label="Free Cash Flow" value={m.free_cashflow_fmt}  highlight={m.free_cashflow_fmt?.startsWith('-') ? 'text-red-300' : 'text-green-300'} /></div>
              </div>
              {(m.revenue_growth != null || m.earnings_growth != null) && (
                <div className="flex gap-6 mt-4 pt-3 border-t border-gray-800 text-xs">
                  {m.revenue_growth != null && (
                    <div>
                      <span className="text-gray-500">Revenue Growth </span>
                      <span className={`font-mono font-semibold ${m.revenue_growth >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {m.revenue_growth >= 0 ? '+' : ''}{pct(m.revenue_growth)}
                      </span>
                    </div>
                  )}
                  {m.earnings_growth != null && (
                    <div>
                      <span className="text-gray-500">Earnings Growth </span>
                      <span className={`font-mono font-semibold ${m.earnings_growth >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {m.earnings_growth >= 0 ? '+' : ''}{pct(m.earnings_growth)}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Three-column analysis */}
          <div className="grid grid-cols-3 gap-6">

            {/* Column 1 — Valuation & Health */}
            <div className="space-y-3">
              <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">Valuation</h2>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['P/E Ratio',      m.pe_ratio?.toFixed(1),        'pe_ratio'],
                  ['Forward P/E',    m.forward_pe?.toFixed(1),       'pe_ratio'],
                  ['PEG Ratio',      m.peg_ratio?.toFixed(2),        null],
                  ['EV/EBITDA',      m.ev_ebitda?.toFixed(1),        'ev_ebitda'],
                  ['P/B Ratio',      m.price_to_book?.toFixed(2),    null],
                  ['EV',             m.enterprise_value_fmt || null, null],
                  ['ROE',            m.roe ? `${(m.roe * 100).toFixed(1)}%` : null,             'roe'],
                  ['ROA',            m.roa ? `${(m.roa * 100).toFixed(1)}%` : null,             'roa'],
                  ['Gross Margin',   m.gross_margin ? `${(m.gross_margin * 100).toFixed(1)}%` : null, null],
                  ['Op. Margin',     m.operating_margin ? `${(m.operating_margin * 100).toFixed(1)}%` : null, null],
                  ['Profit Margin',  m.profit_margin ? `${(m.profit_margin * 100).toFixed(1)}%` : null, 'profit_margin'],
                  ['D/E Ratio',      m.debt_to_equity?.toFixed(2),   'debt_to_equity'],
                  ['Current Ratio',  m.current_ratio?.toFixed(2),    null],
                  ['Quick Ratio',    m.quick_ratio?.toFixed(2),      null],
                ].map(([l, v, tip]) => (
                  <StatCard key={l} label={l} value={v} tip={tip} />
                ))}
              </div>

              {/* Financial health */}
              {h.health_score != null && (
                <div className="card-sm">
                  <div className="flex justify-between items-center">
                    <p className="text-sm font-medium">Financial Health</p>
                    <span className={`text-2xl font-bold font-mono ${
                      h.grade === 'A' ? 'text-green-400' :
                      h.grade === 'B' ? 'text-blue-400' :
                      h.grade === 'C' ? 'text-yellow-400' : 'text-red-400'
                    }`}>{h.grade}</span>
                  </div>
                  <div className="mt-2 h-2 bg-gray-800 rounded-full">
                    <div className="h-full bg-green-500 rounded-full" style={{ width: `${h.health_score}%` }} />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{h.health_score}/100</p>
                </div>
              )}

              {/* GARCH volatility */}
              {vol?.forecast_annual_vol_pct != null && (
                <div className="card-sm">
                  <div className="flex justify-between items-center">
                    <p className="text-sm font-medium">
                      Risk Forecast <span className="text-xs text-gray-500 font-normal">GARCH</span>
                    </p>
                    <span className="text-2xl font-bold font-mono text-yellow-400">
                      {vol.forecast_annual_vol_pct}%
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Expected annual volatility · daily {vol.current_daily_vol_pct}%
                  </p>
                </div>
              )}
            </div>

            {/* Column 2 — Alpha score */}
            <div className="space-y-3">
              <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
                Alpha Score<InfoTip k="alpha_score" />
              </h2>
              {alphaLoading ? <Spinner size="sm" /> : alpha && (
                <div className="card">
                  <AlphaMeter score={alpha.alpha_score} />
                  <div className="mt-5 space-y-3">
                    {Object.entries(alpha.contributions || {}).map(([factor, contrib]) => (
                      <div key={factor}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-gray-400 capitalize">
                            {factor}<InfoTip k={factor} />
                          </span>
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
                    className="btn-ghost w-full mt-3 text-xs"
                  >
                    {explain.isPending ? 'Analysing (30-60s)…' : '🔍 Why this signal?'}
                  </button>
                </div>
              )}

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

            {/* Column 3 — Sentiment & News */}
            <div className="space-y-3">
              <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">News Sentiment</h2>
              {sentLoading ? <Spinner size="sm" /> : s.total_articles > 0 && (
                <div className="card space-y-4">
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Overall</p>
                    <span className={`text-lg font-bold capitalize ${
                      s.overall_sentiment === 'positive' ? 'text-green-400' :
                      s.overall_sentiment === 'negative' ? 'text-red-400' : 'text-gray-400'
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
                      s.trend === 'improving' ? 'text-green-400' :
                      s.trend === 'worsening' ? 'text-red-400' : 'text-gray-400'
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

// ═════════════════════════════════════════════════════════════════════════════
// MAIN EXPORT — routes between list & detail
// ═════════════════════════════════════════════════════════════════════════════
export default function StockExplorer() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [ticker, setTicker] = useState(searchParams.get('ticker') || '')

  const selectTicker = (t) => {
    if (!t) return
    setTicker(t)
    setSearchParams({ ticker: t }, { replace: true })
  }

  const goBack = () => {
    setTicker('')
    setSearchParams({}, { replace: true })
  }

  // Follow URL changes (deep-links from dashboard, etc.)
  useEffect(() => {
    const p = searchParams.get('ticker')
    if (p && p !== ticker) setTicker(p)
    if (!p && ticker) setTicker('')
  }, [searchParams])

  if (ticker) {
    return <StockDetail ticker={ticker} onBack={goBack} />
  }
  return <StocksList onSelect={selectTicker} />
}
