import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { shockPortfolio, shockPresets, multiShock } from '../api'
import Spinner from './Spinner'

/**
 * ShockLab — "what happens to me if X falls 20%?"
 *
 * The Monte Carlo page answers what MIGHT happen, across thousands of futures.
 * This answers a narrower and more useful question: given one specific event,
 * where does the damage land in this portfolio and which holdings cause it.
 *
 * No scenario carries a likelihood, because none is estimated. A number like
 * "12% chance of a crash" would be the most quotable thing on the page and the
 * least defensible, so it does not exist. The question here is "where would
 * this hurt me", not "will this happen".
 */
const rupee = v => v == null ? '—'
  : `${v < 0 ? '-' : ''}₹${Math.abs(Math.round(v)).toLocaleString('en-IN')}`

export default function ShockLab({ holdings, initialValue = 100000 }) {
  const [cash, setCash] = useState(0)
  const [active, setActive] = useState(null)
  const enough = holdings && Object.keys(holdings).length > 0

  const presets = useQuery({
    queryKey: ['shock-presets', JSON.stringify(holdings)],
    queryFn: () => shockPresets({ holdings }),
    enabled: !!enough,
  })
  const run = useMutation({ mutationFn: shockPortfolio })
  // Several things at once, which is what actually happens in a crisis:
  // the market falls, the sector falls harder, and the biggest holding
  // falls hardest. One at a time understates all three.
  const combo = useMutation({ mutationFn: multiShock })
  const [stacked, setStacked] = useState([])

  const fire = p => {
    setActive(p.key)
    run.mutate({ holdings, kind: p.kind, magnitude_pct: p.magnitude_pct,
                 target: p.target ?? null, cash_pct: Number(cash) || 0,
                 initial_value: initialValue })
  }

  if (!enough) return null
  const d = run.data

  return (
    <div className="card space-y-3">
      <div>
        <h2 className="font-semibold text-sm">Test it before your money does</h2>
        <p className="text-xs text-gray-400 mt-0.5 leading-relaxed">
          Pick an event. Every holding moves by its own measured beta to whatever
          is being shocked, so you can see where the damage actually lands rather
          than just a total.
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {presets.isPending && <Spinner size="sm" />}
        {(presets.data?.presets || []).map(p => (
          <button key={p.key} onClick={() => fire(p)}
                  disabled={run.isPending}
                  className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                    active === p.key
                      ? 'border-gray-500 bg-gray-700 text-white'
                      : 'border-gray-700 text-gray-300 hover:bg-gray-800'}`}>
            {p.label}
          </button>
        ))}
      </div>

      {/* Stack scenarios rather than replacing them. */}
      {presets.data?.presets?.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-gray-800 pt-2">
          <span className="text-[11px] uppercase tracking-wide text-gray-500 mr-1">
            Or stack several
          </span>
          {(presets.data.presets || []).slice(0, 8).map(p => {
            const on = stacked.some(x => x.key === p.key)
            return (
              <button key={`s-${p.key}`}
                onClick={() => setStacked(cur => on
                  ? cur.filter(x => x.key !== p.key)
                  : [...cur, p].slice(0, 6))}
                className={`text-[11px] px-2 py-0.5 rounded border transition-colors ${
                  on ? 'border-blue-700 bg-blue-950/40 text-blue-200'
                     : 'border-gray-700 text-gray-400 hover:bg-gray-800'}`}>
                {on ? '✓ ' : '+ '}{p.label}
              </button>
            )
          })}
          {stacked.length >= 2 && (
            <button disabled={combo.isPending}
              onClick={() => { setActive(null); combo.mutate({
                holdings, shocks: stacked.map(p => ({
                  kind: p.kind, magnitude_pct: p.magnitude_pct, target: p.target ?? null })),
                cash_pct: Number(cash) || 0, initial_value: initialValue }) }}
              className="btn-ghost text-[11px] py-0.5">
              {combo.isPending ? 'Running…' : `Run all ${stacked.length} together`}
            </button>
          )}
        </div>
      )}

      {combo.isError && <p className="banner-error text-xs">{String(combo.error)}</p>}
      {combo.data && (
        <div className="p-3 rounded-lg border border-red-800/70 bg-red-950/25 space-y-2">
          <p className="text-[11px] uppercase tracking-wide text-gray-500">
            {combo.data.scenarios_applied.map(s => s.scenario).join(' + ')}
          </p>
          <p className="text-lg font-semibold font-mono">
            <span className="text-gray-400">{rupee(combo.data.initial_value)}</span>
            <span className="text-gray-600 mx-2">→</span>
            <span className="text-red-400">{rupee(combo.data.after_value)}</span>
            <span className="text-sm ml-2 text-gray-500">({combo.data.change_pct}%)</span>
          </p>
          {combo.data.concentration && (
            <p className="text-xs text-gray-400">
              Effective positions{' '}
              <span className="font-mono">
                {combo.data.concentration.effective_positions_before} →
                {' '}{combo.data.concentration.effective_positions_after}
              </span>
              {' · '}largest holding{' '}
              <span className="font-mono">
                {combo.data.concentration.largest_weight_before_pct}% →
                {' '}{combo.data.concentration.largest_weight_after_pct}%
              </span>
            </p>
          )}
          {combo.data.holdings.some(h => h.capped) && (
            <p className="text-[11px] text-yellow-300/90">
              Some holdings hit the -100% floor: stacked shocks implied a fall
              larger than the whole position, which cannot happen.
            </p>
          )}
          <p className="text-[10px] text-gray-500 leading-relaxed">{combo.data.how}</p>
          <p className="text-[11px] text-amber-200/80 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
            {combo.data.limits}
          </p>
        </div>
      )}

      <label className="flex items-center gap-2 text-xs text-gray-400">
        <span>Cash held</span>
        <input type="range" min="0" max="50" step="5" value={cash}
               onChange={e => setCash(e.target.value)} className="flex-1 max-w-[12rem]" />
        <span className="font-mono text-gray-300 w-10">{cash}%</span>
        <span className="text-[11px] text-gray-600">cash does not move</span>
      </label>

      {run.isPending && <Spinner size="sm" />}
      {run.isError && <p className="banner-error text-xs">{String(run.error)}</p>}

      {d && (
        <div className="space-y-3">
          <div className={`p-3 rounded-lg border ${
            d.change_pct < -15 ? 'border-red-800/70 bg-red-950/25'
            : d.change_pct < 0 ? 'border-yellow-800/60 bg-yellow-950/15'
            : 'border-green-800/70 bg-green-950/20'}`}>
            <p className="text-[11px] uppercase tracking-wide text-gray-500">{d.scenario}</p>
            <p className="text-lg font-semibold font-mono mt-0.5">
              <span className="text-gray-400">{rupee(d.initial_value)}</span>
              <span className="text-gray-600 mx-2">→</span>
              <span className={d.change_pct < 0 ? 'text-red-400' : 'text-green-400'}>
                {rupee(d.after_value)}
              </span>
              <span className="text-sm ml-2 text-gray-500">
                ({d.change_pct > 0 ? '+' : ''}{d.change_pct}%)
              </span>
            </p>
            {d.hurt_most?.length > 0 && d.change_pct < 0 && (
              <p className="text-xs text-gray-400 mt-1.5">
                Most of it comes from{' '}
                {d.hurt_most.map((h, i) => (
                  <span key={h.ticker}>
                    {i > 0 && (i === d.hurt_most.length - 1 ? ' and ' : ', ')}
                    <b className="text-gray-300">{h.ticker}</b> ({h.impact_pts} pts)
                  </span>
                ))}.
              </p>
            )}
          </div>

          {Object.keys(d.by_sector || {}).length > 1 && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
                Where it lands, by sector
              </p>
              <div className="space-y-1">
                {Object.entries(d.by_sector).map(([sec, pts]) => (
                  <div key={sec} className="flex items-center gap-2 text-xs">
                    <span className="w-24 shrink-0 text-gray-400 truncate">
                      {sec.replace(/_/g, ' ')}
                    </span>
                    <div className="flex-1 h-2 bg-gray-800 rounded overflow-hidden">
                      <div className={pts < 0 ? 'h-full bg-red-500/70' : 'h-full bg-green-500/70'}
                           style={{ width: `${Math.min(100, Math.abs(pts) * 5)}%` }} />
                    </div>
                    <span className="font-mono text-gray-400 w-14 text-right">{pts} pts</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="table-wrap">
            <table className="w-full text-xs min-w-[26rem]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="text-left py-1">Holding</th>
                  <th className="text-right py-1">Weight</th>
                  <th className="text-right py-1">Beta</th>
                  <th className="text-right py-1">Moves</th>
                  <th className="text-right py-1">Costs you</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {d.holdings.map(h => (
                  <tr key={h.ticker} className="border-t border-gray-800">
                    <td className="py-1 font-sans">
                      {h.ticker.replace('.NS', '')}
                      {h.pinned && <span className="text-[10px] text-gray-600 ml-1">shocked</span>}
                    </td>
                    <td className="py-1 text-right text-gray-500">{h.weight_pct}%</td>
                    <td className="py-1 text-right text-gray-500">
                      {h.beta == null ? '—' : h.pinned ? 'pinned' : h.beta}
                    </td>
                    <td className={`py-1 text-right ${
                      h.move_pct == null ? 'text-gray-600'
                      : h.move_pct < 0 ? 'text-red-400' : 'text-green-400'}`}>
                      {h.move_pct == null ? h.note : `${h.move_pct}%`}
                    </td>
                    <td className="py-1 text-right text-gray-400">
                      {h.impact_inr == null ? '—' : rupee(h.impact_inr)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[10px] text-gray-500 leading-relaxed">{d.how}</p>
          {/* The part that stops this being a false comfort. */}
          <p className="text-[11px] text-amber-200/80 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
            {d.limits}
          </p>
        </div>
      )}
    </div>
  )
}
