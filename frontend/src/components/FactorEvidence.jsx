import { useQuery } from '@tanstack/react-query'
import { getFactorEvidence } from '../api'
import Spinner from './Spinner'

/**
 * FactorEvidence — one row per factor, saying what is actually known about it.
 *
 * A reader who sees one factor marked as tested reasonably assumes the silent
 * ones were checked and passed. They were not. Saying nothing was the
 * overclaim, and this table is the fix: every factor has a row, including the
 * one that failed and the ones that cannot be tested yet.
 *
 * The number that matters is the weight, not the count: four of six factors
 * being untestable sounds survivable until you notice how much of the score
 * they carry. So weight leads, and the headline states it in words as well.
 *
 * Three states, not two. 'Testable now' exists because low_risk turned out to
 * be reconstructible from stored prices after all, and collapsing it into
 * either neighbour would misreport it — 'Tested' claims a result that has not
 * been read, 'Cannot test yet' repeats the error that put it there.
 */
const STATUS = {
  passed: { label: 'Passed', cls: 'text-emerald-300 border-emerald-800/60 bg-emerald-950/25' },
  failed: { label: 'Did not pass', cls: 'text-amber-300 border-amber-800/60 bg-amber-950/25' },
  tested: { label: 'Tested', cls: 'text-yellow-300 border-yellow-800/60 bg-yellow-950/20' },
  testable_now: { label: 'Testable from prices', cls: 'text-sky-300 border-sky-800/60 bg-sky-950/20' },
  cannot_test_yet: { label: 'Cannot test yet', cls: 'text-gray-400 border-gray-700 bg-gray-900/40' },
  untested: { label: 'Untested', cls: 'text-gray-400 border-gray-700 bg-gray-900/40' },
}

export default function FactorEvidence() {
  const { data, isLoading } = useQuery({
    queryKey: ['factorEvidence'],
    queryFn: () => getFactorEvidence(false),
    staleTime: 30 * 60 * 1000,
    retry: false,
  })

  if (isLoading) return <div className="card"><Spinner size="sm" /></div>
  if (!data?.factors) return null

  return (
    <div className="card space-y-3">
      <div>
        <h2 className="font-semibold text-sm">What we actually know about each factor</h2>
        <p className="text-xs text-gray-500 mt-0.5">Evidence status, by weight in the model</p>
      </div>

      {/* The sentence a reader would never have guessed. */}
      <p className="text-sm text-amber-100/90 border-l-2 border-amber-600/70 pl-3 leading-relaxed">
        {data.headline}
      </p>

      {/* One card per factor: name, weight and status at a glance, the long
          result text one click away. Replaced a four-column table whose Result
          column carried a paragraph per row (16 Nov 2026 review: "too
          technical"). A passed factor's caveat stays visible: momentum passed,
          but not among the largest stocks, and folding that away would read as
          a stronger result than the record supports. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {data.factors.map(f => {
          const sig = f.result?.significant_at_5pct
          const st = STATUS[sig === true ? 'passed' : sig === false ? 'failed' : f.status]
                     || STATUS.untested
          const detail = f.result?.summary || f.why
          const extra = f.result?.summary ? null : f.idea_evidence
          return (
            <div key={f.factor} className="rounded-lg border border-gray-800 bg-gray-900/40 p-3 flex flex-col gap-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="capitalize text-gray-200 font-medium">{f.factor.replace(/_/g, ' ')}</p>
                  <p className="text-[11px] text-gray-500">{f.plain}</p>
                </div>
                <div className="text-right shrink-0"
                     title="Weight in the live four-factor model, which produces every score and ranking on the site; the six-factor model's weight in brackets.">
                  <p className="font-mono text-lg text-gray-200 leading-none">
                    {f.weight_v1_pct == null ? '—' : `${f.weight_v1_pct}%`}
                  </p>
                  {f.weight_pct != null && (
                    <p className="text-[10px] text-gray-600 mt-0.5">({f.weight_pct}% in 6-factor)</p>
                  )}
                </div>
              </div>
              <span className={`self-start text-[11px] px-1.5 py-0.5 rounded border ${st.cls}`}>
                {st.label}
              </span>
              {f.result?.caveat && (
                <p className="text-[11px] text-amber-200/80 leading-relaxed">{f.result.caveat}</p>
              )}
              {detail && (
                <details className="group mt-auto">
                  <summary className="cursor-pointer select-none text-[11px] text-green-400 hover:text-green-300 list-none">
                    <span className="group-open:hidden">Details</span>
                    <span className="hidden group-open:inline">Hide details</span>
                  </summary>
                  <p className="mt-1.5 text-[11px] text-gray-400 leading-relaxed">{detail}</p>
                  {extra && <p className="mt-1 text-[11px] text-gray-300/80 leading-relaxed">{extra}</p>}
                </details>
              )}
            </div>
          )
        })}
      </div>

      {(data.why_this_table_exists || data.unblocking?.note) && (
        <details className="group">
          <summary className="cursor-pointer select-none text-[11px] text-gray-500 hover:text-gray-300 list-none">
            <span className="group-open:hidden">Why this table exists, and when the rest can be tested ▸</span>
            <span className="hidden group-open:inline">Hide ▾</span>
          </summary>
          <p className="mt-1.5 text-[11px] text-gray-500 leading-relaxed">{data.why_this_table_exists}</p>
          {/* Not a promise that it will be tested — a computed date for when it
              could be, and why it cannot be sooner. */}
          {data.unblocking?.note && (
            <p className="mt-1.5 text-[11px] text-gray-500 leading-relaxed">{data.unblocking.note}</p>
          )}
        </details>
      )}
    </div>
  )
}
