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
