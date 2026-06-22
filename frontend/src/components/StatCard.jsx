import { InfoTip } from './Term'

export default function StatCard({ label, value, sub, color = '', tip }) {
  return (
    <div className="card-sm">
      <p className="stat-label">{label}{tip && <InfoTip k={tip} />}</p>
      <p className={`stat-value ${color}`}>{value ?? '—'}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  )
}
