import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { findPairs, analyzePair, backtestPair } from '../api'
import Spinner from '../components/Spinner'
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine
} from 'recharts'
import { GitCompareArrows, Plus, Trash2 } from 'lucide-react'
import { InfoTip } from '../components/Term'

const BANK_DEFAULT = ['HDFCBANK.NS','ICICIBANK.NS','SBIN.NS','AXISBANK.NS','KOTAKBANK.NS']

function TickerList({ tickers, setTickers }) {
  const [t, setT] = useState('')
  const add = () => {
    if (!t) return
    const clean = t.toUpperCase().endsWith('.NS') ? t.toUpperCase() : `${t.toUpperCase()}.NS`
    setTickers(prev => [...new Set([...prev, clean])]); setT('')
  }
  return (
    <div>
      <div className="flex gap-2 mb-2">
        <input className="input" placeholder="Add ticker" value={t} onChange={e=>setT(e.target.value)} onKeyDown={e=>e.key==='Enter'&&add()} />
        <button onClick={add} className="btn-ghost"><Plus size={14}/></button>
      </div>
      <div className="flex flex-wrap gap-2">
        {tickers.map(x => (
          <span key={x} className="flex items-center gap-1 px-2 py-1 bg-gray-800 rounded text-xs font-mono text-green-400">
            {x.replace('.NS','')}
            <button onClick={()=>setTickers(p=>p.filter(y=>y!==x))} className="hover:text-red-400 ml-1">×</button>
          </span>
        ))}
      </div>
    </div>
  )
}

