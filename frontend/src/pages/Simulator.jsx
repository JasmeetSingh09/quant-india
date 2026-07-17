import { useState, useEffect } from 'react'
import usePersistentState from '../usePersistentState'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { startSimulation, getSimulationPnl, getSimulations, deleteSimulation, runBacktest, getSimHistory, addSimPosition, removeSimPosition } from '../api'
import Spinner from '../components/Spinner'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line, Legend, BarChart, Bar, Cell, ReferenceLine } from 'recharts'
import { InfoTip } from '../components/Term'
import { Plus, Trash2, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react'

// Commodities you can add to a simulation (friendly name → yfinance futures ticker)
const COMMODITY_PICKS = [
  { name: 'Gold',   ticker: 'GC=F' },
  { name: 'Silver', ticker: 'SI=F' },
  { name: 'Crude',  ticker: 'CL=F' },
  { name: 'Brent',  ticker: 'BZ=F' },
  { name: 'Nat Gas',ticker: 'NG=F' },
  { name: 'Copper', ticker: 'HG=F' },
]
const COMMODITY_NAME = Object.fromEntries(COMMODITY_PICKS.map(c => [c.ticker, c.name]))
const labelOf = t => COMMODITY_NAME[t] || t.replace('.NS', '')

function HoldingsInput({ holdings, setHoldings }) {
  const [ticker, setTicker] = useState('')
  const [pct, setPct] = useState('')
  const total = Object.values(holdings).reduce((a, b) => a + b, 0)

  const add = () => {
    if (!ticker || !pct) return
    const t = ticker.toUpperCase().endsWith('.NS') ? ticker.toUpperCase() : `${ticker.toUpperCase()}.NS`
    setHoldings(h => ({ ...h, [t]: Number(pct) }))
    setTicker(''); setPct('')
  }
  const addCommodity = (t) => setHoldings(h => ({ ...h, [t]: h[t] || 10 }))

  return (
    <div>
      <div className="flex gap-2 mb-2">
        <input className="input" placeholder="Stock e.g. HDFCBANK" value={ticker} onChange={e => setTicker(e.target.value)} />
        <input className="input w-24" type="number" placeholder="%" value={pct} onChange={e => setPct(e.target.value)} min="1" max="100" />
        <button onClick={add} className="btn-primary"><Plus size={14}/></button>
      </div>
      {/* Commodity quick-add */}
      <div className="flex flex-wrap gap-1.5 mb-2">
        <span className="text-xs text-gray-500 self-center mr-1">Commodities:</span>
        {COMMODITY_PICKS.map(c => (
          <button key={c.ticker} onClick={() => addCommodity(c.ticker)}
            className="px-2 py-0.5 rounded text-xs bg-gray-800 text-amber-300 hover:bg-gray-700 border border-gray-700">
            + {c.name}
          </button>
        ))}
      </div>
      <div className="space-y-1">
        {Object.entries(holdings).map(([t, p]) => (
          <div key={t} className="flex items-center justify-between bg-gray-800 rounded px-3 py-1.5">
            <span className="font-mono text-green-400 text-sm">{labelOf(t)}</span>
            <div className="flex items-center gap-2">
              <input type="number" min="1" max="100" value={p}
                className="w-16 bg-gray-900 border border-gray-700 rounded px-2 py-0.5 text-sm text-right focus:outline-none focus:border-green-500"
                onChange={e => setHoldings(h => ({ ...h, [t]: Number(e.target.value) }))} />
              <span className="text-xs text-gray-500">%</span>
              <button onClick={() => setHoldings(h => { const n={...h}; delete n[t]; return n })}
                className="text-gray-600 hover:text-red-400"><Trash2 size={12}/></button>
            </div>
          </div>
        ))}
        {Object.keys(holdings).length > 0 && (
          <p className={`text-xs mt-1 ${Math.abs(total-100)<0.01?'text-green-400':total>100?'text-red-400':'text-yellow-400'}`}>
            Total: {total.toFixed(1)}% {Math.abs(total-100)<0.01 ? '✓' : total>100 ? '(over 100%)' : '(under 100%)'}
          </p>
        )}
      </div>
    </div>
  )
}

function PnlRow({ pos, onRemove, onTopUp, busy }) {
  const up = pos.pnl_inr >= 0
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-800 last:border-0">
      <div>
        <p className="font-mono font-semibold text-sm">{labelOf(pos.ticker)}</p>
        <p className="text-xs text-gray-500">{pos.company_name}</p>
      </div>
      <div className="text-center">
        <p className="text-xs text-gray-500">Entry</p>
        <p className="font-mono text-sm">₹{pos.entry_price?.toLocaleString('en-IN')}</p>
      </div>
      <div className="text-center">
        <p className="text-xs text-gray-500">Current</p>
        <p className="font-mono text-sm">₹{pos.current_price?.toLocaleString('en-IN')}</p>
      </div>
      <div className="text-right">
        <p className={`font-semibold text-sm ${up?'text-green-400':'text-red-400'}`}>
          {up?'+':''}₹{pos.pnl_inr?.toLocaleString('en-IN', { minimumFractionDigits:2, maximumFractionDigits:2 })}
        </p>
        <p className={`text-xs ${up?'text-green-400':'text-red-400'}`}>
          {up?'+':''}{pos.pnl_pct?.toFixed(2)}%
        </p>
      </div>
      <div className="flex items-center gap-1 ml-2">
        {onTopUp && (
          <button onClick={() => onTopUp(pos.ticker)} disabled={busy} title="Buy more (raise this stock's share)"
            className="text-gray-600 hover:text-green-400 disabled:opacity-40">
            <Plus size={14}/>
          </button>
        )}
        {onRemove && (
          <button onClick={() => onRemove(pos.ticker)} disabled={busy} title="Sell & remove from simulation"
            className="text-gray-600 hover:text-red-400 disabled:opacity-40">
            <Trash2 size={13}/>
          </button>
        )}
      </div>
    </div>
  )
}

