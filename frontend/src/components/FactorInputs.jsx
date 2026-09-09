import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFactorInputs } from '../api'

/**
 * FactorInputs — what the model actually read, and what it could not.
 *
 * The scan has been recording every input behind every score since provenance
 * shipped: the value, where it came from, and whether it was missing. Seventy
 * thousand rows of it. None of it reached a screen, so a user could see
 * "quality 0.42" and had no way to learn that three of the eight Piotroski
 * conditions could not be tested at all. A score with an unknown denominator is
 * not explainable, however precise it looks.
 *
 * Missing inputs lead. That is deliberate and it is the whole point of the
 * panel: everything else on the page tells you what the model concluded, and
 * this is the only place that tells you what it was working from. A factor
 * computed from four of nine inputs is not the same claim as one computed from
 * nine, and until now the two rendered identically.
 *
 * The category on each input matters as much as the value. `pit_market` is
 * exchange data, correct as of the date it carries. `observation_yahoo` was
 * fetched on the observation date and carries NO filing date, so it is not
 * point-in-time — a later restatement changes the underlying figure without
 * changing the row. Those are different epistemic objects and the panel says so
 * rather than showing both as "data".
 */

const CATEGORY = {
  pit_market: {
    label: 'exchange',
    cls: 'text-emerald-300 border-emerald-800/60 bg-emerald-950/30',
  },
  observation_yahoo: {
    label: 'not point-in-time',
    cls: 'text-amber-300 border-amber-800/60 bg-amber-950/30',
  },
  derived: {
    label: 'derived',
    cls: 'text-sky-300 border-sky-800/60 bg-sky-950/30',
  },
  assumption: {
    label: 'assumption',
    cls: 'text-violet-300 border-violet-800/60 bg-violet-950/30',
  },
}

const FACTOR_ORDER = ['momentum', 'quality', 'value', 'sentiment']

function fmt(v) {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'number') {
    return Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
  }
  const s = String(v)
  return s.length > 46 ? `${s.slice(0, 46)}…` : s
}

function Pill({ category, categories }) {
  const c = CATEGORY[category] || CATEGORY.derived
  return (
    <span
      title={categories?.[category] || category}
      className={`ml-2 px-1.5 py-0.5 rounded border text-[10px] whitespace-nowrap ${c.cls}`}
    >
      {c.label}
    </span>
  )
}

