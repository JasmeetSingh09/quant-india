export default function RegimeBadge({ regime, proba }) {
  const colors = {
    Bull:     'bg-green-900/50 text-green-400 border-green-700',
    Bear:     'bg-red-900/50 text-red-400 border-red-700',
    Sideways: 'bg-yellow-900/50 text-yellow-400 border-yellow-700',
  }
  const icons = { Bull: '🐂', Bear: '🐻', Sideways: '↔️' }
  if (!regime) return null
  const cls = colors[regime] || colors.Sideways
  const pct = proba?.[regime] ? `${(proba[regime] * 100).toFixed(0)}%` : ''
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${cls}`}>
      {icons[regime]} {regime} {pct && <span className="opacity-70">({pct})</span>}
    </span>
  )
}
