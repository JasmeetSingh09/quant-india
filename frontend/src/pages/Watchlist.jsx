import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getWatchlist, addToWatchlist, removeFromWatchlist } from '../api'
import Spinner from '../components/Spinner'
import { Plus, Trash2, TrendingUp, TrendingDown, Bell } from 'lucide-react'

export default function Watchlist() {
  const qc = useQueryClient()
  const [ticker, setTicker] = useState('')
  const [alertPct, setAlertPct] = useState(5)
  const [error, setError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['watchlist'],
    queryFn: getWatchlist,
    refetchInterval: 60000,
  })

  const addMut = useMutation({
    mutationFn: addToWatchlist,
    onSuccess: () => { qc.invalidateQueries(['watchlist']); setTicker(''); setError('') },
    onError:   e => setError(typeof e === 'string' ? e : 'Failed to add'),
  })

  const removeMut = useMutation({
    mutationFn: removeFromWatchlist,
    onSuccess: () => qc.invalidateQueries(['watchlist']),
  })

  const handleAdd = () => {
    if (!ticker) return
    const t = ticker.toUpperCase().includes('.NS') ? ticker.toUpperCase() : `${ticker.toUpperCase()}.NS`
    addMut.mutate({ ticker: t, price_alert_pct: alertPct, sentiment_alert: true })
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Watchlist</h1>

      {/* Add form */}
      <div className="card">
        <h2 className="font-semibold mb-4">Add Stock</h2>
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="label">NSE Ticker</label>
            <input className="input" placeholder="e.g. HDFCBANK or HDFCBANK.NS"
              value={ticker} onChange={e => setTicker(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAdd()} />
          </div>
          <div className="w-36">
            <label className="label">Alert threshold %</label>
            <input className="input" type="number" min="1" max="50" step="0.5"
              value={alertPct} onChange={e => setAlertPct(Number(e.target.value))} />
          </div>
          <div className="flex items-end">
            <button onClick={handleAdd} disabled={addMut.isPending}
              className="btn-primary flex items-center gap-2">
              <Plus size={15} />
              Add
            </button>
          </div>
        </div>
        {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
      </div>

      {/* Watchlist table */}
      {isLoading ? <Spinner /> : (
        <div className="card overflow-hidden p-0">
          {(!data?.watchlist || data.watchlist.length === 0) ? (
            <div className="p-10 text-center text-gray-500">
              <p>No stocks in watchlist yet.</p>
              <p className="text-sm mt-1">Add a ticker above to start tracking.</p>
            </div>
          ) : (
            <table className="w-full">
              <thead className="border-b border-gray-800">
                <tr className="text-left">
                  {['Stock','Added Price','Current Price','Change','Alert Threshold','Alert',''].map(h => (
                    <th key={h} className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {data.watchlist.map(item => {
                  const chg  = item.change_from_add_pct ?? 0
                  const pos  = chg >= 0
                  const fired = item.alert_triggered
                  return (
                    <tr key={item.ticker} className={`hover:bg-gray-800/50 transition-colors ${fired ? 'bg-yellow-900/10' : ''}`}>
                      <td className="px-4 py-3">
                        <p className="font-mono text-sm font-semibold text-green-400">{item.ticker.replace('.NS','')}</p>
                        <p className="text-xs text-gray-500">{item.company_name}</p>
                      </td>
                      <td className="px-4 py-3 font-mono text-sm">₹{item.added_price?.toLocaleString('en-IN')}</td>
                      <td className="px-4 py-3 font-mono text-sm">₹{item.current_price?.toLocaleString('en-IN')}</td>
                      <td className="px-4 py-3">
                        <span className={`flex items-center gap-1 text-sm font-medium ${pos?'text-green-400':'text-red-400'}`}>
                          {pos ? <TrendingUp size={13}/> : <TrendingDown size={13}/>}
                          {pos?'+':''}{chg?.toFixed(2)}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">±{item.price_alert_pct}%</td>
                      <td className="px-4 py-3">
                        {fired ? (
                          <span className="badge-yellow flex items-center gap-1 w-fit">
                            <Bell size={10} /> Triggered
                          </span>
                        ) : (
                          <span className="badge-blue w-fit">Watching</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => removeMut.mutate(item.ticker)}
                          className="p-1.5 hover:bg-red-900/30 hover:text-red-400 rounded transition-colors text-gray-600">
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
