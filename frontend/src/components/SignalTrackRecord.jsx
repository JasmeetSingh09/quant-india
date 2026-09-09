import { useQuery } from '@tanstack/react-query'
import { getMarketValidation } from '../api'

/**
 * SignalTrackRecord — how this label has actually done, beside the label.
 *
 * A signal that appears without its record invites the reader to supply one,
 * and the one they supply is always better than the truth. So the record
 * travels with the label.
 *
 * The hard part is that the honest answer today is "we do not know", and
 * saying that well is harder than showing a number. Every bucket currently has
 * between zero and nine independent observations:
 *
 *     Strong Sell 0 · Sell 2 · Neutral 0 · Buy 9 · Strong Buy 3
 *
 * Five hundred raw observations become thirty once windows sharing days for the
 * same stock are removed, fourteen once graded, and about six once same-day
 * clustering across stocks is accounted for. A hit rate computed on three
 * observations is two-out-of-three, and rendering "66.7%" would be worse than
 * rendering nothing: it looks like evidence and is not.
 *
 * So the count leads and the percentage is suppressed entirely below the
 * sufficiency threshold the backend sets. The rule is deliberately one-way —
 * this component can refuse to show a rate the backend supplied, and can never
 * show one it did not.
 */

const LABEL_MAP = {
  'STRONG BUY': 'Strong Buy',
  BUY: 'Buy',
  NEUTRAL: 'Neutral',
  SELL: 'Sell',
  'STRONG SELL': 'Strong Sell',
}

export default function SignalTrackRecord({ signal, compact = false }) {
  const { data } = useQuery({
    queryKey: ['marketValidation'],
    queryFn: () => getMarketValidation(21),
    staleTime: 6 * 60 * 60 * 1000,
    retry: false,
  })

  if (!signal || !data?.available) return null
  const want = LABEL_MAP[String(signal).toUpperCase()] || signal
  const row = (data.by_signal_bucket || []).find(b => b.group === want)
  if (!row) return null

  const n = row.n_independent || 0
  // `insufficient` is the backend's own judgement. Trusting it rather than
  // re-deriving a threshold here keeps one definition of "enough" in the app.
  const enough = !row.insufficient && row.hit_rate_pct != null
  const ci = row.hit_ci_95

  if (compact) {
    return (
      <span className="text-[11px] text-gray-500" title={
        enough
          ? `${row.hit_rate_pct}% over ${n} independent observations`
          : `${n} independent observation${n === 1 ? '' : 's'} — too few to judge`
      }>
        {enough
          ? <>track record <span className="text-gray-300">{row.hit_rate_pct}%</span> (n={n})</>
          : <>no track record yet (n={n})</>}
      </span>
    )
  }

  return (
    <div className="card-sm">
      <p className="stat-label">Track record — {want}</p>

      {enough ? (
        <>
          <p className="stat-value">{row.hit_rate_pct}%</p>
          <p className="text-xs text-gray-500 mt-0.5">
            over {n} independent observations
            {ci && <> · 95% CI {ci[0]}–{ci[1]}%</>}
          </p>
          {row.significant_at_5pct === false && (
            <p className="text-[11px] text-amber-400/80 mt-1">
              Not statistically distinguishable from chance.
            </p>
          )}
        </>
      ) : (
        <>
          {/* No percentage at all. Three observations rendered as "66.7%" reads
              as evidence, and it is two out of three. */}
          <p className="stat-value text-gray-500">not yet</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {n === 0
              ? 'No independent observations of this label have matured yet.'
              : `Only ${n} independent observation${n === 1 ? '' : 's'} so far — too few to judge.`}
          </p>
        </>
      )}

      {data.sample && (
        <p className="text-[11px] text-gray-600 mt-2 border-t border-gray-800 pt-1.5">
          {data.sample.raw_observations} raw observations reduce to{' '}
          {data.sample.independent_windows} independent windows and about{' '}
          {data.sample.effective_sample_size} effective, once repeated windows
          on the same stock and shared market days are removed.
        </p>
      )}
    </div>
  )
}
