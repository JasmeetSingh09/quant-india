import { useQuery } from '@tanstack/react-query'
import { getFactorEvidence } from '../api'
import { EVIDENCE_CLASS } from '../evidenceStatus'

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
 * evidence stands behind it. Since 2026-09-18: momentum passed pre-registered
 * point-in-time tests (not among the largest stocks), low risk failed, and the
 * rest cannot yet be tested as computed. The combined score is untested.
 *
 * The status comes from /factors/evidence, which computes it. Nothing here is
 * hard-coded prose about a p-value: if the backend later shows momentum IS
 * significant, these badges change on their own.
 */

const STATUS = {
  tested_significant: {
    short: 'Passed',
    long: 'Passed a pre-registered point-in-time test',
    cls: EVIDENCE_CLASS.passed,
  },
  tested_not_significant: {
    short: 'Did not pass',
    long: 'Tested; no statistically significant edge found',
    cls: EVIDENCE_CLASS.failed,
  },
  tested_unknown: {
    short: 'Tested',
    long: 'Has been tested; open the validation page for the result',
    cls: EVIDENCE_CLASS.tested,
  },
  testable_now: {
    short: 'Untested',
    long: 'Reconstructible from prices, not yet tested',
    cls: EVIDENCE_CLASS.untested,
  },
  cannot_test_yet: {
    short: 'Untested',
    long: 'Not yet testable as we compute it (needs accounts or news as first published)',
    cls: EVIDENCE_CLASS.untested,
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
  const pText = p == null ? null : p < 0.001 ? '<0.001' : Number(p).toFixed(3)
  const caveat = row.result?.caveat ? ` ${row.result.caveat}` : ''
  return (
    <span
      title={p != null ? `${s.long} (p = ${pText}).${caveat}` : s.long}
      className={`inline-block px-1.5 py-0.5 rounded border text-[10px]
                  font-medium leading-none whitespace-nowrap ${s.cls}`}
    >
      {long ? s.long : s.short}
      {p != null && <span className="opacity-70"> p{p < 0.001 ? '<0.001' : `=${Number(p).toFixed(2)}`}</span>}
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
  // Only the live model's factors (a V1 weight above zero) are named here:
  // every signal on screen comes from V1.
  const live = (data.factors || []).filter(f => (f.weight_v1_pct ?? 0) > 0)
  const passed = live.filter(f => f.result?.significant_at_5pct === true)
  const untested = live.filter(f => f.status === 'cannot_test_yet')
  const pct = rows => rows.reduce((a, f) => a + (f.weight_v1_pct || 0), 0)
  return (
    <div className={`text-xs leading-relaxed text-gray-400 ${className}`}>
      <span className="text-gray-300 font-medium">Model ranking</span>
      {' — the combined score is '}
      <span className="text-amber-300/90">not yet tested</span>.
      {passed.length > 0 && (
        <> {passed.map(f => f.factor).join(', ')} ({pct(passed).toFixed(0)}% of
          the score) passed point-in-time tests
          {passed.some(f => f.result?.caveat) && ', but not among the largest, most liquid stocks'}.
        </>
      )}
      {untested.length > 0 && (
        <> {untested.map(f => f.factor).join(', ')} ({pct(untested).toFixed(0)}%)
          {' '}are untested as we compute them.</>
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
// A stamp as one unbreakable value (display only; the data is unchanged).
// The scan writes naive ISO times from the server clock, which runs on UTC
// (Render; the nightly scan starts 00:02 UTC), e.g. "2026-11-18T02:01:15.368799"
// -> "2026-11-18 02:01 UTC". A stamp that carries its own zone is converted to
// UTC; anything else is shown as it came.
function fmtStamp(v) {
  if (v == null) return v
  const s = String(v)
  const m = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/)
  if (!m) return s
  if (!m[3]) return `${m[1]} ${m[2]} UTC`
  const d = new Date(s)
  return isNaN(d) ? s : `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)} UTC`
}
const Stamp = ({ v }) => <span className="font-mono whitespace-nowrap text-gray-300">{fmtStamp(v)}</span>

export function ScoreProvenance({ mode, asOf, cycle, className = '' }) {
  const live = mode === 'live'
  return (
    <div className={`text-[11px] text-gray-500 leading-snug ${className}`}>
      <span className="text-gray-400">
        {live ? 'Live' : 'Nightly cycle'}
      </span>
      {live
        ? asOf && <> — computed <Stamp v={asOf} /></>
        : cycle && <> <span className="font-mono whitespace-nowrap">{cycle}</span>{asOf && <> — completed <Stamp v={asOf} /></>}</>}
      <span className="block text-gray-600 mt-0.5">
        {live
          ? 'Other views may show the last completed nightly cycle instead, so scores can differ.'
          : 'Live views recompute during the day, so scores there can differ from this.'}
      </span>
    </div>
  )
}

export default EvidenceBadge
