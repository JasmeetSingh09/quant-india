import { useQuery } from '@tanstack/react-query'
import { getMCX, getRegime, getMarketNews, getPrice } from '../api'
import Spinner from '../components/Spinner'
import RegimeBadge from '../components/RegimeBadge'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link } from 'react-router-dom'

const NIFTY_STOCKS = ['RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS','ICICIBANK.NS']

function PriceTag({ ticker }) {
  const { data, isLoading } = useQuery({
    queryKey: ['price', ticker],
    queryFn: () => getPrice(ticker),
    refetchInterval: 60000,
  })
  if (isLoading) return <div className="card-sm animate-pulse h-20" />
  const pos = data?.change_pct >= 0
  return (
    <div className="card-sm">
      <p className="text-xs text-gray-500">{ticker.replace('.NS','')}</p>
      <p className="text-lg font-bold font-mono">₹{data?.price?.toLocaleString('en-IN')}</p>
      <p className={`text-xs font-medium flex items-center gap-1 mt-0.5 ${pos ? 'text-green-400' : 'text-red-400'}`}>
        {pos ? <TrendingUp size={11}/> : <TrendingDown size={11}/>}
        {pos ? '+' : ''}{data?.change_pct?.toFixed(2)}%
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
  const timeStr = mins < 60 ? `${mins}m ago` : `${Math.floor(mins/60)}h ago`
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

export default function Dashboard() {
  const { data: mcx,    isLoading: mcxLoading }    = useQuery({ queryKey: ['mcx'],    queryFn: getMCX,          refetchInterval: 120000 })
  const { data: regime, isLoading: regimeLoading }  = useQuery({ queryKey: ['regime'], queryFn: getRegime,       staleTime: 300000 })
  const { data: news,   isLoading: newsLoading }    = useQuery({ queryKey: ['mktNews'],queryFn: getMarketNews,   staleTime: 60000 })

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
            <Link to="/commodities" className="text-xs text-green-400 hover:text-green-300">View all →</Link>
          </div>
          {mcxLoading ? <Spinner size="sm" /> : (
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
            <Link to="/news" className="text-xs text-green-400 hover:text-green-300">View all →</Link>
          </div>
          {newsLoading ? <Spinner size="sm" /> : (
            <div className="space-y-1">
              {news?.articles?.slice(0, 6).map((a, i) => <NewsCard key={i} article={a} />)}
            </div>
          )}
        </div>
      </div>

      {/* Regime detail */}
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
