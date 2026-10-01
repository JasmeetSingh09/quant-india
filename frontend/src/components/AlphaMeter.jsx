import { SignalEvidenceNote } from './Evidence'
import { signalLabel, SIGNAL_TITLE } from '../signalLabel'

export default function AlphaMeter({ score, showEvidence = true }) {
  if (score == null) return null
  const clamped = Math.max(-100, Math.min(100, score))
  const pct     = ((clamped + 100) / 200) * 100
  // One cool hue for rank, not buy-green / sell-red (see signalLabel.js).
  const color   = clamped > 40  ? '#7dd3fc' : clamped > 15  ? '#38bdf8'
                : clamped < -40 ? '#64748b' : clamped < -15 ? '#94a3b8'
                : '#6b7280'
  const signal  = clamped > 40  ? 'STRONG BUY' : clamped > 15  ? 'BUY'
                : clamped < -40 ? 'STRONG SELL' : clamped < -15 ? 'SELL'
                : 'NEUTRAL'
  const display = clamped === 0 ? '0' : (clamped > 0 ? `+${clamped}` : `${clamped}`)

  return (
    <div>
      <div className="flex justify-between text-xs text-gray-600 mb-1.5">
        <span>Lower</span>
        <span style={{ color }} className="font-bold text-[11px]" title={SIGNAL_TITLE}>{signalLabel(signal)}</span>
        <span>Higher</span>
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
      {/* The badge above is the model's output. This says what is known about
          whether that output predicts anything — in the same eyeline, because
          a validation status on another page is a validation status nobody
          reads. */}
      {showEvidence && (
        <SignalEvidenceNote className="mt-2 pt-2 border-t border-gray-800" />
      )}
    </div>
  )
}