export default function PairsTrading() {
  const [tickers, setTickers] = useState(BANK_DEFAULT)
  const [a, setA] = useState('HDFCBANK.NS')
  const [b, setB] = useState('ICICIBANK.NS')

  const find = useMutation({ mutationFn: findPairs })
  const ana  = useMutation({ mutationFn: analyzePair })
  const bt   = useMutation({ mutationFn: backtestPair })

  const actionColor = act => act==='long'?'text-green-400':act==='short'?'text-red-400':'text-gray-400'

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><GitCompareArrows size={24} className="text-green-400"/> Pairs Trading</h1>
        <p className="text-gray-400 text-sm mt-0.5">
          Statistical arbitrage — market-neutral. Find cointegrated pairs, then trade their spread when it diverges.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: find pairs */}
        <div className="card space-y-4">
          <div>
            <label className="label">Universe to scan</label>
            <TickerList tickers={tickers} setTickers={setTickers} />
          </div>
          <button className="btn-primary w-full" onClick={()=>find.mutate({ tickers })} disabled={find.isPending}>
            {find.isPending ? 'Testing cointegration…' : 'Find Cointegrated Pairs'}
          </button>

          {find.data && (
            <div className="space-y-1 pt-2">
              <p className="text-xs text-gray-500">{find.data.interpretation}</p>
              {find.data.tradeable_pairs?.map(p => (
                <button key={p.pair} onClick={()=>{ setA(p.stock_a); setB(p.stock_b) }}
                  className="w-full flex justify-between items-center bg-gray-800 hover:bg-gray-700 rounded px-3 py-2 text-xs">
                  <span className="font-mono text-green-400">{p.stock_a.replace('.NS','')}/{p.stock_b.replace('.NS','')}</span>
                  <span className="text-gray-400">p={p.pvalue}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: analyze + backtest */}
        <div className="col-span-2 space-y-4">
          <div className="card">
            <div className="flex items-end gap-2 mb-4">
              <div className="flex-1">
                <label className="label">Stock A</label>
                <input className="input" value={a} onChange={e=>setA(e.target.value.toUpperCase())} />
              </div>
              <div className="flex-1">
                <label className="label">Stock B</label>
                <input className="input" value={b} onChange={e=>setB(e.target.value.toUpperCase())} />
              </div>
              <button className="btn-primary" onClick={()=>ana.mutate({ stock_a:a, stock_b:b })} disabled={ana.isPending}>Analyse</button>
              <button className="btn-ghost" onClick={()=>bt.mutate({ stock_a:a, stock_b:b })} disabled={bt.isPending}>Backtest</button>
            </div>

            {(ana.isPending||bt.isPending) && <Spinner size="sm" />}
            {ana.isError && <p className="text-red-400 text-sm">{String(ana.error)}</p>}

            {/* Signal */}
            {ana.data && (
              <div className="space-y-4">
                <div className="grid grid-cols-4 gap-3">
                  <div className="card-sm"><p className="stat-label">Hedge ratio<InfoTip k="hedge_ratio" /></p><p className="stat-value">{ana.data.hedge_ratio}</p></div>
                  <div className="card-sm"><p className="stat-label">Linkage test<InfoTip k="cointegration" /></p><p className="stat-value">{ana.data.cointegration_pvalue}</p>
                    <p className={`text-xs ${ana.data.is_cointegrated?'positive':'negative'}`}>{ana.data.is_cointegrated?'linked ✓ (tradeable)':'not linked'}</p></div>
                  <div className="card-sm"><p className="stat-label">Snap-back time<InfoTip k="half_life" /></p><p className="stat-value">{ana.data.half_life_days ?? '∞'}<span className="text-xs text-gray-500"> d</span></p></div>
                  <div className="card-sm"><p className="stat-label">Gap stretch<InfoTip k="zscore" /></p><p className="stat-value">{ana.data.current_zscore}</p></div>
                </div>
                <div className={`p-3 rounded-lg border ${ana.data.action==='long'?'border-green-700 bg-green-900/20':ana.data.action==='short'?'border-red-700 bg-red-900/20':'border-gray-700 bg-gray-800'}`}>
                  <p className={`font-semibold ${actionColor(ana.data.action)}`}>{ana.data.signal}</p>
                  <p className="text-xs text-gray-400 mt-1">{ana.data.interpretation}</p>
                </div>
                {/* z-score chart */}
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={ana.data.zscore_history}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="date" stroke="#6b7280" fontSize={9} tick={{fontSize:9}} minTickGap={40} />
                    <YAxis stroke="#6b7280" fontSize={10} domain={[-4,4]} />
                    <Tooltip contentStyle={{background:'#111827',border:'1px solid #374151',borderRadius:8}} />
                    <ReferenceLine y={2}  stroke="#dc2626" strokeDasharray="4 4" label={{value:'+2σ short',fill:'#dc2626',fontSize:9}} />
                    <ReferenceLine y={-2} stroke="#16a34a" strokeDasharray="4 4" label={{value:'-2σ long',fill:'#16a34a',fontSize:9}} />
                    <ReferenceLine y={0}  stroke="#6b7280" />
                    <Line type="monotone" dataKey="z" stroke="#eab308" dot={false} strokeWidth={1.5} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Backtest */}
            {bt.data && (
              <div className="mt-6 pt-6 border-t border-gray-800 space-y-3">
                <h3 className="font-semibold text-sm">Backtest (market-neutral)</h3>
                <div className="grid grid-cols-5 gap-2">
                  {[['Return',`${bt.data.total_return_pct}%`,null],['Sharpe',bt.data.sharpe_ratio,'sharpe'],['Max drop',`${bt.data.max_drawdown_pct}%`,'max_drawdown'],['Trades',bt.data.num_trades,null],['Win rate',`${bt.data.win_rate_pct}%`,null]].map(([l,v,tip])=>(
                    <div key={l} className="card-sm"><p className="stat-label">{l}{tip&&<InfoTip k={tip} />}</p><p className="text-lg font-bold font-mono">{v}</p></div>
                  ))}
                </div>
                <ResponsiveContainer width="100%" height={180}>
                  <AreaChart data={bt.data.equity_curve}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="date" stroke="#6b7280" fontSize={9} minTickGap={40} />
                    <YAxis stroke="#6b7280" fontSize={10} domain={['auto','auto']} />
                    <Tooltip contentStyle={{background:'#111827',border:'1px solid #374151',borderRadius:8}} />
                    <Area type="monotone" dataKey="value" stroke="#22c55e" fill="#22c55e" fillOpacity={0.15} />
                  </AreaChart>
                </ResponsiveContainer>
                <p className="text-xs text-gray-500">{bt.data.interpretation}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
