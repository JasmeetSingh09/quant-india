/**
 * Dates — keep every date and date range in a sentence on one line.
 *
 * Browsers may break "2026-07-24" at its hyphens, and a range such as
 * "2026-07-24 to 2026-09-02" at its spaces, which left "2026-09-" on one line
 * and "02" on the next (18 Nov 2026 design review). This wraps each ISO date
 * (and "date to date" / "date–date" range) in one unbreakable mono span. The
 * text itself is never changed.
 */
const ISO = String.raw`\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?`
const PATTERN = new RegExp(`(${ISO}(?:\\s*(?:to|–|—)\\s*${ISO})?)`, 'g')

export function DateText({ text }) {
  if (text == null) return null
  const s = String(text)
  const parts = s.split(PATTERN)
  if (parts.length === 1) return s
  return parts.map((p, i) => (i % 2
    ? <span key={i} className="font-mono whitespace-nowrap">{p}</span>
    : p))
}

/** One date or range from separate values: <DateRange from=… to=… />. */
export function DateRange({ from, to, sep = ' to ' }) {
  return <span className="font-mono whitespace-nowrap">{from}{sep}{to}</span>
}
