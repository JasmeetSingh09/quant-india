import { useState } from 'react'
import usePersistentState from '../usePersistentState'
import { useMutation } from '@tanstack/react-query'
import { getDeflatedSharpe, getPositionSize } from '../api'
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

      <p className="text-[11px] text-gray-600">
        These tools mirror how professional quants avoid fooling themselves (overfitting) and avoid ruin (sizing).
        Estimates only — not financial advice.
      </p>
    </div>
  )
}
