import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
import { AuthProvider } from './AuthContext.jsx'
import './index.css'

// Slider fill (index.css): CSS cannot read a range input's value, so keep a
// --fill percentage in step with every slider on the page — on input, and
// whenever React mounts one or changes its value (18 Nov 2026).
function syncRange(el) {
  const min = el.min === '' ? 0 : Number(el.min)
  const max = el.max === '' ? 100 : Number(el.max)
  const pct = max > min ? ((Number(el.value) - min) / (max - min)) * 100 : 0
  el.style.setProperty('--fill', `${Math.min(100, Math.max(0, pct))}%`)
}
const syncAll = () => document.querySelectorAll('input[type="range"]').forEach(syncRange)
let rangeFrame = 0
document.addEventListener('input', e => { if (e.target?.type === 'range') syncRange(e.target) }, true)
new MutationObserver(() => {
  cancelAnimationFrame(rangeFrame)
  rangeFrame = requestAnimationFrame(syncAll)
}).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['value'] })

const queryClient = new QueryClient({
  defaultOptions: {
    // Switching back to the browser tab used to refetch every query on the
    // page at once, which is what made returning to the app stutter. Data
    // with its own refresh interval still polls on that schedule.
    queries: { retry: 1, staleTime: 60_000, refetchOnWindowFocus: false }
  }
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
