export default function RegimeBadge({ regime, proba }) {
  const styles = {
    Bull:     { cls: 'bg-green-900/50 text-green-400 border-green-700/70',   icon: '🐂' },
    Bear:     { cls: 'bg-red-900/50 text-red-400 border-red-700/70',         icon: '🐻' },
    Sideways: { cls: 'bg-yellow-900/50 text-yellow-400 border-yellow-700/70', icon: '⟷' },
  }
  if (!regime) return null
  const { cls, icon } = styles[regime] ?? { cls: 'bg-gray-800 text-gray-300 border-gray-600', icon: '◌' }
  // probability key may be capitalised differently — try both
  const rawProba = proba?.[regime] ?? proba?.[regime?.toLowerCase()]
  const pct = rawProba != null ? `${(rawProba * 100).toFixed(0)}%` : null
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${cls}`}>
      <span>{icon}</span>
      <span>{regime}</span>
      {pct && <span className="opacity-60">({pct})</span>}
    </span>
  )
}
