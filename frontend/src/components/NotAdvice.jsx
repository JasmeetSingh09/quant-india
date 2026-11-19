// The line shown on Home, the dashboard, stock detail and in every alert and
// summary e-mail (decided 19 Nov 2026; backend/modules/alerts.py NOT_ADVICE
// carries the same words). It sits beside Jasmeet's own disclaimers, it does
// not replace them.
export const NOT_ADVICE = 'Educational research tool, not investment advice; not SEBI-registered.'

export default function NotAdvice({ className = '' }) {
  return <p className={`text-xs text-gray-400 ${className}`}>{NOT_ADVICE}</p>
}
