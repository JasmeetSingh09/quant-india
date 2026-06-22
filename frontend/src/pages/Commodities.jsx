import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getAllCommodities, getCommodityHistory } from '../api'
import Spinner from '../components/Spinner'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { TrendingUp, TrendingDown } from 'lucide-react'

const CATEGORIES = [
  { key: 'precious_metals', label: '🥇 Precious Metals' },
  { key: 'energy',          label: '⛽ Energy'          },
  { key: 'base_metals',     label: '🔩 Base Metals'     },
  { key: 'agricultural',    label: '🌾 Agricultural'    },
  { key: 'india_etf',       label: '🇮🇳 India ETFs'     },
]

function CommodityCard({ c, onClick, selected }) {
  const up = c.change_pct >= 0
  return (
    <button onClick={onClick}
      className={`card-sm text-left w-full transition-all ${selected ? 'border-green-500 bg-green-900/10' : 'hover:border-gray-600'}`}>
      <p className="text-sm font-semibold">{c.name}</p>
      <p className="text-xs text-gray-500">{c.unit}</p>
      <div className="mt-2 flex items-end justify-between">
        <div>
          <p className="font-mono text-lg font-bold">
            {c.price_inr ? `₹${c.price_inr?.toLocaleString('en-IN')}` : `$${c.price?.toFixed(3)}`}
          </p>
          {c.price_inr && <p className="text-xs text-gray-500">${c.price?.toFixed(2)}</p>}
        </div>
        <span className={`text-sm font-semibold ${up?'text-green-400':'text-red-400'}`}>
          {up?'+':''}{c.change_pct?.toFixed(2)}%
        </span>
      </div>
    </button>
  )
}

function PriceChart({ commodityKey }) {
  const [period, setPeriod] = useState('3mo')
  const { data, isLoading } = useQuery({
    queryKey: ['comHistory', commodityKey, period],
    queryFn: () => getCommodityHistory(commodityKey, period),
    enabled: !!commodityKey,
  })
  const periods = ['1mo','3mo','6mo','1y','2y']
  const chartData = data?.history?.map(h => ({ date: h.date.slice(5), price: h.close })) || []

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">{data?.name || commodityKey} Price Chart</h3>
        <div className="flex gap-1">
          {periods.map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-2 py-1 text-xs rounded ${period===p?'bg-green-600 text-white':'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
              {p}
            </button>
          ))}
        </div>
      </div>
      {isLoading ? <Spinner size="sm" /> : (
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="cGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fontSize:10, fill:'#6b7280' }} />
            <YAxis tick={{ fontSize:10, fill:'#6b7280' }} width={60} />
            <Tooltip contentStyle={{ background:'#111827', border:'1px solid #374151', borderRadius:'8px' }}
              labelStyle={{ color:'#9ca3af' }} itemStyle={{ color:'#22c55e' }} />
            <Area type="monotone" dataKey="price" stroke="#22c55e" fill="url(#cGrad)" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export default function Commodities() {
  const [selectedCat, setSelectedCat] = useState('precious_metals')
  const [selectedKey, setSelectedKey] = useState('gold')

  const { data, isLoading } = useQuery({
    queryKey: ['allCommodities'],
    queryFn: getAllCommodities,
    refetchInterval: 120000,
  })

  const catData = data?.categories?.[selectedCat] || []

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Commodities</h1>
        {data?.usd_inr_rate && (
          <div className="card-sm flex items-center gap-3">
            <span className="text-gray-500 text-sm">USD/INR</span>
            <span className="font-mono font-bold text-lg">₹{data.usd_inr_rate}</span>
          </div>
        )}
      </div>

      {/* Category tabs */}
      <div className="flex gap-2 flex-wrap">
        {CATEGORIES.map(c => (
          <button key={c.key} onClick={() => { setSelectedCat(c.key); setSelectedKey(null) }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              selectedCat===c.key ? 'bg-green-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}>
            {c.label}
          </button>
        ))}
      </div>

      {isLoading ? <Spinner /> : (
        <>
          <div className="grid grid-cols-4 gap-3">
            {catData.map(c => (
              <CommodityCard key={c.key} c={c} selected={selectedKey===c.key}
                onClick={() => setSelectedKey(c.key)} />
            ))}
          </div>
          {selectedKey && <PriceChart commodityKey={selectedKey} />}
        </>
      )}
    </div>
  )
}
