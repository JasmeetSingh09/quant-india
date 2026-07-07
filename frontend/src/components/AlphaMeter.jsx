export default function AlphaMeter({ score }) {
  if (score == null) return null
  const clamped = Math.max(-100, Math.min(100, score))
  const pct     = ((clamped + 100) / 200) * 100
  const color   = clamped > 40  ? '#22c55e' : clamped > 15  ? '#86efac'
                : clamped < -40 ? '#ef4444' : clamped < -15 ? '#fca5a5'
                : '#6b7280'
  const signal  = clamped > 40  ? 'STRONG BUY' : clamped > 15  ? 'BUY'
                : clamped < -40 ? 'STRONG SELL' : clamped < -15 ? 'SELL'
                : 'NEUTRAL'
  const display = clamped === 0 ? '0' : (clamped > 0 ? `+${clamped}` : `${clamped}`)

  return (
    <div>
      <div className="flex justify-between text-xs text-gray-600 mb-1.5">
        <span>SELL</span>
        <span style={{ color }} className="font-bold text-[11px]">{signal}</span>
        <span>BUY</span>
      </div>
      <div className="h-2.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <div className="flex justify-between mt-1.5">
        <span className="text-xs text-gray-700">−100</span>
        <span className="text-base font-bold font-mono" style={{ color }}>{display}</span>
        <span className="text-xs text-gray-700">+100</span>
      </div>
    </div>
  )
}