function FactorBlock({ name, inputs, categories }) {
  const [open, setOpen] = useState(false)
  const entries = Object.entries(inputs || {})
  const missing = entries.filter(([, v]) => v.missing)
  const present = entries.filter(([, v]) => !v.missing)
  if (!entries.length) return null

  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-900/60 hover:bg-gray-900 text-left"
      >
        <span className="text-sm font-medium capitalize">{name}</span>
        <span className="text-xs">
          {missing.length > 0 ? (
            <span className="text-amber-300">
              {missing.length} of {entries.length} missing
            </span>
          ) : (
            <span className="text-gray-500">{entries.length} inputs, none missing</span>
          )}
          <span className="text-gray-600 ml-2">{open ? '−' : '+'}</span>
        </span>
      </button>

      {/* Missing inputs are shown whether or not the block is expanded. They
          are the reason this panel exists; hiding them behind a click would
          reproduce the problem it was built to fix. */}
      {missing.length > 0 && (
        <div className="px-3 py-2 border-t border-gray-800 bg-amber-950/10">
          <p className="text-[11px] uppercase tracking-wider text-amber-400/80 mb-1">
            could not be read
          </p>
          <div className="flex flex-wrap gap-1.5">
            {missing.map(([k, v]) => (
              <span
                key={k}
                title={v.source ? `expected from ${v.source}` : undefined}
                className="px-1.5 py-0.5 rounded border border-amber-800/60 bg-amber-950/30 text-amber-200 text-[11px] font-mono"
              >
                {k}
              </span>
            ))}
          </div>
          <p className="text-[11px] text-gray-500 mt-1.5">
            This factor was computed without {missing.length === 1 ? 'this input' : 'these inputs'}.
          </p>
        </div>
      )}

      {open && present.length > 0 && (
        <div className="border-t border-gray-800 divide-y divide-gray-800/70">
          {present.map(([k, v]) => (
            <div key={k} className="px-3 py-1.5 flex items-baseline justify-between gap-3">
              <span className="text-xs font-mono text-gray-400 shrink-0">{k}</span>
              <span className="flex items-baseline min-w-0">
                <span className="text-xs font-mono text-gray-200 truncate" title={String(v.value)}>
                  {fmt(v.value)}
                </span>
                <Pill category={v.category} categories={categories} />
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function FactorInputs({ ticker }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['factorInputs', ticker],
    queryFn: () => getFactorInputs(ticker),
    enabled: !!ticker,
    staleTime: 10 * 60 * 1000,
    retry: false,
  })

  if (!ticker || isLoading) return null
  // A 404 means the scan has not recorded this stock yet. Saying so is more
  // useful than an empty space, and far more useful than a spinner that never
  // resolves.
  if (isError || !data?.factors) {
    return (
      <div className="card-sm">
        <p className="stat-label">What the model read</p>
        <p className="text-xs text-gray-500 mt-1">
          No stored observation for this stock yet. Inputs are recorded by the
          nightly scan, so a newly listed or newly searched name appears after
          the next pass.
        </p>
      </div>
    )
  }

  const factors = data.factors || {}
  const ordered = [
    ...FACTOR_ORDER.filter(f => factors[f]),
    ...Object.keys(factors).filter(f => !FACTOR_ORDER.includes(f)),
  ]
  const totals = Object.values(factors).reduce(
    (a, inp) => {
      const e = Object.values(inp || {})
      return { n: a.n + e.length, missing: a.missing + e.filter(v => v.missing).length }
    },
    { n: 0, missing: 0 },
  )
  const peers = data.peers || []
  const articles = data.articles || []

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
          What the model read
        </h2>
        <span className="text-xs text-gray-500">
          {totals.missing > 0
            ? <span className="text-amber-300">{totals.missing} of {totals.n} inputs missing</span>
            : `${totals.n} inputs, none missing`}
        </span>
      </div>

      <p className="text-xs text-gray-500">
        Every value each factor actually read on{' '}
        {String(data.observed_at || data.cycle_id || '').slice(0, 10)}, and every
        one it could not. Recorded at scan time, not reconstructed now.
      </p>

      <div className="space-y-2">
        {ordered.map(f => (
          <FactorBlock
            key={f}
            name={f}
            inputs={factors[f]}
            categories={data.categories}
          />
        ))}
      </div>

      {peers.length > 0 && (
        <div>
          <p className="text-[11px] uppercase tracking-wider text-gray-500 mb-1">
            valued against these peers
          </p>
          <div className="flex flex-wrap gap-1.5">
            {peers.map(p => (
              <span
                key={p.ticker}
                className="px-1.5 py-0.5 rounded border border-gray-700 bg-gray-900/60 text-gray-300 text-[11px] font-mono"
                title={`P/E ${p.pe ?? '—'}  ·  P/B ${p.pb ?? '—'}`}
              >
                {String(p.ticker).replace('.NS', '')}
              </span>
            ))}
          </div>
        </div>
      )}

      {articles.length > 0 && (
        <details className="group">
          <summary className="text-[11px] uppercase tracking-wider text-gray-500 cursor-pointer hover:text-gray-400">
            sentiment was built from {articles.length} article
            {articles.length === 1 ? '' : 's'}
          </summary>
          <div className="mt-1.5 space-y-1">
            {articles.slice(0, 12).map((a, i) => (
              <div key={i} className="flex items-baseline gap-2 text-[11px]">
                <span
                  className={
                    a.label === 'positive' ? 'text-green-400'
                      : a.label === 'negative' ? 'text-red-400' : 'text-gray-500'
                  }
                >
                  ●
                </span>
                <span className="text-gray-400 truncate" title={a.title}>{a.title}</span>
                <span className="text-gray-600 ml-auto shrink-0 font-mono">
                  {String(a.published_at || '').slice(0, 10)}
                </span>
              </div>
            ))}
          </div>
        </details>
      )}

      {data.provenance_note && (
        <p className="text-[11px] text-gray-600 border-t border-gray-800 pt-2">
          {data.provenance_note}
        </p>
      )}
    </div>
  )
}
