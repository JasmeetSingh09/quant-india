import { useState, useEffect } from 'react'

/**
 * useState that survives navigation and reloads by persisting to localStorage.
 * Use for user "progress" (form inputs, selected tabs, results) so switching
 * modules (e.g. Simulator → Top Picks → back) never loses work.
 *
 *   const [holdings, setHoldings] = usePersistentState('sim.rtHoldings', {})
 *
 * Keep the key namespaced (e.g. 'sim.', 'opt.') to avoid collisions.
 */
export default function usePersistentState(key, initial) {
  const [state, setState] = useState(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw != null ? JSON.parse(raw) : initial
    } catch {
      return initial
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(state))
    } catch {
      /* quota / serialization issues are non-fatal — just skip persisting */
    }
  }, [key, state])

  return [state, setState]
}
