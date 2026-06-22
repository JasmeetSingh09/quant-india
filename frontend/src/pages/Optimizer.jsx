import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { runMVO, runBL, getFrontier, autoOptimize, runHRP } from '../api'
import Spinner from '../components/Spinner'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceDot, LineChart, Line } from 'recharts'
import { Plus, Trash2 } from 'lucide-react'
import { InfoTip } from '../components/Term'

const DEFAULT_TICKERS = ['HDFCBANK.NS','TCS.NS','RELIANCE.NS','INFY.NS','HINDUNILVR.NS','SBIN.NS']

function TickerList({ tickers, setTickers }) {
  const [t, setT] = useState('')
  const add = () => {
    if (!t) return
    const clean = t.toUpperCase().endsWith('.NS') ? t.toUpperCase() : `${t.toUpperCase()}.NS`
    setTickers(prev => [...new Set([...prev, clean])])
    setT('')
  }
  return (
    <div>
      <div className="flex gap-2 mb-2">
        <input className="input" placeholder="Add ticker" value={t} onChange={e => setT(e.target.value)} onKeyDown={e => e.key==='Enter'&&add()} />
        <button onClick={add} className="btn-ghost"><Plus size={14}/></button>
      </div>
      <div className="flex flex-wrap gap-2">
        {tickers.map(t => (
          <span key={t} className="flex items-center gap-1 px-2 py-1 bg-gray-800 rounded text-xs font-mono text-green-400">
            {t.replace('.NS','')}
            <button onClick={() => setTickers(p => p.filter(x => x!==t))} className="hover:text-red-400 ml-1">×</button>
          </span>
        ))}
      </div>
    </div>
  )
}

function WeightBar({ ticker, weight }) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="font-mono text-green-400 text-sm w-28 shrink-0">{ticker.replace('.NS','')}</span>
      <div className="flex-1 h-2 bg-gray-800 rounded-full">
        <div className="h-full bg-green-500 rounded-full transition-all" style={{ width: `${weight}%` }} />
      </div>
      <span className="text-sm font-bold w-12 text-right">{weight}%</span>
    </div>
  )
}

