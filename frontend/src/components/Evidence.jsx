import { useQuery } from '@tanstack/react-query'
import { getFactorEvidence } from '../api'

/**
 * Evidence — what is known about whether a score predicts anything.
 *
 * The app computes a signal and shows it prominently. That is fine; a model may
 * produce an output without that output being validated. What is not fine is
 * showing the two as though they were one thing, which is what a green STRONG
 * BUY beside "91.5%" does.
 *
 * So these pieces travel with the score wherever it is displayed. They do not
 * soften the signal or hide it — they state, in the same eyeline, how much
 * evidence stands behind it. Today that is: momentum is the only factor that
 * has been tested at all; the rest cannot be tested on the data that exists.
 *
 * The status comes from /factors/evidence, which computes it. Nothing here is
 * hard-coded prose about a p-value: if the backend later shows momentum IS
 * significant, these badges change on their own.
 */

const STATUS = {
  tested_significant: {
    short: 'Tested',
    long: 'Tested and statistically significant',
    cls: 'text-emerald-300 border-emerald-800/60 bg-emerald-950/25',
  },
  tested_not_significant: {
    short: 'Not significant',
    long: 'Tested — no statistically significant edge found',
    cls: 'text-amber-300 border-amber-800/60 bg-amber-950/25',
  },
  tested_unknown: {
    short: 'Tested',
    long: 'Has been tested; open the validation page for the result',
    cls: 'text-amber-300 border-amber-800/60 bg-amber-950/25',
  },
  testable_now: {
    short: 'Untested',
    long: 'Reconstructible from prices, not yet tested',
    cls: 'text-sky-300 border-sky-800/60 bg-sky-950/25',
  },
  cannot_test_yet: {
    short: 'Not testable',
    long: 'Cannot be tested on the data that exists',
    cls: 'text-gray-400 border-gray-700 bg-gray-900/50',
  },
}

/**
 * Collapse the backend's status plus its result into one display key.
 *
 * The significance verdict is only claimed when the backend actually carries
 * one. /factors/evidence returns an empty `result` unless full=true, and
 * reading "not significant" out of an absent field would be inventing an
 * evidence claim — the exact failure this component exists to prevent.
 */
function statusKey(row) {
  if (!row) return 'cannot_test_yet'
  if (row.status === 'tested') {
    const sig = row.result?.significant_at_5pct
    if (sig === true) return 'tested_significant'
    if (sig === false) return 'tested_not_significant'
    return 'tested_unknown'
  }
  return row.status === 'testable_now' ? 'testable_now' : 'cannot_test_yet'
}

/** Shared fetch. One request serves every badge on the page. */
export function useEvidence() {
  return useQuery({
    queryKey: ['factorEvidence'],
    queryFn: () => getFactorEvidence(false),
    staleTime: 60 * 60 * 1000,
    retry: false,
  })
}

/**
 * A badge for one factor. Renders nothing until the data arrives rather than
 * guessing — an evidence claim invented client-side would defeat the point.
 */
export function EvidenceBadge({ factor, long = false }) {
  const { data } = useEvidence()
  const row = (data?.factors || []).find(f => f.factor === factor)
  if (!row) return null
  const s = STATUS[statusKey(row)]
  const p = row.result?.p_value
  return (
    <span
      title={p != null ? `${s.long} (p = ${Number(p).toFixed(3)})` : s.long}
      className={`inline-block px-1.5 py-0.5 rounded border text-[10px]
                  font-medium leading-none whitespace-nowrap ${s.cls}`}
    >
      {long ? s.long : s.short}
      {p != null && <span className="opacity-70"> p={Number(p).toFixed(2)}</span>}
    </span>
  )
}

/**
 * The line that sits under a signal. States what the signal is and what is
 * known about it, in that order, without editorialising either.
 */
export function SignalEvidenceNote({ className = '' }) {
  const { data } = useEvidence()
  if (!data) return null
  const rows = data.factors || []
  const tested = rows.filter(f => f.status === 'tested').map(f => f.factor)
  const blocked = rows.filter(f => f.status === 'cannot_test_yet').length
  return (
    <div className={`text-[11px] leading-snug text-gray-400 ${className}`}>
      <span className="text-gray-300 font-medium">Model signal</span>
      {' — historical validation: '}
      <span className="text-amber-300/90">insufficient evidence</span>.
      {tested.length > 0 && (
        <> Only {tested.join(', ')} has been tested against future returns
          {blocked > 0 && <>; {blocked} other factors cannot be tested on the
            data that exists</>}.
        </>
      )}
      {' '}A score is the model&apos;s output, not a validated prediction.
    </div>
  )
}

/**
 * Where a number came from and when. Two views can show different scores for
 * the same stock and both be correct — Top Picks is computed live, the
 * universe list serves the last completed nightly cycle. Without this the
 * difference reads as unreliability.
 */
export function ScoreProvenance({ mode, asOf, cycle, className = '' }) {
  const live = mode === 'live'
  return (
    <div className={`text-[11px] text-gray-500 leading-snug ${className}`}>
      <span className="text-gray-400">
        {live ? 'Live' : 'Nightly cycle'}
      </span>
      {live
        ? asOf && <> — computed {asOf}</>
        : cycle && <> {cycle}{asOf && <> — completed {asOf}</>}</>}
      <span className="block text-gray-600 mt-0.5">
        {live
          ? 'Other views may show the last completed nightly cycle instead, so scores can differ.'
          : 'Live views recompute during the day, so scores there can differ from this.'}
      </span>
    </div>
  )
}

export default EvidenceBadge
