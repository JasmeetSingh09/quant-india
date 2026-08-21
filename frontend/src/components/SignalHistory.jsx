import { useQuery } from '@tanstack/react-query'
import { getSignalHistory } from '../api'

const sigClass = s =>
  s?.includes('BUY')  ? 'bg-green-900/50 text-green-400 border-green-800/70' :
  s?.includes('SELL') ? 'bg-red-900/50 text-red-400 border-red-800/70'
                      : 'bg-gray-800 text-gray-400 border-gray-700'

function daysAgoLabel(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  const days = Math.round((Date.now() - d.getTime()) / 86400000)
  return days <= 0 ? 'Today' : days === 1 ? 'Yesterday' : `${days} days ago`
}

/**
 * SignalHistory — this one stock's own call over time.
 *
 * Answers "what did the model say yesterday, and 5 days ago?" for the stock
 * being viewed, rather than aggregate model performance. History only exists
 * from the first universe scan onwards — we cannot show a past that was never
 * recorded, and the empty state says so instead of implying no signal.
 */
export default function SignalHistory({ ticker }) {
  const { data, isLoading } = useQuery({
    queryKey: ['signalHistory', ticker],
    queryFn: () => getSignalHistory(ticker, 30),
    enabled: !!ticker,
    staleTime: 10 * 60 * 1000,
  })

  const rows = data?.history ?? []
  if (isLoading || rows.length === 0) return null

  const latest = rows[0]

  return (
    <div className="card">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <h2 className="font-semibold text-sm">This stock's signal history</h2>
        <span className="text-[11px] text-gray-600">
          {rows.length} recorded {rows.length === 1 ? 'reading' : 'readings'}
        </span>
      </div>

      {/* Current call, stated plainly */}
      <div className="flex items-center gap-3 mb-4">
        <span className={`px-2.5 py-1 rounded-lg text-sm font-semibold border ${sigClass(latest.signal)}`}>
          {latest.signal}
        </span>
        <span className={`font-mono text-lg ${latest.alpha_score >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {latest.alpha_score > 0 ? '+' : ''}{latest.alpha_score}
        </span>
        <span className="text-xs text-gray-500">
          <span title={latest.date}>{latest.date}</span> <span className="text-gray-600">({daysAgoLabel(latest.date)})</span> · {Math.round((latest.confidence || 0) * 100)}% data coverage
        </span>
      </div>

      <div className="table-wrap">
        <table className="w-full min-w-[28rem] text-sm">
          <thead>
            <tr className="text-gray-500 text-xs border-b border-gray-800">
              <th className="text-left py-1.5 font-medium">When</th>
              <th className="text-left font-medium">Signal</th>
              <th className="text-right font-medium">Alpha</th>
              <th className="text-right font-medium">Close</th>
              <th className="text-right font-medium">Since</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.date + i} className="border-b border-gray-900 last:border-0">
                <td className="py-1.5 text-gray-400">{daysAgoLabel(r.date)}</td>
                <td>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${sigClass(r.signal)}`}>
                    {r.signal}
                  </span>
                </td>
                <td className={`text-right font-mono ${r.alpha_score >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {r.alpha_score > 0 ? '+' : ''}{r.alpha_score}
                </td>
                {/* What the stock actually closed at that day, and what it has
                    done since — so a past call can be judged, not just read. */}
                <td className="text-right font-mono text-gray-300">
                  {r.close != null ? `₹${r.close.toLocaleString('en-IN')}` : '—'}
                </td>
                {/* Direction-aware. A stock falling after a SELL is the model
                    being RIGHT; colouring it red says the opposite. Same error
                    as scoring a SELL by whether the stock rose, in the palette. */}
                <td className={`text-right font-mono ${
                  r.since_pct == null ? 'text-gray-600'
                  : ((r.signal || '').includes('SELL') ? r.since_pct <= 0 : r.since_pct >= 0)
                    ? 'text-green-400' : 'text-red-400'}`}
                    title={(r.signal || '').includes('SELL')
                      ? 'For a SELL, a fall is the signal being right.'
                      : 'For a BUY, a rise is the signal being right.'}>
                  {r.since_pct == null ? '—'
                    : `${r.since_pct > 0 ? '+' : ''}${r.since_pct.toFixed(1)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] text-gray-600 mt-3">
        Recorded once per daily universe scan. “Close” is what the stock ended at
        that day; “Since” is how it has moved from that close to now — so you can
        judge each past call, not just read it. History starts from the first scan.
      </p>
    </div>
  )
}
