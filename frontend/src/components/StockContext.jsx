import { useQuery } from '@tanstack/react-query'
import { getAnomaly, getEvents } from '../api'
import { AlertTriangle, Newspaper, Calendar } from 'lucide-react'

/**
 * StockContext — what is happening to this company, deliberately without a score.
 *
 * Both halves answer "what is going on" rather than "should I buy". That
 * restraint is the design: the alpha model already scores this stock, and a
 * second number built from the same headlines would be one opinion counted
 * twice, dressed up as corroboration.
 *
 * Anomalies are measured against the stock's OWN history, because "unusual" is
 * meaningless otherwise — a 4% day is ordinary for a small cap and remarkable
 * for a large one.
 */
export default function StockContext({ ticker }) {
  const { data: anom } = useQuery({
    queryKey: ['anomaly', ticker],
    queryFn: () => getAnomaly(ticker),
    staleTime: 30 * 60 * 1000,
    retry: false,
  })
  const { data: ev } = useQuery({
    queryKey: ['events', ticker],
    queryFn: () => getEvents(ticker),
    staleTime: 30 * 60 * 1000,
    retry: false,
  })

  const hasAnom = anom?.checked && anom?.unusual
  const hasEv = ev?.checked && (ev.earnings || ev.n_headlines > 0)
  if (!hasAnom && !hasEv) return null

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold text-sm">What's happening</h2>

      {hasAnom && (
        <div className="space-y-1.5">
          <p className="text-[11px] uppercase tracking-wide text-amber-400/90 flex items-center gap-1.5">
            <AlertTriangle size={12} /> Unusual behaviour
          </p>
          {anom.findings.map((f, i) => (
            <p key={i} className="text-xs text-gray-300 leading-relaxed pl-3 relative">
              <span className="absolute left-0 text-gray-600">·</span>{f.detail}
            </p>
          ))}
        </div>
      )}

      {ev?.earnings && (
        <div className="flex items-start gap-2">
          <Calendar size={13} className="text-gray-500 shrink-0 mt-0.5" />
          <p className="text-xs text-gray-300 leading-relaxed">
            <b className="text-gray-200">Results {ev.earnings.days_away >= 0 ? 'due' : 'reported'}
            {' '}{ev.earnings.date}</b>
            {ev.notes?.[0] ? ` — ${ev.notes[0].split('—').slice(1).join('—').trim() || ev.notes[0]}` : ''}
          </p>
        </div>
      )}

      {ev?.headlines?.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] uppercase tracking-wide text-gray-500 flex items-center gap-1.5">
            <Newspaper size={12} /> Recent coverage ({ev.n_headlines})
          </p>
          {ev.headlines.slice(0, 4).map((h, i) => (
            <a key={i} href={h.url} target="_blank" rel="noreferrer"
               className="block text-xs text-gray-400 hover:text-gray-200 transition-colors leading-snug">
              {h.title}
              {h.source && <span className="text-gray-600"> · {h.source}</span>}
            </a>
          ))}
        </div>
      )}

      {/* The restraint, stated. Without it a panel of warnings beside a BUY
          badge reads as the model hedging, which is not what this is. */}
      <p className="text-[10px] text-gray-600 leading-relaxed">
        {anom?.this_is_not_a_signal || ev?.this_is_not_a_signal}
      </p>
    </div>
  )
}
