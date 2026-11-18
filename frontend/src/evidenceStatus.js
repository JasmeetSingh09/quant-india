// How an evidence status is coloured, everywhere it appears: the Home
// evidence list, the Advanced evidence board and the badges beside a score.
//
// One map, because the same word in two colours reads as two meanings. Until
// 18 Nov 2026 the Advanced board drew "Did not pass" in amber and "Cannot test
// yet" in grey, while the Home design drew the opposite; a reader moving
// between the pages could not tell which was the warning. The statuses
// themselves come from /factors/evidence (backend factor_evidence.py) and are
// never decided here: this file only picks the colour.
//
//   passed   sky   — the one colour for a positive result (not buy-green)
//   failed   grey  — tested, nothing found; a closed question, not an alarm
//   tested   grey  — tested, result on the validation page
//   untested amber — not yet tested (cannot test yet, testable from prices):
//                    amber is kept for untested and experimental only
export const EVIDENCE_CLASS = {
  passed:   'text-sky-300 border-sky-800/70 bg-sky-950/40',
  failed:   'text-gray-300 border-gray-700 bg-gray-800/60',
  tested:   'text-gray-300 border-gray-700 bg-gray-800/60',
  untested: 'text-amber-300 border-amber-800/60 bg-amber-950/25',
}

// One factor row from /factors/evidence -> its colour key.
export function evidenceKey(row) {
  if (!row) return 'untested'
  const sig = row.result?.significant_at_5pct
  if (sig === true) return 'passed'
  if (sig === false) return 'failed'
  return row.status === 'tested' ? 'tested' : 'untested'
}
