import { InfoTip } from './Term'

/**
 * StatCard — one figure, and an honest account of it when there isn't one.
 *
 * A dash used to mean two unrelated things. SBIN showed one against EV/EBITDA,
 * Gross Margin, D/E, Current Ratio and Quick Ratio, which reads as "we tried to
 * fetch this and failed". It isn't. A bank has no cost of goods sold, so gross
 * margin has no denominator, and its current liabilities are customer deposits,
 * so a current ratio measures nothing. Those figures are missing from the data
 * because they are missing from the concept.
 *
 * So there are three states, not two:
 *
 *   a value            show it — including 0, which is a fact, not an absence
 *   not applicable     "n/a" plus the reason it does not exist here
 *   genuinely absent   the dash, now meaning only what it says
 *
 * `na` carries the reason from the server, where the accounting judgement is
 * tested, rather than being decided in a template.
 */
export default function StatCard({ label, value, sub, color = '', tip, na, naShort }) {
  // Only null and undefined are absent. 0 is a value: Maruti's debt-to-equity
  // of zero is one of the more interesting things about Maruti, and it used to
  // render as a dash because a truthiness check treated it as nothing.
  const has = value !== null && value !== undefined && value !== ''

  return (
    <div className="card-sm">
      <p className="stat-label">{label}{tip && <InfoTip k={tip} />}</p>
      {has ? (
        <p className={`stat-value ${color}`}>{value}</p>
      ) : na ? (
        <p className="stat-value text-gray-500" title={na}>n/a</p>
      ) : (
        <p className={`stat-value ${color}`}>—</p>
      )}
      {has && sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
      {!has && na && (
        <p className="text-xs text-gray-500 mt-0.5" title={na}>
          {naShort || 'not meaningful here'}
        </p>
      )}
    </div>
  )
}
