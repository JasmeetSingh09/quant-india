/**
 * horizonLabel — months and years that unmistakably describe the same value.
 *
 * Previously "15 months (1.3 years)": correct arithmetic, but 1.25 rounded to
 * one decimal reads as an independent number rather than the same duration, and
 * a reviewer flagged it as an inconsistency. Two decimals removes the ambiguity,
 * and trailing zeros are trimmed so a clean year stays clean.
 */
export function horizonLabel(months) {
  const m = Number(months) || 0
  if (m < 12) return `${m} months`
  const y = (m / 12).toFixed(2).replace(/\.?0+$/, '')
  return `${m} months (${y} ${y === '1' ? 'year' : 'years'})`
}
