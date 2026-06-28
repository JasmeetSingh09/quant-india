import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPortfolio, addHolding, removeHolding } from '../api'
import Spinner from '../components/Spinner'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { Briefcase, Plus, Trash2 } from 'lucide-react'

const fmt = n => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
const COLORS = ['#22c55e','#3b82f6','#eab308','#f97316','#a855f7','#06b6d4','#ec4899','#84cc16','#ef4444','#14b8a6']

export default function Portfolio() {
  const qc = useQueryClient()
  const [ticker, setTicker] = useState('')
  const [qty, setQty] = useState('')
  const [buy, setBuy] = useState('')
  const [err, setErr] = useState('')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['portfolio'], queryFn: getPortfolio, refetchInterval: 60000,
  })
  const addMut = useMutation({
    mutationFn: addHolding,
    onSuccess: () => { qc.invalidateQueries(['portfolio']); setTicker(''); setQty(''); setBuy(''); setErr('') },
    onError: e => setErr(String(e)),
  })
  const delMut = useMutation({
    mutationFn: removeHolding,
    onSuccess: () => qc.invalidateQueries(['portfolio']),
  })

  const add = () => {
    if (!ticker || !qty || !buy) { setErr('Fill all fields'); return }
    const t = ticker.toUpperCase().endsWith('.NS') ? ticker.toUpperCase() : `${ticker.toUpperCase()}.NS`
    addMut.mutate({ ticker: t, quantity: Number(qty), buy_price: Number(buy) })
  }

  const pieData = (data?.holdings || []).map(h => ({ name: h.ticker.replace('.NS',''), value: h.current_value }))

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Briefcase size={24} className="text-green-400"/> My Portfolio</h1>
        <p className="text-gray-400 text-sm mt-0.5">Track your real holdings with live profit/loss.</p>
      </div>

      {/* Add holding */}
      <div className="card flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-[140px]">
          <label className="label">Ticker</label>
          <input className="input" placeholder="e.g. HDFCBANK" value={ticker} onChange={e=>setTicker(e.target.value)} onKeyDown={e=>e.key==='Enter'&&add()} />
        </div>
        <div className="w-28">
          <label className="label">Quantity</label>
          <input className="input" type="number" value={qty} onChange={e=>setQty(e.target.value)} />
        </div>
        <div className="w-32">
          <label className="label">Buy price (₹)</label>
          <input className="input" type="number" value={buy} onChange={e=>setBuy(e.target.value)} />
        </div>
        <button className="btn-primary" onClick={add} disabled={addMut.isPending}>
          <Plus size={14} className="inline"/> Add
        </button>
        {err && <p className="text-red-400 text-xs w-full">{err}</p>}
      </div>

      {isLoading ? <Spinner /> : isError ? (
        <div className="card text-red-400 text-sm">Backend offline — start it on port 8000.</div>
      ) : data?.count === 0 ? (
        <div className="card text-center py-16 text-gray-500">
          <Briefcase size={40} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">No holdings yet. Add your first above.</p>
        </div>
      ) : (
        <>
          {/* Summary */}
          <div className="grid grid-cols-4 gap-3">
            <div className="card-sm"><p className="stat-label">Invested</p><p className="stat-value">{fmt(data.total_invested)}</p></div>
            <div className="card-sm"><p className="stat-label">Current Value</p><p className="stat-value">{fmt(data.total_current_value)}</p></div>
            <div className="card-sm">
              <p className="stat-label">Total P&L</p>
              <p className={`stat-value ${data.total_pnl>=0?'positive':'negative'}`}>{data.total_pnl>=0?'+':''}{fmt(data.total_pnl)}</p>
              <p className={`text-xs ${data.total_pnl>=0?'positive':'negative'}`}>{data.total_pnl_pct>=0?'+':''}{data.total_pnl_pct}%</p>
            </div>
            <div className="card-sm">
              <p className="stat-label">Best / Worst</p>
              <p className="text-sm positive mt-1">▲ {data.best_performer?.ticker?.replace('.NS','')} {data.best_performer?.pnl_pct}%</p>
              <p className="text-sm negative">▼ {data.worst_performer?.ticker?.replace('.NS','')} {data.worst_performer?.pnl_pct}%</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-6">
            {/* Allocation pie */}
            <div className="card">
              <h3 className="font-semibold mb-2">Allocation</h3>
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={e=>e.name}>
                    {pieData.map((_,i)=>(<Cell key={i} fill={COLORS[i%COLORS.length]} />))}
                  </Pie>
                  <Tooltip contentStyle={{background:'#111827',border:'1px solid #374151',borderRadius:8}} formatter={v=>fmt(v)} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Holdings table */}
            <div className="card col-span-2 overflow-x-auto">
              <h3 className="font-semibold mb-3">Holdings</h3>
              <table className="w-full text-sm">
                <thead><tr className="text-gray-500 text-xs border-b border-gray-800">
                  <th className="text-left py-2">Stock</th><th className="text-right">Qty</th>
                  <th className="text-right">Buy</th><th className="text-right">Now</th>
                  <th className="text-right">Value</th><th className="text-right">P&L</th>
                  <th className="text-right">Alloc</th><th></th>
                </tr></thead>
                <tbody>
                  {data.holdings.map(h => (
                    <tr key={h.id} className="border-b border-gray-800 last:border-0">
                      <td className="py-2 font-mono text-green-400">{h.ticker.replace('.NS','')}</td>
                      <td className="text-right font-mono">{h.quantity}</td>
                      <td className="text-right font-mono">₹{h.buy_price}</td>
                      <td className="text-right font-mono">₹{h.current_price}</td>
                      <td className="text-right font-mono">{fmt(h.current_value)}</td>
                      <td className={`text-right font-mono ${h.pnl>=0?'positive':'negative'}`}>
                        {h.pnl>=0?'+':''}{fmt(h.pnl)}<span className="text-xs block">{h.pnl_pct>=0?'+':''}{h.pnl_pct}%</span>
                      </td>
                      <td className="text-right font-mono text-gray-400">{h.allocation_pct}%</td>
                      <td className="text-right">
                        <button onClick={()=>delMut.mutate(h.id)} className="text-gray-600 hover:text-red-400"><Trash2 size={13}/></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
