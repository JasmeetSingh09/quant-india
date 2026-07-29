import { useState, useEffect } from 'react'

/**
 * Subscribe to a CSS media query from JS.
 *
 *   const isMobile = useMediaQuery('(max-width: 1023px)')
 *
 * We need this (rather than pure CSS) because the sidebar behaves *structurally*
 * differently on phones — it's an overlay drawer that traps focus and closes on
 * navigation, versus a docked rail on desktop. Those are different components,
 * not different styles.
 *
 * SSR-safe: returns false when `window` is unavailable.
 */
export default function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mql = window.matchMedia(query)
    const sync = () => setMatches(mql.matches)
    sync()                            // resync in case the query prop changed
    mql.addEventListener('change', sync)
    // Belt-and-braces: some environments (devtools viewport overrides, a few
    // embedded webviews) resize without emitting a matchMedia change event.
    window.addEventListener('resize', sync)
    return () => {
      mql.removeEventListener('change', sync)
      window.removeEventListener('resize', sync)
    }
  }, [query])

  return matches
}
