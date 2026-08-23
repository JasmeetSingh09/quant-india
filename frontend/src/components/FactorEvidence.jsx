import { useQuery } from '@tanstack/react-query'
import { getFactorEvidence } from '../api'
import Spinner from './Spinner'

/**
 * FactorEvidence — one row per factor, saying what is actually known about it.
 *
 * The app has been careful to say momentum has not demonstrated a significant
 * edge in our tested configurations. Next to that careful sentence sat five
 * factors it said nothing about, and a reader who sees one factor honestly
 * marked unproven reasonably assumes the silent ones were checked and passed.
 * They were not. Saying nothing was the overclaim, and this table is the fix.
 *
 * The number that matters is the weight, not the count: five of six factors
 * being untested sounds survivable until you notice they carry 82% of the
 * score. So weight leads, and the headline states it in words as well.
 */
const STATUS = {
  tested: { label: 'Tested', cls: 'text-yellow-300 border-yellow-800/60 bg-yellow-950/20' },
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
              <th className="text-right py-1">Weight</th>
              <th className="text-left py-1 pl-3">Evidence</th>
              <th className="text-left py-1 pl-3">Result</th>
            </tr>
          </thead>
          <tbody>
            {data.factors.map(f => {
              const st = STATUS[f.status] || STATUS.untested
              return (
                <tr key={f.factor} className="border-t border-gray-800 align-top">
                  <td className="py-2">
                    <span className="capitalize text-gray-200">{f.factor.replace(/_/g, ' ')}</span>
                    <span className="block text-[11px] text-gray-500">{f.plain}</span>
                  </td>
                  <td className="py-2 text-right font-mono text-gray-300">
                    {f.weight_pct == null ? '—' : `${f.weight_pct}%`}
                  </td>
                  <td className="py-2 pl-3">
                    <span className={`text-[11px] px-1.5 py-0.5 rounded border ${st.cls}`}>
                      {st.label}
                    </span>
                  </td>
                  <td className="py-2 pl-3 text-[11px] text-gray-400 leading-relaxed max-w-md">
                    {f.result
                      ? <>
                          {f.result.windows} windows, hit rate {f.result.hit_rate_pct}%,
                          {' '}p = {f.result.p_value}
                          {f.result.significant_at_5pct === false &&
                            <span className="text-yellow-300/90"> — not significant</span>}
                        </>
                      : f.why}
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
