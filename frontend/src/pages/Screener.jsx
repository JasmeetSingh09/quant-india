import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { runScreener, getScreenerSectors, getScreenerStatus } from '../api'
import Spinner from '../components/Spinner'
import { Filter, RefreshCw } from 'lucide-react'

const fmtCap = v => v == null ? '—'
  : v >= 1e12 ? `₹${(v/1e12).toFixed(2)}L Cr`
  : v >= 1e7  ? `₹${(v/1e7).toFixed(0)} Cr`
  : `₹${v}`
const num = (v, d=1) => v == null ? '—' : Number(v).toFixed(d)

export default function Screener() {
  const [f, setF] = useState({ pe_max: '', roe_min: '', market_cap_min: '', sector: '' })
  const [sortBy, setSortBy] = useState('market_cap')
  const set = (k, v) => setF(p => ({ ...p, [k]: v }))

  const { data: sectors } = useQuery({ queryKey: ['scrSectors'], queryFn: getScreenerSectors })
  const { data: status }  = useQuery({ queryKey: ['scrStatus'],  queryFn: getScreenerStatus })
  const scr = useMutation({ mutationFn: runScreener })

  const run = () => {
    const filters = {}
    if (f.pe_max)         filters.pe_max = Number(f.pe_max)
    if (f.roe_min)        filters.roe_min = Number(f.roe_min)
    if (f.market_cap_min) filters.market_cap_min = Number(f.market_cap_min) * 1e7 // Cr → ₹
    if (f.sector)         filters.sector = f.sector
    scr.mutate({ filters, sort_by: sortBy, descending: true, limit: 50 })
  }

  useEffect(() => { run() }, [])   // initial run

  const rows = scr.data?.results || []

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Filter size={24} className="text-green-400"/> Stock Screener</h1>
        <p className="text-gray-400 text-sm mt-0.5">
          Filter the NSE universe by fundamentals.
          {status && <span className="text-gray-600"> · {status.cached_stocks} stocks cached</span>}
        </p>
      </div>

      {/* Filters */}
      <div className="card grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
        <div>
          <label className="label">Max P/E</label>
          <input className="input" type="number" placeholder="e.g. 25" value={f.pe_max} onChange={e=>set('pe_max',e.target.value)} />
        </div>
        <div>
          <label className="label">Min ROE %</label>
          <input className="input" type="number" placeholder="e.g. 15" value={f.roe_min} onChange={e=>set('roe_min',e.target.value)} />
        </div>
        <div>
          <label className="label">Min Mkt Cap (₹ Cr)</label>
          <input className="input" type="number" placeholder="e.g. 50000" value={f.market_cap_min} onChange={e=>set('market_cap_min',e.target.value)} />
        </div>
        <div>
          <label className="label">Sector</label>
          <select className="input" value={f.sector} onChange={e=>set('sector',e.target.value)}>
            <option value="">All sectors</option>
            {(sectors?.sectors||[]).map(s => <option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}
          </select>
        </div>
        <button className="btn-primary h-[42px]" onClick={run} disabled={scr.isPending}>
          {scr.isPending ? 'Screening…' : 'Run Screen'}
        </button>
      </div>

      {/* Sort */}
      <div className="flex items-center gap-2 text-xs text-gray-400">
        Sort by:
        {[['market_cap','Market Cap'],['pe_ratio','P/E'],['roe','ROE'],['revenue_growth','Rev Growth'],['dividend_yield','Div Yield']].map(([v,l])=>(
          <button key={v} onClick={()=>{ setSortBy(v); setTimeout(run,0) }}
            className={`px-2 py-1 rounded ${sortBy===v?'bg-green-600 text-white':'bg-gray-800 hover:bg-gray-700'}`}>{l}</button>
        ))}
      </div>

      {/* Results */}
      <div className="card overflow-x-auto">
        {scr.isPending ? <Spinner /> : scr.isError ? (
          <p className="text-red-400 text-sm">{String(scr.error)}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs border-b border-gray-800">
                <th className="text-left py-2">Stock</th>
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
                <tr key={r.ticker} className="border-b border-gray-800 last:border-0 hover:bg-gray-800/50">
                  <td className="py-2">
                    <span className="font-mono text-green-400">{r.ticker.replace('.NS','')}</span>
                    <span className="text-gray-500 text-xs block">{r.company_name}</span>
                  </td>
                  <td className="text-gray-400 text-xs">{r.sector?.replace(/_/g,' ')}</td>
                  <td className="text-right font-mono">{r.price ? `₹${num(r.price,0)}` : '—'}</td>
                  <td className="text-right font-mono text-gray-300">{fmtCap(r.market_cap)}</td>
                  <td className="text-right font-mono">{num(r.pe_ratio)}</td>
                  <td className="text-right font-mono text-green-400">{num(r.roe)}</td>
                  <td className="text-right font-mono">{num(r.profit_margin)}</td>
                  <td className="text-right font-mono">{num(r.revenue_growth)}</td>
                  <td className="text-right font-mono">{num(r.dividend_yield,2)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan="9" className="text-center text-gray-500 py-8">No stocks match these filters.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {rows.length > 0 && <p className="text-xs text-gray-600 mt-3">{scr.data.count} matches</p>}
      </div>
    </div>
  )
}
