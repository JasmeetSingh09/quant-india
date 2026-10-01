// How the model's signal is worded on screen.
//
// The backend's signal values (STRONG BUY ... STRONG SELL) are unchanged: they
// are recorded in the track record and the frozen specification. What changes
// is the wording people read. "STRONG BUY" reads as a tested recommendation,
// and the combined score behind it has not been tested against future returns
// (docs/FACTOR_TEST1_RESULT_2026-09-13.md, factor_evidence.py). A rank says
// what the model actually does: order stocks by its score.

const LABELS = {
  'STRONG BUY':  'Top ranked',
  'BUY':         'Ranked high',
  'NEUTRAL':     'Middle',
  'HOLD':        'Middle',
  'SELL':        'Ranked low',
  'STRONG SELL': 'Bottom ranked',
}

export function signalLabel(signal) {
  if (!signal) return signal
  return LABELS[String(signal).toUpperCase()] || signal
}

export const SIGNAL_TITLE =
  "Where the model's score ranks this stock today. A ranking, not a " +
  'recommendation or a forecast: the combined score and these labels have ' +
  'not been tested against future returns.'

// How a rank is coloured. Not green for "buy" and red for "sell": those read
// as a tested recommendation, and the combined score has not been tested
// (agreed Tier 1 honesty work, done 2026-10-01). One cool hue, stronger for a
// higher rank, grey for a low one: it shows order, not advice.
const BADGE = 'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border '
const RANK_CLASS = {
  'Top ranked':    'bg-sky-900/50 text-sky-300 border-sky-700/70',
  'Ranked high':   'bg-sky-950/60 text-sky-400/90 border-sky-800/60',
  'Middle':        'bg-gray-800 text-gray-400 border-gray-700',
  'Ranked low':    'bg-slate-800/70 text-slate-400 border-slate-700',
  'Bottom ranked': 'bg-slate-900 text-slate-500 border-slate-700',
}

// Colours only, for places that set their own size.
export function rankColorClass(signal) {
  return RANK_CLASS[signalLabel(signal)] || RANK_CLASS['Middle']
}

export function rankBadgeClass(signal) {
  return BADGE + rankColorClass(signal)
}

// The score's colour follows the same rule: blue above zero, grey below.
export function scoreTextClass(score) {
  if (score == null || score === 0) return 'text-gray-400'
  return score > 0 ? 'text-sky-300' : 'text-slate-400'
}
