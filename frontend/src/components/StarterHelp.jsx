import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { buildPortfolio, trackEvent } from '../api'
import { Wand2, ChevronDown, ChevronRight, Check } from 'lucide-react'

const RISKS = [
  { key: 'conservative', label: 'Careful' },
  { key: 'balanced',     label: 'Balanced' },
  { key: 'aggressive',   label: 'Bold' },
]

/**
 * StarterHelp — a stuck-button, not an autopilot.
 *
 * The point of the simulator is that people learn portfolio construction by
 * DOING it. A guided flow that hands back a finished portfolio teaches nothing;
 * the user never chooses a stock or a weight. So this deliberately does not
 * build and run anything — it only FILLS THE FORM the user is already looking
 * at, then gets out of the way. Every suggested weight stays editable, and
 * nothing starts until they press Start themselves.
 *
 * Collapsed by default, so the manual path is the obvious one and this is the
 * fallback for someone facing an empty box.
 */
export default function StarterHelp({ amount = 100000, onFill }) {
  const [open, setOpen] = useState(false)
  const [risk, setRisk] = useState('balanced')
  const [n, setN] = useState(5)
  const [done, setDone] = useState(0)

  const mut = useMutation({
    mutationFn: () => buildPortfolio({
      amount, horizon_months: 12, max_loss_pct: 30, n_stocks: n, risk,
    }),
    onSuccess: d => {
      onFill?.(Object.fromEntries(d.holdings.map(h => [h.ticker, h.weight_pct])))
      trackEvent('portfolio_built', { n_stocks: d.holdings.length, risk })
      setDone(d.holdings.length)
      setOpen(false)
    },
  })

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/40">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 text-xs text-gray-400">
          {done ? <Check size={13} className="text-green-400" />
                : <Wand2 size={13} className="text-green-400" />}
          {done
            ? `Filled ${done} stocks above — edit any weight, then press Start`
            : 'Not sure where to start? Get some suggestions'}
        </span>
        {open ? <ChevronDown size={14} className="text-gray-500" />
              : <ChevronRight size={14} className="text-gray-600" />}
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-3 border-t border-gray-800 pt-3">
          <p className="text-[11px] text-gray-500 leading-relaxed">
            We'll suggest stocks and starting weights based on the alpha model.
            They go straight into the form above — change anything you disagree
            with before you start. That editing is the part worth learning.
          </p>

          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="label">Style</label>
              <div className="flex gap-1">
                {RISKS.map(o => (
                  <button key={o.key} onClick={() => setRisk(o.key)}
                    className={`px-2.5 py-1 rounded text-xs transition-colors ${
                      risk === o.key ? 'bg-green-600 text-white'
                                     : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="label">How many stocks</label>
              <input type="range" min="3" max="12" step="1" className="w-32"
                     value={n} onChange={e => setN(Number(e.target.value))} />
              <span className="ml-2 text-xs text-gray-400">{n}</span>
            </div>
            <button onClick={() => mut.mutate()} disabled={mut.isPending}
                    className="btn-ghost text-xs">
              {mut.isPending ? 'Finding stocks…' : 'Fill the form'}
            </button>
          </div>

          {/* This call scores candidates and runs a simulation on a throttled
              host — it can take up to a minute. Without saying so the button
              just sits there and reads as broken. */}
          {mut.isPending && (
            <p className="text-[11px] text-gray-500 flex items-center gap-2">
              <span className="w-3 h-3 border-2 border-gray-600 border-t-green-400 rounded-full animate-spin" />
              Scoring stocks and simulating the result — this can take up to a minute.
            </p>
          )}

          {mut.isError && <p className="banner-error text-xs">{String(mut.error)}</p>}
        </div>
      )}
    </div>
  )
}
