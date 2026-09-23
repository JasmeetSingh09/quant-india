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

      <div className="table-wrap">
        <table className="w-full text-sm min-w-[34rem]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-gray-500">
              <th className="text-left py-1">Factor</th>
              <th className="text-right py-1" title="Weight in the live four-factor model, which produces every score and ranking on the site; the six-factor model's weight in brackets.">Weight</th>
              <th className="text-left py-1 pl-3">Evidence</th>
              <th className="text-left py-1 pl-3">Result</th>
            </tr>
          </thead>
          <tbody>
            {data.factors.map(f => {
              const sig = f.result?.significant_at_5pct
              const st = STATUS[sig === true ? 'passed' : sig === false ? 'failed' : f.status]
                         || STATUS.untested
              return (
                <tr key={f.factor} className="border-t border-gray-800 align-top">
                  <td className="py-2">
                    <span className="capitalize text-gray-200">{f.factor.replace(/_/g, ' ')}</span>
                    <span className="block text-[11px] text-gray-500">{f.plain}</span>
                  </td>
                  <td className="py-2 text-right font-mono text-gray-300">
                    {f.weight_v1_pct == null ? '—' : `${f.weight_v1_pct}%`}
                    {f.weight_pct != null && (
                      <span className="block text-[10px] text-gray-600">({f.weight_pct}%)</span>
                    )}
                  </td>
                  <td className="py-2 pl-3">
                    <span className={`text-[11px] px-1.5 py-0.5 rounded border ${st.cls}`}>
                      {st.label}
                    </span>
                  </td>
                  <td className="py-2 pl-3 text-[11px] text-gray-400 leading-relaxed max-w-md">
                    {f.result?.summary
                      ? <>
                          {f.result.summary}
                          {f.result.caveat &&
                            <span className="block text-amber-200/80 mt-1">{f.result.caveat}</span>}
                        </>
                      : <>
                          {f.why}
                          {f.idea_evidence &&
                            <span className="block text-gray-300/80 mt-1">{f.idea_evidence}</span>}
                        </>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] text-gray-500 leading-relaxed">
        {data.why_this_table_exists}
      </p>

      {/* Not a promise that it will be tested — a computed date for when it
          could be, and why it cannot be sooner. */}
      {data.unblocking?.note && (
        <p className="text-[11px] text-gray-500 border-t border-gray-800 pt-2 leading-relaxed">
          {data.unblocking.note}
        </p>
      )}
    </div>
  )
}
