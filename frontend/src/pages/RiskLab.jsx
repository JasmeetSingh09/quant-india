import { useState } from 'react'
import usePersistentState from '../usePersistentState'
import { useMutation } from '@tanstack/react-query'
import { getDeflatedSharpe, getPositionSize, runBacktest, getFactorRegression } from '../api'
import { InfoTip } from '../components/Term'
import Explainer from '../components/Explainer'
import { ShieldAlert, Loader2 } from 'lucide-react'

export default function RiskLab() {
  // Deflated Sharpe
  const [ticker, setTicker] = usePersistentState('risk.ticker', 'RELIANCE.NS')
  const [trials, setTrials] = usePersistentState('risk.trials', 1)
  const dsr = useMutation({ mutationFn: ({ t, n }) => getDeflatedSharpe(t, n) })

  // Position sizing
  const [ret, setRet] = usePersistentState('risk.ret', 18)
  const [vol, setVol] = usePersistentState('risk.vol', 25)
  const [tgt, setTgt] = usePersistentState('risk.tgt', 15)
  const pos = useMutation({ mutationFn: getPositionSize })

  const runDsr = () => {
    const t = ticker.toUpperCase().endsWith('.NS') ? ticker.toUpperCase() : `${ticker.toUpperCase()}.NS`
    setTicker(t); dsr.mutate({ t, n: Number(trials) })
  }
  const runPos = () => pos.mutate({ annual_return_pct: Number(ret), annual_vol_pct: Number(vol), target_vol_pct: Number(tgt) })

  // Portfolio tail risk (surfaces VaR / CVaR / Sharpe / Sortino / Calmar from the backtester)
  const [pf, setPf] = usePersistentState('risk.pf', { 'HDFCBANK.NS': 40, 'TCS.NS': 30, 'RELIANCE.NS': 30 })
  const pfTotal = Object.values(pf).reduce((a, b) => a + Number(b), 0)
  const pfOk = Math.abs(pfTotal - 100) < 0.01
  const tail = useMutation({ mutationFn: () => runBacktest({ holdings: pf, start_date: '2021-01-01' }) })
  const setPfW = (t, v) => setPf({ ...pf, [t]: Number(v) })
  const renamePf = (o, n) => { const { [o]: w, ...r } = pf; setPf({ ...r, [n.toUpperCase()]: w }) }
  const rmPf = t => { const { [t]: _, ...r } = pf; setPf(r) }

  // Fama-French factor exposure (surfaces the existing regression)
  const [facT, setFacT] = usePersistentState('risk.facT', 'HDFCBANK.NS')
  const fac = useMutation({ mutationFn: () => getFactorRegression(facT.toUpperCase().endsWith('.NS') ? facT.toUpperCase() : `${facT.toUpperCase()}.NS`) })

  const td = tail.data
  const fd = fac.data

  const d = dsr.data
  const dsrColor = d ? (d.edge_is_real ? 'text-green-400' : 'text-red-400') : ''

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldAlert size={24} className="text-green-400"/> Risk Lab</h1>
        <p className="text-gray-400 text-sm mt-0.5">
          Institutional-grade rigor: is a result real or luck, and how much should you bet?
        </p>
      </div>

      {/* ── Deflated Sharpe ── */}
      <div className="card space-y-4">
        <div>
          <h2 className="font-semibold">Backtest Reality Check
            <InfoTip k="significant" />
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Deflated Sharpe Ratio (López de Prado) — the probability a track record is real, not luck.
            Raise "strategies tried" to watch multiple-testing destroy a good-looking result.
          </p>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[140px]">
            <label className="label">Ticker</label>
            <input className="input" value={ticker} onChange={e=>setTicker(e.target.value)} onKeyDown={e=>e.key==='Enter'&&runDsr()} />
          </div>
          <div className="w-44">
            <label className="label">Strategies tried: {trials}</label>
            <input type="range" min="1" max="1000" value={trials} onChange={e=>setTrials(Number(e.target.value))} className="w-full accent-green-500" />
          </div>
          <button className="btn-primary" onClick={runDsr} disabled={dsr.isPending}>
            {dsr.isPending ? <Loader2 className="animate-spin" size={16}/> : 'Check'}
          </button>
        </div>
        {dsr.isError && <p className="text-red-400 text-xs">{String(dsr.error)}</p>}
        {d && (
          <div className="grid grid-cols-4 gap-3">
            <div className="card-sm"><p className="stat-label">Annual Sharpe</p><p className="stat-value">{d.annualised_sharpe}</p></div>
            <div className="card-sm"><p className="stat-label">Deflated Sharpe</p><p className={`stat-value ${dsrColor}`}>{Math.round(d.deflated_sharpe*100)}%</p><p className="text-xs text-gray-500">prob. real</p></div>
            <div className="card-sm"><p className="stat-label">Luck benchmark</p><p className="stat-value">{d.luck_benchmark_sharpe}</p><p className="text-xs text-gray-500">SR from {d.n_trials} trials</p></div>
            <div className="card-sm"><p className="stat-label">Verdict</p><p className={`text-sm font-bold mt-1 ${dsrColor}`}>{d.edge_is_real?'LIKELY REAL':'LIKELY LUCK'}</p></div>
          </div>
        )}
        {d && (
          <Explainer>
            <p><b>What we just did:</b> we measured how good {d.ticker?.replace('.NS','')}'s past
              returns were <i>for the risk taken</i> (that's the "Sharpe ratio" — higher is better),
              then checked whether that's genuine or just luck.</p>
            <p><b>Why "strategies tried" matters:</b> if you test {d.n_trials} different ideas,
              some will look great purely by chance. So we raised the bar — the "luck benchmark"
              ({d.luck_benchmark_sharpe}) is the score you'd expect from luck alone after {d.n_trials} tries.</p>
            <p><b>The result:</b> there's about <b className={dsrColor}>{Math.round(d.deflated_sharpe*100)}%</b> chance
              this is a <b>real edge</b>. {d.edge_is_real
                ? 'That’s high (above 95%) — this looks genuine, not luck.'
                : 'That’s not high enough to trust — it’s probably luck or too small a sample, not a reliable pattern. Real edges are rare, so this is the normal, honest answer for most stocks.'}</p>
          </Explainer>
        )}
      </div>

      {/* ── Position Sizing ── */}
      <div className="card space-y-4">
        <div>
          <h2 className="font-semibold">Position Sizer</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Kelly criterion + volatility targeting — how much of your capital to risk on one position.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div><label className="label">Expected return %/yr</label><input className="input" type="number" value={ret} onChange={e=>setRet(e.target.value)} /></div>
          <div><label className="label">Volatility %/yr<InfoTip k="volatility" /></label><input className="input" type="number" value={vol} onChange={e=>setVol(e.target.value)} /></div>
          <div><label className="label">Target volatility %</label><input className="input" type="number" value={tgt} onChange={e=>setTgt(e.target.value)} /></div>
        </div>
        <button className="btn-primary" onClick={runPos} disabled={pos.isPending}>
          {pos.isPending ? <Loader2 className="animate-spin" size={16}/> : 'Calculate Size'}
        </button>
        {pos.isError && <p className="text-red-400 text-xs">{String(pos.error)}</p>}
        {pos.data && (
          <div className="grid grid-cols-3 gap-3">
            <div className="card-sm"><p className="stat-label">Half-Kelly</p><p className="stat-value">{pos.data.half_kelly_weight_pct}%</p></div>
            <div className="card-sm"><p className="stat-label">Vol-target</p><p className="stat-value">{pos.data.vol_target_weight_pct}%</p></div>
            <div className="card-sm"><p className="stat-label">Recommended</p><p className="stat-value text-green-400">{pos.data.recommended_weight_pct}%</p><p className="text-xs text-gray-500">{pos.data.cash_pct}% cash</p></div>
          </div>
        )}
        {pos.data && (
          <Explainer>
            <p><b>What we just did:</b> we worked out how much of your money to put into this one
              position so you grow without risking ruin.</p>
            <p><b>Two methods:</b> "Half-Kelly" ({pos.data.half_kelly_weight_pct}%) is the math-optimal
              bet based on reward vs risk. "Vol-target" ({pos.data.vol_target_weight_pct}%) caps it so your
              portfolio isn't too bumpy. We take the <b>smaller (safer)</b> of the two.</p>
            <p><b>The result:</b> put about <b className="text-green-400">{pos.data.recommended_weight_pct}%</b> of
              your capital here and keep <b>{pos.data.cash_pct}%</b> in cash.
              {pos.data.recommended_weight_pct < 10
                ? ' That’s small because the reward doesn’t justify the risk — betting big here would be dangerous.'
                : ' This captures most of the growth while protecting you from a bad streak.'}</p>
          </Explainer>
        )}
      </div>

      {/* ── Portfolio Tail Risk (VaR / CVaR) ── */}
      <div className="card space-y-4">
        <div>
          <h2 className="font-semibold">Portfolio Tail Risk</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Value at Risk (95%), Conditional VaR (Expected Shortfall), drawdown and
            risk-adjusted ratios from a cost-adjusted historical backtest.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            {Object.entries(pf).map(([t, w]) => (
              <div key={t} className="flex items-center gap-2">
                <input className="input flex-1 text-xs" value={t} onChange={e => renamePf(t, e.target.value)} />
                <input type="number" className="input w-16 text-xs" value={w} onChange={e => setPfW(t, e.target.value)} />
                <span className="text-xs text-gray-500">%</span>
                <button onClick={() => rmPf(t)} className="text-gray-600 hover:text-red-400 text-xs">✕</button>
              </div>
            ))}
            <button onClick={() => setPf({ ...pf, ['NEW.NS']: 0 })} className="text-xs text-blue-400 hover:text-blue-300">+ add stock</button>
            <p className={`text-xs ${pfOk ? 'text-green-400' : 'text-yellow-400'}`}>Total {pfTotal.toFixed(0)}% {pfOk ? '✓' : '(must be 100%)'}</p>
            <button className="btn-primary" disabled={!pfOk || tail.isPending} onClick={() => tail.mutate()}>
              {tail.isPending ? <Loader2 className="animate-spin" size={16}/> : 'Analyse tail risk'}
            </button>
            {tail.isError && <p className="text-xs text-red-400">{String(tail.error)}</p>}
          </div>
          <div>
            {td && (
              <div className="grid grid-cols-2 gap-2">
                <div className="card-sm" title="On a bad day (worst 5%), you lose at least this."><p className="stat-label">VaR 95% (daily)</p><p className="stat-value text-orange-400">{td.var_95_daily_pct}%</p></div>
                <div className="card-sm" title="Average loss on the worst-5% days."><p className="stat-label">CVaR 95%</p><p className="stat-value text-red-400">{td.cvar_95_daily_pct}%</p></div>
                <div className="card-sm"><p className="stat-label">Max drawdown</p><p className="stat-value text-red-400">{td.max_drawdown_pct}%</p></div>
                <div className="card-sm"><p className="stat-label">Volatility</p><p className="stat-value">{td.volatility_pct}%</p></div>
                <div className="card-sm"><p className="stat-label">Sharpe</p><p className="stat-value">{td.sharpe_ratio}</p></div>
                <div className="card-sm"><p className="stat-label">Sortino / Calmar</p><p className="stat-value">{td.sortino_ratio} / {td.calmar_ratio}</p></div>
              </div>
            )}
            {!td && <p className="text-xs text-gray-600">Enter a portfolio and analyse to see tail-risk metrics.</p>}
          </div>
        </div>
      </div>

      {/* ── Fama-French Factor Exposure ── */}
      <div className="card space-y-4">
        <div>
          <h2 className="font-semibold">Factor Exposure (Fama-French)</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Decompose a stock's return into market / size / value factor betas plus
            alpha — is the performance a real edge, or just factor exposure?
          </p>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[140px]"><label className="label">Ticker</label>
            <input className="input" value={facT} onChange={e => setFacT(e.target.value)} onKeyDown={e => e.key === 'Enter' && fac.mutate()} /></div>
          <button className="btn-primary" onClick={() => fac.mutate()} disabled={fac.isPending}>
            {fac.isPending ? <Loader2 className="animate-spin" size={16}/> : 'Run regression'}
          </button>
        </div>
        {fac.isError && <p className="text-xs text-red-400">{String(fac.error)}</p>}
        {fd && fd.coefficients && (
          <>
            <div className="grid grid-cols-4 gap-3">
              {Object.entries(fd.coefficients).map(([k, c]) => (
                <div key={k} className="card-sm" title={`t-stat ${c.t_stat ?? '—'}, p ${c.p_value ?? '—'}`}>
                  <p className="stat-label">{k.replace(/_/g, ' ')}</p>
                  <p className="stat-value">{c.coefficient}</p>
                </div>
              ))}
            </div>
            {fd.interpretation && <p className="text-xs text-gray-400">{fd.interpretation}</p>}
            {fd.r_squared != null && <p className="text-[11px] text-gray-500">R² = {fd.r_squared} — higher means more of the return is explained by factor exposure, less by stock-specific alpha.</p>}
          </>
        )}
      </div>

      <p className="text-[11px] text-gray-600">
        These tools mirror how professional quants avoid fooling themselves (overfitting) and avoid ruin (sizing).
        Estimates only — not financial advice.
      </p>
    </div>
  )
}
