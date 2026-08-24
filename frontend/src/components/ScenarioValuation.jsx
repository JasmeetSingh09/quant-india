import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getScenarios } from '../api'
import Spinner from './Spinner'

/**
 * ScenarioValuation — bull, base and bear, with the assumptions in the open.
 *
 * The numbers here are arithmetic on assumptions the user can see and change,
 * not a forecast. That is the whole design: given a growth rate and an exit
 * multiple there is exactly one implied value, and the reason to show three is
 * that the honest answer to "what is this worth" is a range whose width comes
 * from assumptions rather than from the model knowing something.
 *
 * The refusal path matters as much as the working one. A loss-making company
 * has no meaningful P/E, and three confident-looking scenarios built on a
 * substituted zero would be worse than showing nothing.
 */
const rupee = v => v == null ? '—' : `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

const TONE = {
  Bear: 'text-red-400',
  Base: 'text-gray-200',
  Bull: 'text-green-400',
}

export default function ScenarioValuation({ ticker }) {
  const [years, setYears] = useState(3)
  const [growth, setGrowth] = useState('')
  const [multiple, setMultiple] = useState('')

  const params = { years }
  if (growth !== '') params.base_growth_pct = Number(growth)
  if (multiple !== '') params.base_multiple = Number(multiple)

  const { data, isLoading } = useQuery({
    queryKey: ['scenarios', ticker, years, growth, multiple],
    queryFn: () => getScenarios(ticker, params),
    enabled: !!ticker,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  if (!ticker) return null
  if (isLoading) return <div className="card"><Spinner size="sm" /></div>
  if (!data) return null

  // The refusal, stated as specifically as the working case.
  if (!data.available) {
    return (
      <div className="card space-y-2">
        <h2 className="font-semibold text-sm">Bull / base / bear</h2>
        <p className="text-xs text-gray-400 leading-relaxed">{data.reason}</p>
        {data.why_it_matters && (
          <p className="text-[11px] text-gray-500 leading-relaxed">{data.why_it_matters}</p>
        )}
      </div>
    )
  }

  const a = data.assumptions_used

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">Bull / base / bear</h2>
        <span className="text-[11px] text-gray-500">
          ₹{data.current_price} today · P/E {data.current_pe} · EPS {data.eps_now}
        </span>
      </div>

      {/* Change any of these and every number below moves with it. */}
      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="label text-[11px]">Years</label>
          <input type="number" min="1" max="10" className="input text-xs"
                 value={years} onChange={e => setYears(Number(e.target.value) || 1)} />
        </div>
        <div>
          <label className="label text-[11px]">Base growth %</label>
          <input type="number" className="input text-xs" placeholder={a.base_growth_pct}
                 value={growth} onChange={e => setGrowth(e.target.value)} />
        </div>
        <div>
          <label className="label text-[11px]">Base exit P/E</label>
          <input type="number" className="input text-xs" placeholder={a.base_multiple}
                 value={multiple} onChange={e => setMultiple(e.target.value)} />
        </div>
      </div>

      <div className="table-wrap">
        <table className="w-full text-sm min-w-[30rem]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-gray-500">
              <th className="text-left py-1">Case</th>
              <th className="text-right py-1">Growth</th>
              <th className="text-right py-1">Exit P/E</th>
              <th className="text-right py-1">EPS in {data.years}y</th>
              <th className="text-right py-1">Implied value</th>
              <th className="text-right py-1">Change</th>
              <th className="text-right py-1">Per year</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            <tr className="border-t border-gray-800">
              <td className="py-1.5 font-sans text-gray-500">Today</td>
              <td colSpan={3}></td>
              <td className="py-1.5 text-right text-gray-400">{rupee(data.current_price)}</td>
              <td colSpan={2}></td>
            </tr>
            {data.scenarios.map(s => (
              <tr key={s.scenario} className="border-t border-gray-800">
                <td className={`py-1.5 font-sans font-medium ${TONE[s.scenario]}`}>{s.scenario}</td>
                <td className="py-1.5 text-right text-gray-400">{s.growth_pct}%</td>
                <td className="py-1.5 text-right text-gray-400">{s.exit_multiple}</td>
                <td className="py-1.5 text-right text-gray-400">{s.eps_end}</td>
                <td className={`py-1.5 text-right ${TONE[s.scenario]}`}>{rupee(s.implied_value)}</td>
                <td className={`py-1.5 text-right ${s.change_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {s.change_pct > 0 ? '+' : ''}{s.change_pct}%
                </td>
                <td className="py-1.5 text-right text-gray-500">
                  {s.annualised_pct > 0 ? '+' : ''}{s.annualised_pct}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.order_note && (
        <p className="text-[11px] text-yellow-300/90 leading-relaxed">{data.order_note}</p>
      )}

      <p className="text-[11px] text-gray-500 leading-relaxed">
        {data.method} Growth defaults to {a.growth_source}
        {a.growth_was_clamped && ', capped because the reported figure was extreme'}.
      </p>

      <p className="text-[11px] text-amber-200/80 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
        {data.not_a_forecast}
      </p>
    </div>
  )
}