export default function Optimizer() {
  const [tab, setTab]       = useState('mvo')
  const [tickers, setTickers] = useState(DEFAULT_TICKERS)
  const [target, setTarget]   = useState('max_sharpe')
  const [maxWeight, setMaxWeight] = useState(35)   // cap per stock (%) to force diversification

  const mvoMut     = useMutation({ mutationFn: runMVO })
  const blMut      = useMutation({ mutationFn: data => runBL({ ...data, tickers }) })
  const frontierMut= useMutation({ mutationFn: getFrontier })
  const autoMut    = useMutation({ mutationFn: autoOptimize })
  const hrpMut     = useMutation({ mutationFn: runHRP })

  const run = () => {
    if (tab === 'mvo')      mvoMut.mutate({ tickers, target, max_weight: maxWeight / 100 })
    if (tab === 'hrp')      hrpMut.mutate({ tickers })
    if (tab === 'frontier') frontierMut.mutate({ tickers, n_points: 50 })
    if (tab === 'auto')     autoMut.mutate({ tickers })
  }

  const isLoading = mvoMut.isPending || blMut.isPending || frontierMut.isPending || autoMut.isPending || hrpMut.isPending
  const mvoResult     = mvoMut.data
  const frontierResult= frontierMut.data
  const autoResult    = autoMut.data
  const hrpResult     = hrpMut.data

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Portfolio Optimizer</h1>

      <div className="grid grid-cols-3 gap-6">
        {/* Left panel */}
        <div className="card space-y-5">
          <div>
            <label className="label">Tickers</label>
            <TickerList tickers={tickers} setTickers={setTickers} />
          </div>

          <div>
            <label className="label">Algorithm</label>
            <div className="space-y-1">
              {[
                ['mvo',      'Markowitz (classic)',     'Best return for the risk — but can pile into one stock'],
                ['hrp',      'Smart Diversify (HRP)',   'Spreads money sensibly by grouping similar stocks (2016)'],
                ['frontier', 'Risk-vs-Return Map',      'Shows every best risk/return combo on a curve'],
                ['auto',     'AI-Guided Mix',           'Uses news sentiment to tilt the portfolio'],
              ].map(([v, l, d]) => (
                <label key={v} className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                  tab===v ? 'bg-green-900/20 border border-green-700' : 'bg-gray-800 hover:bg-gray-750 border border-transparent'
                }`}>
                  <input type="radio" checked={tab===v} onChange={() => setTab(v)} className="mt-0.5 accent-green-500" />
                  <div>
                    <p className="text-sm font-medium">{l}</p>
                    <p className="text-xs text-gray-500">{d}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {tab === 'mvo' && (
            <>
              <div>
                <label className="label">Objective</label>
                <select className="input" value={target} onChange={e => setTarget(e.target.value)}>
                  <option value="max_sharpe">Maximise Sharpe Ratio</option>
                  <option value="min_variance">Minimise Variance</option>
                  <option value="max_return">Maximise Return</option>
                </select>
              </div>
              <div>
                <label className="label">Max weight per stock: {maxWeight}%</label>
                <input type="range" min="10" max="100" step="5" value={maxWeight}
                       onChange={e => setMaxWeight(Number(e.target.value))}
                       className="w-full accent-green-500" />
                <p className="text-xs text-gray-500 mt-1">
                  Lower = more diversified. 100% lets it concentrate in one stock.
                </p>
              </div>
            </>
          )}

          <button onClick={run} disabled={isLoading || tickers.length < 2} className="btn-primary w-full">
            {isLoading ? 'Optimising...' : 'Run Optimiser'}
          </button>
        </div>

        {/* Results */}
        <div className="col-span-2 space-y-4">
          {isLoading && <div className="card"><Spinner /></div>}

          {/* MVO result */}
          {mvoResult && !mvoResult.error && (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3">
                {[
                  ['Expected Return', `${mvoResult.expected_annual_return_pct}%`, null],
                  ['Expected Bumpiness', `${mvoResult.expected_annual_vol_pct}%`, 'volatility'],
                  ['Sharpe Ratio',    mvoResult.expected_sharpe, 'sharpe'],
                  ['Better than equal-split', `${mvoResult.vs_equal_weight?.sharpe_improvement > 0 ? '+' : ''}${mvoResult.vs_equal_weight?.sharpe_improvement}`, 'sharpe'],
                ].map(([l,v,tip]) => (
                  <div key={l} className="card-sm">
                    <p className="stat-label">{l}{tip && <InfoTip k={tip} />}</p>
                    <p className="stat-value">{v}</p>
                  </div>
                ))}
              </div>
              <div className="card">
                <h3 className="font-semibold mb-3">Optimal Weights</h3>
                {Object.entries(mvoResult.optimal_pct || {})
                  .sort(([,a],[,b]) => b-a)
                  .map(([t,w]) => <WeightBar key={t} ticker={t} weight={w} />)}
              </div>
            </div>
          )}

          {/* HRP result */}
          {hrpResult && !hrpResult.error && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                {[
                  ['Expected Return', `${hrpResult.expected_annual_return_pct}%`, null],
                  ['Expected Bumpiness', `${hrpResult.expected_annual_vol_pct}%`, 'volatility'],
                  ['Sharpe Ratio',    hrpResult.expected_sharpe, 'sharpe'],
                ].map(([l,v,tip]) => (
                  <div key={l} className="card-sm">
                    <p className="stat-label">{l}{tip && <InfoTip k={tip} />}</p>
                    <p className="stat-value">{v}</p>
                  </div>
                ))}
              </div>
              <div className="card">
                <h3 className="font-semibold mb-1">HRP Weights <span className="text-xs text-gray-500 font-normal ml-2">López de Prado 2016 — clustering, no matrix inversion</span></h3>
                <p className="text-xs text-gray-500 mb-3">Cluster order: {hrpResult.cluster_order?.map(t=>t.replace('.NS','')).join(' → ')}</p>
                {Object.entries(hrpResult.optimal_pct || {})
                  .sort(([,a],[,b]) => b-a)
                  .map(([t,w]) => <WeightBar key={t} ticker={t} weight={w} />)}
                <div className="mt-3 p-3 bg-gray-800 rounded-lg">
                  <p className="text-xs text-gray-300">{hrpResult.interpretation}</p>
                </div>
              </div>
            </div>
          )}

          {/* Frontier */}
          {frontierResult && !frontierResult.error && (
            <div className="card">
              <h3 className="font-semibold mb-4">Efficient Frontier</h3>
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="vol_pct" name="Volatility %" unit="%" tick={{ fontSize:10, fill:'#6b7280' }} label={{ value:'Annual Volatility %', position:'insideBottom', offset:-5, fill:'#6b7280', fontSize:10 }} />
                  <YAxis dataKey="return_pct" name="Return %" unit="%" tick={{ fontSize:10, fill:'#6b7280' }} label={{ value:'Annual Return %', angle:-90, position:'insideLeft', fill:'#6b7280', fontSize:10 }} />
                  <Tooltip cursor={{ strokeDasharray:'3 3' }} contentStyle={{ background:'#111827', border:'1px solid #374151', borderRadius:'8px' }}
                    formatter={(v, n) => [`${v?.toFixed(2)}%`, n]} />
                  <Scatter data={frontierResult.frontier} fill="#22c55e" opacity={0.7} />
                  {frontierResult.tangency_portfolio && (
                    <ReferenceDot x={frontierResult.tangency_portfolio.vol_pct} y={frontierResult.tangency_portfolio.return_pct}
                      r={6} fill="#f59e0b" label={{ value:'Max Sharpe', fill:'#f59e0b', fontSize:10 }} />
                  )}
                  {frontierResult.equal_weight_portfolio && (
                    <ReferenceDot x={frontierResult.equal_weight_portfolio.vol_pct} y={frontierResult.equal_weight_portfolio.return_pct}
                      r={6} fill="#6b7280" label={{ value:'Equal Weight', fill:'#9ca3af', fontSize:10 }} />
                  )}
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Auto BL result */}
          {autoResult && !autoResult.error && (
            <div className="space-y-4">
              <div className="card">
                <h3 className="font-semibold mb-1">Alpha Scores → Black-Litterman Weights</h3>
                <p className="text-xs text-gray-500 mb-4">FinBERT sentiment views automatically converted to portfolio weights</p>
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Alpha Scores</p>
                    {Object.entries(autoResult.alpha_scores || {}).sort(([,a],[,b])=>b-a).map(([t,s]) => (
                      <div key={t} className="flex justify-between items-center py-1.5 border-b border-gray-800">
                        <span className="font-mono text-sm">{t.replace('.NS','')}</span>
                        <span className={`font-bold text-sm ${s>0?'text-green-400':'text-red-400'}`}>{s>0?'+':''}{s?.toFixed(1)}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider">BL Weights</p>
                    {Object.entries(autoResult.bl_result?.bl_pct || {}).sort(([,a],[,b])=>b-a).map(([t,w]) => (
                      <WeightBar key={t} ticker={t} weight={w} />
                    ))}
                  </div>
                </div>
                <div className="mt-4 p-3 bg-gray-800 rounded-lg">
                  <p className="text-xs text-gray-300">{autoResult.bl_result?.interpretation}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
