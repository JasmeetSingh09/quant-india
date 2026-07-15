import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts'
import { runBlackScholes, runImpliedVol, optionsAutofill } from '../api'
import Spinner from '../components/Spinner'
import usePersistentState from '../usePersistentState'

const GREEK_HELP = {
  delta: 'Price change per ₹1 move in the stock. Also ≈ hedge ratio.',
  gamma: 'How fast delta itself changes — curvature of the option value.',
  vega:  'Price change per +1% in volatility.',
  theta: 'Value lost per calendar day (time decay).',
  rho:   'Price change per +1% in the risk-free rate.',
}

function Stat({ label, value, tip, accent }) {
  return (
    <div className="card-sm" title={tip || ''}>
      <p className="text-[11px] text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-lg font-semibold ${accent || 'text-white'}`}>{value}</p>
    </div>
  )
}

export default function OptionsLab() {
  const [ticker, setTicker]   = usePersistentState('bs.ticker', 'RELIANCE')
  const [spot, setSpot]       = usePersistentState('bs.spot', 1400)
  const [strike, setStrike]   = usePersistentState('bs.strike', 1400)
  const [days, setDays]       = usePersistentState('bs.days', 30)
  const [rate, setRate]       = usePersistentState('bs.rate', 6.5)
  const [vol, setVol]         = usePersistentState('bs.vol', 22)
  const [type, setType]       = usePersistentState('bs.type', 'call')
  const [autoMsg, setAutoMsg] = useState(null)

  const price = useMutation({ mutationFn: runBlackScholes })
  const auto  = useMutation({
    mutationFn: () => optionsAutofill(ticker),
    onSuccess: d => {
      setSpot(d.spot); setStrike(d.strike); setVol(d.vol_pct)
      setAutoMsg(`Filled from ${d.ticker}: spot ₹${d.spot}, vol ${d.vol_pct}% (${d.vol_basis})`)
    },
    onError: e => setAutoMsg(`Auto-fill failed: ${String(e)}`),
  })

  const body = () => ({
    spot: Number(spot), strike: Number(strike), days_to_expiry: Number(days),
    rate_pct: Number(rate), vol_pct: Number(vol), option_type: type,
  })
  const run = () => price.mutate(body())

  const d = price.data
  const g = d?.greeks

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Options Lab — Black-Scholes</h1>
        <p className="text-sm text-gray-400 mt-1">
          European option pricing (Black-Scholes-Merton) with Greeks, probability of
          finishing in-the-money, and the payoff at expiry. Prices are theoretical
          fair values, not live option quotes.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Inputs */}
        <div className="card space-y-4">
          <div>
            <label className="text-xs text-gray-400">Auto-fill from NSE stock</label>
            <div className="flex gap-2 mt-1">
              <input className="input flex-1" value={ticker}
                     onChange={e => setTicker(e.target.value.toUpperCase())}
                     placeholder="RELIANCE" />
              <button className="btn-ghost text-sm" onClick={() => { setAutoMsg(null); auto.mutate() }}
                      disabled={auto.isPending}>
                {auto.isPending ? '…' : 'Fill'}
              </button>
            </div>
            {autoMsg && <p className="text-[11px] text-gray-500 mt-1">{autoMsg}</p>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400">Spot (₹)</label>
              <input type="number" className="input w-full" value={spot} onChange={e => setSpot(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-gray-400">Strike (₹)</label>
              <input type="number" className="input w-full" value={strike} onChange={e => setStrike(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-gray-400">Days to expiry</label>
              <input type="number" className="input w-full" value={days} onChange={e => setDays(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-gray-400">Volatility (%)</label>
              <input type="number" className="input w-full" value={vol} onChange={e => setVol(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-gray-400">Risk-free (%)</label>
              <input type="number" className="input w-full" value={rate} onChange={e => setRate(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-gray-400">Type</label>
              <select className="input w-full" value={type} onChange={e => setType(e.target.value)}>
                <option value="call">Call</option>
                <option value="put">Put</option>
              </select>
            </div>
          </div>

          <button className="btn-primary w-full" onClick={run} disabled={price.isPending}>
            {price.isPending ? 'Pricing…' : 'Price option'}
          </button>
          {price.isError && <p className="text-sm text-red-400">{String(price.error)}</p>}
        </div>

        {/* Results */}
        <div className="col-span-2 space-y-4">
          {price.isPending && <div className="card"><Spinner /></div>}

          {d && (
            <>
              <div className="grid grid-cols-4 gap-3">
                <Stat label="Fair value" value={`₹${d.price}`} accent="text-green-400" />
                <Stat label="Moneyness" value={d.moneyness} />
                <Stat label="Intrinsic" value={`₹${d.intrinsic}`} />
                <Stat label="Time value" value={`₹${d.time_value}`} />
              </div>

              <div className="grid grid-cols-5 gap-3">
                <Stat label="Delta" value={g.delta} tip={GREEK_HELP.delta} />
                <Stat label="Gamma" value={g.gamma} tip={GREEK_HELP.gamma} />
                <Stat label="Vega"  value={g.vega}  tip={GREEK_HELP.vega} />
                <Stat label="Theta" value={g.theta} tip={GREEK_HELP.theta} accent="text-red-400" />
                <Stat label="Rho"   value={g.rho}   tip={GREEK_HELP.rho} />
              </div>

              <div className="card">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-white">Payoff at expiry (long {type})</h3>
                  <span className="text-xs text-gray-400">P(finish ITM): {d.prob_itm_pct}%</span>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={d.payoff} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="spot" stroke="#6b7280" fontSize={11}
                           tickFormatter={v => `₹${v}`} />
                    <YAxis stroke="#6b7280" fontSize={11} tickFormatter={v => `₹${v}`} />
                    <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                             formatter={v => [`₹${v}`, 'P/L']} labelFormatter={l => `Spot ₹${l}`} />
                    <ReferenceLine y={0} stroke="#4b5563" />
                    <ReferenceLine x={Number(strike)} stroke="#3b82f6" strokeDasharray="4 4"
                                   label={{ value: 'strike', fill: '#3b82f6', fontSize: 10 }} />
                    <Line type="monotone" dataKey="pnl" stroke="#22c55e" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
                <p className="text-[11px] text-gray-500 mt-2">
                  P/L = intrinsic value at expiry − premium paid (₹{d.price}). Break-even at
                  spot ₹{type === 'call' ? (Number(strike) + d.price).toFixed(2) : (Number(strike) - d.price).toFixed(2)}.
                  d1 = {d.d1}, d2 = {d.d2}.
                </p>
              </div>
            </>
          )}

          {!d && !price.isPending && (
            <div className="card text-sm text-gray-500">
              Enter the inputs (or auto-fill from a stock) and hit <b>Price option</b> to
              see the fair value, Greeks, and payoff diagram.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
