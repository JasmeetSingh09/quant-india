export default function AlphaMeter({ score }) {
  if (score == null) return null
  const clamped  = Math.max(-100, Math.min(100, score))
  const pct      = ((clamped + 100) / 200) * 100
  const color    = score > 40 ? '#22c55e' : score > 15 ? '#86efac'
                 : score < -40 ? '#ef4444' : score < -15 ? '#fca5a5'
                 : '#6b7280'
  const signal   = score > 40 ? 'STRONG BUY' : score > 15 ? 'BUY'
                 : score < -40 ? 'STRONG SELL' : score < -15 ? 'SELL'
                 : 'NEUTRAL'

  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>SELL</span>
        <span style={{ color }} className="font-bold">{signal}</span>
        <span>BUY</span>
      </div>
      <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-xs text-gray-600">-100</span>
        <span className="text-sm font-bold font-mono" style={{ color }}>
          {score > 0 ? '+' : ''}{score}
        </span>
        <span className="text-xs text-gray-600">+100</span>
      </div>
    </div>
  )
}
