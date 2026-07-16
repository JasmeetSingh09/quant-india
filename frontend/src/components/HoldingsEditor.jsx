/**
 * Shared portfolio holdings editor.
 *
 * IMPORTANT: rows carry a STABLE `id`. An earlier version keyed each row by the
 * ticker itself while the ticker was also the input's value — so every keystroke
 * changed the key, React remounted the input, and the cursor/focus was lost after
 * each letter. Never key an editable row by the value being edited.
 */

let _seq = 0
export const newRow = (ticker = '', weight = 0) => ({
  id: `r${Date.now().toString(36)}_${_seq++}`,
  ticker,
  weight,
})

/** Build the {TICKER.NS: weight} object the API expects. */
export function rowsToHoldings(rows) {
  const out = {}
  for (const r of rows || []) {
    const t = (r.ticker || '').trim().toUpperCase()
    if (!t) continue
    out[t.endsWith('.NS') ? t : `${t}.NS`] = Number(r.weight) || 0
  }
  return out
}

export const rowsTotal = rows =>
  (rows || []).reduce((a, r) => a + (Number(r.weight) || 0), 0)

export const rowsValid = rows => Math.abs(rowsTotal(rows) - 100) < 0.01

export default function HoldingsEditor({ rows, setRows }) {
  const total = rowsTotal(rows)
  const ok = rowsValid(rows)
  const patch = (id, p) => setRows(rows.map(r => (r.id === id ? { ...r, ...p } : r)))

  return (
    <div className="space-y-2">
      {rows.map(r => (
        // key is the stable row id — NOT the ticker being typed
        <div key={r.id} className="flex items-center gap-2">
          <input
            className="input flex-1 text-xs"
            value={r.ticker}
            placeholder="RELIANCE"
            onChange={e => patch(r.id, { ticker: e.target.value })}
          />
          <input
            type="number"
            className="input w-16 text-xs"
            value={r.weight}
            onChange={e => patch(r.id, { weight: e.target.value })}
          />
          <span className="text-xs text-gray-500">%</span>
          <button
            onClick={() => setRows(rows.filter(x => x.id !== r.id))}
            className="text-gray-600 hover:text-red-400 text-xs"
            title="Remove"
          >✕</button>
        </div>
      ))}
      <button onClick={() => setRows([...rows, newRow()])}
              className="text-xs text-blue-400 hover:text-blue-300">+ add stock</button>
      <p className={`text-xs ${ok ? 'text-green-400' : 'text-yellow-400'}`}>
        Total {total.toFixed(0)}% {ok ? '✓' : '(must be 100%)'}
      </p>
    </div>
  )
}