export default function Simulator() {
  const [tab, setTab] = usePersistentState('sim.tab', 'realtime')
  const qc = useQueryClient()

  // Realtime state — persisted so switching modules never loses your setup
  const [simName, setSimName]     = usePersistentState('sim.simName', '')
  const [rtHoldings, setRtHoldings] = usePersistentState('sim.rtHoldings', {})
  const [rtCapital, setRtCapital] = usePersistentState('sim.rtCapital', 100000)
  const [activeSimName, setActiveSimName] = usePersistentState('sim.activeSimName', '')

  // Historic state — persisted
  const [htHoldings, setHtHoldings] = usePersistentState('sim.htHoldings', {})
  const [startDate, setStartDate] = usePersistentState('sim.startDate', '2019-01-01')
  const [endDate, setEndDate]     = usePersistentState('sim.endDate', '2022-12-31')
  const [htCapital, setHtCapital] = usePersistentState('sim.htCapital', 100000)
  const [btResult, setBtResult]   = usePersistentState('sim.btResult', null)

  const { data: simList } = useQuery({ queryKey: ['simList'], queryFn: getSimulations })

  // activeSimName is persisted in localStorage, so it can outlive the simulation
  // it points at (e.g. the row is gone after a redeploy wiped the DB). Left
  // alone it wedges the panel on a sim that will never load — clear it instead.
  useEffect(() => {
    if (!activeSimName || !simList?.simulations) return
    if (!simList.simulations.some(s => s.name === activeSimName)) setActiveSimName('')
  }, [simList, activeSimName])

  const { data: pnlData, isLoading: pnlLoading, refetch: refetchPnl } = useQuery({
    queryKey: ['pnl', activeSimName],
    queryFn: () => getSimulationPnl(activeSimName),
    enabled: !!activeSimName,
    refetchInterval: 60000,
  })
  // P&L history (snapshots) for the value-over-time chart
  const { data: histData } = useQuery({
    queryKey: ['simHist', activeSimName],
    queryFn: () => getSimHistory(activeSimName),
    enabled: !!activeSimName,
    staleTime: 55000,
    refetchInterval: 60000,
  })

  const startMut = useMutation({
    mutationFn: startSimulation,
    onSuccess: (d) => { qc.invalidateQueries(['simList']); setActiveSimName(d.name) },
  })

  const deleteMut = useMutation({
    mutationFn: deleteSimulation,
    onSuccess: (_, deletedName) => { qc.invalidateQueries(['simList']); if (activeSimName === deletedName) setActiveSimName('') },
  })

  const btMut = useMutation({
    mutationFn: runBacktest,
    onSuccess: d => setBtResult(d),
  })

  // Buy/sell into a RUNNING simulation (books at today's live price)
  const [addTicker, setAddTicker] = useState('')
  const [addAmount, setAddAmount] = useState(10000)
  const addPosMut = useMutation({
    mutationFn: (ticker) => addSimPosition(activeSimName, ticker, Number(addAmount)),
    onSuccess: () => { setAddTicker(''); qc.invalidateQueries(['pnl', activeSimName]); refetchPnl() },
  })
  const removePosMut = useMutation({
    mutationFn: (ticker) => removeSimPosition(activeSimName, ticker),
    onSuccess: () => { qc.invalidateQueries(['pnl', activeSimName]); refetchPnl() },
  })
  const addPos = () => {
    if (!activeSimName || !addTicker || !addAmount) return
    const t = addTicker.toUpperCase()
    const full = (t.endsWith('.NS') || t.includes('=F') || t.startsWith('^') || t.endsWith('.BO')) ? t : `${t}.NS`
    addPosMut.mutate(full)
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold">Simulator</h1>
        <div className="flex bg-gray-800 rounded-lg p-1">
          {['realtime','historic'].map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded text-sm font-medium transition-colors capitalize ${
                tab===t ? 'bg-green-600 text-white' : 'text-gray-400 hover:text-gray-200'
              }`}>{t === 'realtime' ? '⚡ Real-time' : '📈 Historic'}</button>
          ))}
        </div>
      </div>

      {tab === 'realtime' && (
        <div className="grid grid-cols-2 gap-6">
          {/* Start simulation */}
          <div className="card space-y-4">
            <h2 className="font-semibold">Start Paper Trade</h2>
            <div>
              <label className="label">Simulation name</label>
              <input className="input" placeholder="e.g. my_hdfc_bet" value={simName} onChange={e => setSimName(e.target.value)} />
            </div>
            <div>
              <label className="label">Capital (₹)</label>
              <input className="input" type="number" value={rtCapital} onChange={e => setRtCapital(Number(e.target.value))} />
            </div>
            <div>
              <label className="label">Holdings</label>
              <HoldingsInput holdings={rtHoldings} setHoldings={setRtHoldings} />
            </div>
            <button
              onClick={() => startMut.mutate({ name: simName, holdings: rtHoldings, initial_value: rtCapital })}
              disabled={startMut.isPending || !simName || Object.keys(rtHoldings).length === 0}
              className="btn-primary w-full">
              {startMut.isPending ? 'Starting...' : 'Start Simulation'}
            </button>
            {startMut.isError && <p className="text-red-400 text-xs">{String(startMut.error)}</p>}
          </div>

          {/* Active simulations */}
          <div className="space-y-3">
            <h2 className="font-semibold">Active Simulations</h2>
            {simList?.simulations?.map(s => (
              <div key={s.name}
                className={`card-sm cursor-pointer transition-colors ${activeSimName===s.name?'border-green-500':'hover:border-gray-600'}`}
                onClick={() => setActiveSimName(s.name)}>
                <div className="flex justify-between">
                  <span className="font-mono font-semibold text-green-400">{s.name}</span>
                  <button onClick={e => { e.stopPropagation(); deleteMut.mutate(s.name) }}
                    className="text-gray-600 hover:text-red-400"><Trash2 size={13}/></button>
                </div>
                <p className="text-xs text-gray-500 mt-1">₹{s.initial_value?.toLocaleString('en-IN')} · Started {s.started_at?.slice(0,10)}</p>
              </div>
            ))}

            {/* P&L display */}
            {activeSimName && (
              <div className="card space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-semibold">{activeSimName}</h3>
                  <button onClick={refetchPnl} className="p-1.5 hover:bg-gray-700 rounded transition-colors">
                    <RefreshCw size={13} className={pnlLoading ? 'animate-spin text-green-400' : 'text-gray-400'} />
                  </button>
                </div>
                {pnlLoading ? <Spinner size="sm" /> : pnlData && (
                  <>
                    <div className="flex gap-4">
                      <div>
                        <p className="text-xs text-gray-500">Portfolio Value</p>
                        <p className="text-xl font-bold font-mono">₹{pnlData.current_value?.toLocaleString('en-IN')}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Total P&L</p>
                        <p className={`text-xl font-bold font-mono ${pnlData.total_pnl_inr>=0?'text-green-400':'text-red-400'}`}>
                          {pnlData.total_pnl_inr>=0?'+':''}₹{pnlData.total_pnl_inr?.toLocaleString('en-IN', {minimumFractionDigits:2,maximumFractionDigits:2})}
                        </p>
                        <p className={`text-xs ${pnlData.total_pnl_pct>=0?'text-green-400':'text-red-400'}`}>
                          {pnlData.total_pnl_pct>=0?'+':''}{pnlData.total_pnl_pct?.toFixed(2)}%
                        </p>
                      </div>
                    </div>
                    {/* Portfolio value over time — builds as it auto-refreshes */}
                    {histData?.snapshots?.length > 1 ? (
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Portfolio value over time<InfoTip k="backtest" /></p>
                        <ResponsiveContainer width="100%" height={150}>
                          <AreaChart data={histData.snapshots}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                            <XAxis dataKey="at" stroke="#6b7280" fontSize={8} minTickGap={40}
                                   tickFormatter={t => (t?.slice(11,16) || t?.slice(5,10))} />
                            <YAxis stroke="#6b7280" fontSize={9} domain={['auto','auto']}
                                   tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                            <Tooltip contentStyle={{background:'#111827',border:'1px solid #374151',borderRadius:8}}
                                     formatter={v => [`₹${v.toLocaleString('en-IN')}`,'Value']} />
                            <ReferenceLine y={pnlData.initial_value} stroke="#6b7280" strokeDasharray="4 4"
                                           label={{value:'start',fill:'#6b7280',fontSize:8}} />
                            <Area type="monotone" dataKey="value"
                                  stroke={pnlData.total_pnl_inr>=0?'#22c55e':'#ef4444'}
                                  fill={pnlData.total_pnl_inr>=0?'#22c55e':'#ef4444'} fillOpacity={0.12} />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="text-xs text-gray-600 italic">
                        📈 Value chart builds as the simulation auto-refreshes (every 60s). Check back to watch it grow.
                      </p>
                    )}

                    {/* Per-stock P&L bar chart — immediate */}
                    {pnlData.positions?.length > 0 && (
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Profit / loss by stock</p>
                        <ResponsiveContainer width="100%" height={Math.max(80, pnlData.positions.length * 32)}>
                          <BarChart data={pnlData.positions.map(p => ({ name: labelOf(p.ticker), pnl: p.pnl_inr }))}
                                    layout="vertical" margin={{ left: 10 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                            <XAxis type="number" stroke="#6b7280" fontSize={9} tickFormatter={v => `₹${(v/1000).toFixed(1)}k`} />
                            <YAxis type="category" dataKey="name" stroke="#6b7280" fontSize={10} width={70} />
                            <Tooltip contentStyle={{background:'#111827',border:'1px solid #374151',borderRadius:8}}
                                     formatter={v => [`₹${v.toLocaleString('en-IN')}`,'P&L']} />
                            <ReferenceLine x={0} stroke="#6b7280" />
                            <Bar dataKey="pnl">
                              {pnlData.positions.map((p,i)=>(<Cell key={i} fill={p.pnl_inr>=0?'#22c55e':'#ef4444'} />))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )}

                    <div className="divide-y divide-gray-800">
                      {pnlData.positions?.map(p => (
                        <PnlRow key={p.ticker} pos={p}
                          onRemove={removePosMut.mutate} onTopUp={addPosMut.mutate}
                          busy={removePosMut.isPending || addPosMut.isPending} />
                      ))}
                    </div>

                    {/* Buy a stock into THIS running simulation, at today's price */}
                    <div className="border-t border-gray-800 pt-4 space-y-2">
                      <div className="flex items-center gap-2">
                        <Plus size={13} className="text-green-400" />
                        <p className="text-sm font-medium text-gray-200">Buy / top up in this simulation</p>
                        <span className="text-xs text-gray-500">· new stock, or type one you already hold to raise its share</span>
                      </div>
                      <div className="flex gap-2">
                        <input className="input flex-1" placeholder="Stock e.g. INFY"
                          value={addTicker} onChange={e => setAddTicker(e.target.value)}
                          onKeyDown={e => e.key === 'Enter' && addPos()} />
                        <div className="relative">
                          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-gray-500">₹</span>
                          <input className="input w-32 pl-6" type="number" min="1" step="1000" placeholder="amount"
                            value={addAmount} onChange={e => setAddAmount(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && addPos()} />
                        </div>
                        <button onClick={addPos} disabled={addPosMut.isPending || !addTicker}
                          className="btn-primary flex items-center gap-1 whitespace-nowrap">
                          {addPosMut.isPending ? '...' : <><Plus size={14}/> Buy</>}
                        </button>
                      </div>
                      {/* Commodity quick-add */}
                      <div className="flex flex-wrap gap-1.5">
                        <span className="text-xs text-gray-500 self-center mr-1">Quick add:</span>
                        {COMMODITY_PICKS.map(c => (
                          <button key={c.ticker} disabled={addPosMut.isPending}
                            onClick={() => addPosMut.mutate(c.ticker)}
                            className="px-2 py-0.5 rounded text-xs bg-gray-800 text-amber-300 hover:bg-gray-700 border border-gray-700 disabled:opacity-40">
                            + {c.name}
                          </button>
                        ))}
                      </div>
                      {addPosMut.isError && <p className="text-red-400 text-xs">{String(addPosMut.error?.response?.data?.detail || addPosMut.error)}</p>}
                      {addPosMut.isSuccess && addPosMut.data?.note && <p className="text-green-400 text-xs">✓ {addPosMut.data.note}</p>}
                      {removePosMut.isError && <p className="text-red-400 text-xs">{String(removePosMut.error?.response?.data?.detail || removePosMut.error)}</p>}
                      {removePosMut.isSuccess && removePosMut.data?.note && <p className="text-gray-400 text-xs">↩ {removePosMut.data.note}</p>}
                      <p className="text-[11px] text-gray-600 leading-snug">
                        On any holding: <span className="text-green-500">+</span> buys more (raises its share) · 🗑 sells it,
                        locking in its realized P&amp;L. Other holdings are unaffected.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'historic' && (
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-6">
            <div className="card space-y-4">
              <h2 className="font-semibold">Backtest Setup</h2>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label">Start date</label>
                  <input className="input" type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
                </div>
                <div>
                  <label className="label">End date</label>
                  <input className="input" type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
                </div>
              </div>
              <div>
                <label className="label">Capital (₹)</label>
                <input className="input" type="number" value={htCapital} onChange={e => setHtCapital(Number(e.target.value))} />
              </div>
              <div>
                <label className="label">Holdings</label>
                <HoldingsInput holdings={htHoldings} setHoldings={setHtHoldings} />
              </div>
              <button
                onClick={() => btMut.mutate({ holdings: htHoldings, start_date: startDate, end_date: endDate, initial_value: htCapital })}
                disabled={btMut.isPending || Object.keys(htHoldings).length === 0}
                className="btn-primary w-full">
                {btMut.isPending ? 'Running backtest...' : 'Run Backtest'}
              </button>
            </div>

            {/* Metrics */}
            {btResult && (
              <div className="col-span-2 space-y-4">
                <div className="grid grid-cols-4 gap-3">
                  {[
                    ['Total Return', `${btResult.total_return_pct > 0 ? '+' : ''}${btResult.total_return_pct}%`, btResult.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400', null],
                    ['Yearly growth', `${btResult.cagr_pct}%`, 'text-white', 'cagr'],
                    ['Sharpe', btResult.sharpe_ratio, 'text-white', 'sharpe'],
                    ['Worst drop', `${btResult.max_drawdown_pct}%`, 'text-red-400', 'max_drawdown'],
                    ['Sortino', btResult.sortino_ratio, 'text-white', 'sortino'],
                    ['Calmar', btResult.calmar_ratio, 'text-white', 'calmar'],
                    ['Bad-day loss', `${btResult.var_95_daily_pct}%`, 'text-red-400', 'var95'],
                    ['Up days', `${btResult.win_days_pct}%`, 'text-white', 'win_days'],
                  ].map(([l, v, c, tip]) => (
                    <div key={l} className="card-sm">
                      <p className="stat-label">{l}{tip && <InfoTip k={tip} />}</p>
                      <p className={`stat-value ${c}`}>{v ?? '—'}</p>
                    </div>
                  ))}
                </div>

                {btResult.benchmark && (
                  <div className="card-sm">
                    <div className="grid grid-cols-4 gap-4">
                      <div><p className="stat-label">Beat the index by<InfoTip k="alpha" /></p>
                        <p className={`stat-value ${btResult.benchmark.alpha>=0?'text-green-400':'text-red-400'}`}>
                          {btResult.benchmark.alpha>0?'+':''}{btResult.benchmark.alpha}%
                        </p>
                      </div>
                      <div><p className="stat-label">Nifty Return</p><p className="stat-value">{btResult.benchmark.nifty_total_return}%</p></div>
                      <div><p className="stat-label">Nifty Sharpe</p><p className="stat-value">{btResult.benchmark.nifty_sharpe}</p></div>
                      <div>
                        <p className="stat-label">Statistical Significance</p>
                        <p className={`text-sm font-semibold mt-1 ${btResult.significance_test?.alpha_significant?'text-green-400':'text-yellow-400'}`}>
                          {btResult.significance_test?.alpha_significant ? '✓ Significant (p<0.05)' : '✗ Not significant'}
                        </p>
                        <p className="text-xs text-gray-500">p={btResult.significance_test?.p_value}</p>
                      </div>
                    </div>
                  </div>
                )}

                {btResult.overfitting_warning && (
                  <div className="border border-yellow-700 bg-yellow-900/20 rounded-lg p-3">
                    <p className="text-yellow-400 text-sm font-semibold">⚠️ Overfitting Warning</p>
                    <p className="text-yellow-300/70 text-xs mt-1">
                      Out-of-sample Sharpe is less than 50% of in-sample Sharpe. Results may not generalise.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Chart */}
          {btResult?.portfolio_chart && (
            <div className="card">
              <h3 className="font-semibold mb-4">Portfolio Value vs Nifty 50</h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="date" tick={{ fontSize:10, fill:'#6b7280' }} />
                  <YAxis tick={{ fontSize:10, fill:'#6b7280' }} width={70}
                    tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                  <Tooltip contentStyle={{ background:'#111827', border:'1px solid #374151', borderRadius:'8px' }}
                    formatter={v => [`₹${v?.toLocaleString('en-IN')}`, '']} />
                  <Legend />
                  <Line data={btResult.portfolio_chart} type="monotone" dataKey="value"
                    name="Portfolio" stroke="#22c55e" dot={false} strokeWidth={2} />
                  {btResult.benchmark?.nifty_chart && (
                    <Line data={btResult.benchmark.nifty_chart} type="monotone" dataKey="value"
                      name="Nifty 50" stroke="#6b7280" dot={false} strokeWidth={1.5} strokeDasharray="4 4" />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* In/out of sample */}
          {btResult && (
            <div className="grid grid-cols-2 gap-4">
              {[btResult.in_sample, btResult.out_of_sample].map(s => s && (
                <div key={s.label} className="card-sm">
                  <p className="text-xs text-gray-500 mb-1">{s.label}</p>
                  <p className="text-xs text-gray-400">{s.period}</p>
                  <div className="flex gap-4 mt-2">
                    <div><p className="stat-label">Sharpe</p><p className="text-lg font-bold font-mono">{s.sharpe}</p></div>
                    <div><p className="stat-label">CAGR</p><p className="text-lg font-bold font-mono">{s.cagr}%</p></div>
                    <div><p className="stat-label">Max DD</p><p className="text-lg font-bold font-mono text-red-400">{s.max_drawdown}%</p></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
