import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { getFactorRegression } from '../api'
import Spinner from '../components/Spinner'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'
import { Layers } from 'lucide-react'
import { InfoTip } from '../components/Term'
import Explainer from '../components/Explainer'

export default function Factors() {
  const [ticker, setTicker] = useState('HDFCBANK.NS')
  const reg = useMutation({ mutationFn: getFactorRegression })

  const run = () => {
    const t = ticker.toUpperCase().endsWith('.NS') ? ticker.toUpperCase() : `${ticker.toUpperCase()}.NS`
    setTicker(t); reg.mutate(t)
  }

  const d = reg.data
  const betaData = d ? [
    { name: 'Market', value: d.coefficients.market_beta.coefficient, sig: d.coefficients.market_beta.significant },
    { name: 'Size (SMB)', value: d.coefficients.size_beta_smb.coefficient, sig: d.coefficients.size_beta_smb.significant },
    { name: 'Value (HML)', value: d.coefficients.value_beta_hml.coefficient, sig: d.coefficients.value_beta_hml.significant },
  ] : []

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Layers size={24} className="text-green-400"/> Fama-French Factor Model</h1>
        <p className="text-gray-400 text-sm mt-0.5">
          Is a stock's return real skill (alpha), or just exposure to market, size, and value factors? The academic gold standard.
        </p>
      </div>

      <div className="card">
        <div className="flex gap-2 items-end max-w-md">
          <div className="flex-1">
            <label className="label">NSE Ticker</label>
            <input className="input" value={ticker} onChange={e=>setTicker(e.target.value)} onKeyDown={e=>e.key==='Enter'&&run()} />
          </div>
          <button className="btn-primary" onClick={run} disabled={reg.isPending}>
            {reg.isPending ? 'Running…' : 'Run Regression'}
          </button>
        </div>
      </div>

      {reg.isPending && <div className="card"><Spinner /></div>}
      {reg.isError && <div className="card text-red-400 text-sm">{String(reg.error)}</div>}

      {d && (
        <>
          <div className="grid grid-cols-4 gap-3">
            <div className={`card-sm border ${d.alpha_significant && d.alpha_annual_pct>0?'border-green-700':d.alpha_significant?'border-red-700':'border-gray-800'}`}>
              <p className="stat-label">Real skill (alpha)<InfoTip k="alpha" /></p>
              <p className={`stat-value ${d.alpha_annual_pct>=0?'positive':'negative'}`}>{d.alpha_annual_pct>0?'+':''}{d.alpha_annual_pct}%</p>
              <p className="text-xs text-gray-500">{d.alpha_significant?'real, not luck ✓':'could be luck'}</p>
            </div>
            <div className="card-sm"><p className="stat-label">Explained<InfoTip k="r_squared" /></p><p className="stat-value">{Math.round(d.r_squared*100)}%</p><p className="text-xs text-gray-500">of its movement</p></div>
            <div className="card-sm"><p className="stat-label">Data points</p><p className="stat-value">{d.observations}</p><p className="text-xs text-gray-500">trading days</p></div>
            <div className="card-sm"><p className="stat-label">Market link<InfoTip k="market_beta" /></p><p className="stat-value">{d.coefficients.market_beta.coefficient}</p><p className="text-xs text-gray-500">{d.factor_tilts.market}</p></div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {/* Factor loadings chart */}
            <div className="card">
              <h3 className="font-semibold mb-3">Factor Loadings (β)</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={betaData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis type="number" stroke="#6b7280" fontSize={10} />
                  <YAxis type="category" dataKey="name" stroke="#6b7280" fontSize={11} width={80} />
                  <Tooltip contentStyle={{background:'#111827',border:'1px solid #374151',borderRadius:8}} />
                  <Bar dataKey="value">
                    {betaData.map((e,i)=>(<Cell key={i} fill={e.value>=0?'#22c55e':'#dc2626'} fillOpacity={e.sig?0.9:0.35} />))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="text-xs text-gray-500 mt-2">Faded bars = not statistically significant.</p>
            </div>

            {/* Detail table */}
            <div className="card">
              <h3 className="font-semibold mb-3">Regression Detail</h3>
              <table className="w-full text-sm">
                <thead><tr className="text-gray-500 text-xs border-b border-gray-800">
                  <th className="text-left py-2">Factor</th>
                  <th className="text-right">β<InfoTip k="beta" /></th>
                  <th className="text-right">strength<InfoTip k="t_stat" /></th>
                  <th className="text-right">p-value<InfoTip k="pvalue" /></th>
                </tr></thead>
                <tbody>
                  {Object.entries(d.coefficients).map(([name,c])=>(
                    <tr key={name} className="border-b border-gray-800 last:border-0">
                      <td className="py-2 text-gray-300">{name.replace(/_/g,' ')}</td>
                      <td className="text-right font-mono">{c.coefficient}</td>
                      <td className="text-right font-mono">{c.t_stat}</td>
                      <td className={`text-right font-mono ${c.significant?'text-green-400':'text-gray-500'}`}>{c.p_value}{c.significant?' ✓':''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-3 flex gap-2 text-xs">
                <span className="badge-blue">{d.factor_tilts.size}</span>
                <span className="badge-blue">{d.factor_tilts.value}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <Explainer>
              <p><b>What we just did:</b> we broke this stock's returns into pieces to find out
                <i> why</i> it made (or lost) money — was it skill, or just riding well-known patterns?</p>
              <p><b>The factors:</b> "Market" = how much it just follows the overall market.
                "Size" = whether it behaves like a small or large company. "Value" = whether it acts
                like a cheap (value) or pricey (growth) stock.</p>
              <p><b>"Real skill (alpha)":</b> the return left over <i>after</i> removing those patterns.
                {d.alpha_significant && d.alpha_annual_pct > 0
                  ? ' Here it is genuinely positive — a rare sign of real edge.'
                  : ' Here there’s no proven extra skill — its returns are explained by the patterns above, which is the normal result for most stocks.'}</p>
            </Explainer>
            <p className="text-xs text-gray-600 mt-2">{d.note}</p>
          </div>
        </>
      )}

      {!d && !reg.isPending && (
        <div className="card text-center py-16 text-gray-500">
          <Layers size={40} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">Enter a ticker and run the 3-factor regression.</p>
        </div>
      )}
    </div>
  )
}
