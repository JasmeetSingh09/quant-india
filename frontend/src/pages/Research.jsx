import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { getSentimentAlpha, getMeanReversion, runMomentumStudy, runCorrelation } from '../api'
import Spinner from '../components/Spinner'
import { FlaskConical, CheckCircle, XCircle } from 'lucide-react'

function StudyResult({ data }) {
  if (!data) return null
  const found = data.signal_found ?? (data.conclusion?.toLowerCase().includes('exists') ?? false)
  return (
    <div className="space-y-4">
      <div className={`p-4 rounded-lg border ${found ? 'bg-green-900/20 border-green-700' : 'bg-gray-800 border-gray-700'}`}>
        <div className="flex items-start gap-2">
          {found ? <CheckCircle size={16} className="text-green-400 mt-0.5 shrink-0"/> : <XCircle size={16} className="text-gray-400 mt-0.5 shrink-0"/>}
          <div>
            <p className="text-sm font-semibold mb-0.5">{data.study}</p>
            <p className="text-sm text-gray-300 leading-relaxed">{data.conclusion}</p>
          </div>
        </div>
      </div>

      {data.hypothesis && (
        <div className="card-sm">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Hypothesis</p>
          <p className="text-sm text-gray-300">{data.hypothesis}</p>
        </div>
      )}

      {data.methodology && (
        <div className="card-sm">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Methodology</p>
          <p className="text-sm text-gray-400">{data.methodology}</p>
        </div>
      )}

      {/* Sentiment alpha windows */}
      {data.results && Object.entries(data.results).map(([window, r]) => (
        <div key={window} className="card-sm">
          <p className="text-xs font-semibold text-gray-400 mb-2">Day +{r.forward_window_days} Forward Return</p>
          <div className="grid grid-cols-3 gap-3">
            {['positive_sentiment','neutral_sentiment','negative_sentiment'].map(k => {
              const s = r[k]; if (!s) return null
              const label = k.replace('_sentiment','').replace('_',' ')
              const color = k==='positive_sentiment'?'text-green-400':k==='negative_sentiment'?'text-red-400':'text-gray-400'
              return (
                <div key={k}>
                  <p className={`text-xs font-medium capitalize ${color}`}>{label}</p>
                  <p className="text-xs text-gray-500">n={s.count}</p>
                  <p className={`font-mono font-bold ${s.avg_return>=0?'text-green-400':'text-red-400'}`}>
                    {s.avg_return != null ? `${s.avg_return>0?'+':''}${s.avg_return?.toFixed(3)}%` : '—'}
                  </p>
                  {s.t_test && (
                    <p className="text-xs text-gray-500">p={s.t_test.p_value}</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {/* Momentum results */}
      {data.results?.avg_monthly_spread_pct != null && (
        <div className="grid grid-cols-2 gap-3">
          {[
            ['Winner Avg Return/month', `${data.results.avg_winner_return_pct?.toFixed(3)}%`],
            ['Loser Avg Return/month',  `${data.results.avg_loser_return_pct?.toFixed(3)}%`],
            ['Winner-Loser Spread',     `${data.results.avg_monthly_spread_pct?.toFixed(3)}%`],
            ['Months Spread > 0',       `${data.results.months_spread_positive_pct?.toFixed(1)}%`],
            ['p-value',                 data.results.t_test?.p_value],
            ['Significant',             data.results.t_test?.significant ? '✓ Yes (p<0.05)' : '✗ No'],
          ].map(([l,v]) => (
            <div key={l} className="card-sm">
              <p className="stat-label">{l}</p>
              <p className="text-sm font-bold font-mono">{v ?? '—'}</p>
            </div>
          ))}
        </div>
      )}

      {/* Correlation */}
      {data.pairs && (
        <div className="space-y-3">
          <div className="card-sm">
            <p className="text-xs text-gray-500">Portfolio volatility</p>
            <p className="text-2xl font-bold font-mono">{data.portfolio_stats?.equal_weight_annual_vol_pct}%</p>
            <p className="text-xs text-green-400 mt-0.5">
              -{data.portfolio_stats?.diversification_benefit_pct}% vs avg single stock
            </p>
          </div>
          <div className="card-sm">
            <p className="text-xs font-semibold text-gray-400 mb-2">Best Diversifier Pairs</p>
            {data.best_diversifiers?.slice(0,3).map((p, i) => (
              <div key={i} className="flex justify-between py-1 border-b border-gray-800 last:border-0 text-sm">
                <span className="font-mono text-gray-300">{p.pair.replace(/\.NS/g,'')}</span>
                <span className="text-green-400">corr={p.correlation}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const STUDIES = [
  { id: 'sentiment', label: 'Sentiment Alpha',   desc: 'Does FinBERT sentiment predict NSE returns?',    icon: '🧠' },
  { id: 'momentum',  label: 'Momentum Factor',   desc: 'Do past winners keep winning on NSE?',           icon: '📈' },
  { id: 'reversion', label: 'Mean Reversion',    desc: 'Do large moves reverse within 5 days?',          icon: '↩️' },
  { id: 'corr',      label: 'Diversification',   desc: 'Which stock pairs reduce portfolio risk?',       icon: '🔗' },
]

export default function Research() {
  const [study, setStudy]   = useState('sentiment')
  const [ticker, setTicker] = useState('HDFCBANK.NS')
  const [tickers, setTickers] = useState(['TCS.NS','INFY.NS','HDFCBANK.NS','ICICIBANK.NS','HINDUNILVR.NS','RELIANCE.NS'])

  const sentMut  = useMutation({ mutationFn: ({ticker}) => getSentimentAlpha(ticker) })
  const momMut   = useMutation({ mutationFn: ({tickers}) => runMomentumStudy({ tickers }) })
  const revMut   = useMutation({ mutationFn: ({ticker}) => getMeanReversion(ticker) })
  const corrMut  = useMutation({ mutationFn: ({tickers}) => runCorrelation({ tickers }) })

  const run = () => {
    if (study === 'sentiment') sentMut.mutate({ ticker })
    if (study === 'momentum')  momMut.mutate({ tickers })
    if (study === 'reversion') revMut.mutate({ ticker })
    if (study === 'corr')      corrMut.mutate({ tickers })
  }

  const isLoading = sentMut.isPending || momMut.isPending || revMut.isPending || corrMut.isPending
  const result    = sentMut.data || momMut.data || revMut.data || corrMut.data

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <FlaskConical size={22} className="text-green-400" />
        <div>
          <h1 className="text-2xl font-bold">Quantitative Research</h1>
          <p className="text-gray-400 text-sm">Signal studies on NSE data with statistical significance tests</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Controls */}
        <div className="card space-y-5">
          <div>
            <label className="label">Study</label>
            <div className="space-y-2">
              {STUDIES.map(s => (
                <label key={s.id} className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                  study===s.id ? 'bg-green-900/20 border border-green-700' : 'bg-gray-800 border border-transparent hover:bg-gray-750'
                }`}>
                  <input type="radio" checked={study===s.id} onChange={() => { setStudy(s.id); sentMut.reset?.(); momMut.reset?.() }} className="mt-0.5 accent-green-500" />
                  <div>
                    <p className="text-sm font-medium">{s.icon} {s.label}</p>
                    <p className="text-xs text-gray-500">{s.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {(study === 'sentiment' || study === 'reversion') && (
            <div>
              <label className="label">Ticker</label>
              <input className="input" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} placeholder="e.g. HDFCBANK.NS" />
            </div>
          )}

          {(study === 'momentum' || study === 'corr') && (
            <div>
              <label className="label">Tickers (comma separated)</label>
              <textarea className="input h-24 resize-none" value={tickers.join(',')}
                onChange={e => setTickers(e.target.value.split(',').map(t => t.trim()).filter(Boolean))} />
            </div>
          )}

          <button onClick={run} disabled={isLoading} className="btn-primary w-full">
            {isLoading ? 'Running study...' : 'Run Study'}
          </button>

          <div className="text-xs text-gray-600 space-y-1">
            <p>• All results include p-values</p>
            <p>• p &lt; 0.05 = statistically significant</p>
            <p>• Studies use real NSE price data</p>
          </div>
        </div>

        {/* Result */}
        <div className="col-span-2">
          {isLoading ? (
            <div className="card"><Spinner /></div>
          ) : result ? (
            <StudyResult data={result} />
          ) : (
            <div className="card flex flex-col items-center justify-center py-20 text-center">
              <FlaskConical size={40} className="text-gray-700 mb-4" />
              <p className="text-gray-500">Select a study and click Run</p>
              <p className="text-gray-600 text-sm mt-1">Results include hypothesis, methodology, and significance tests</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
