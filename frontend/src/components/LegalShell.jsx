import { Link } from 'react-router-dom'
import { CONTACT_EMAIL, LEGAL_LAST_UPDATED } from '../siteConfig'

/**
 * Interim privacy notice and terms (V4-01 option (b), decided 19 Nov 2026).
 *
 * Built from what the code does today and from Jasmeet's own drafts in
 * docs/legal/ (29 Oct 2026), without their bracketed blanks and lawyer
 * questions. Sources for each statement:
 *   accounts            — Supabase auth (AuthContext.jsx), 18+ flag (ageGate.js)
 *   watchlist, holdings,
 *   simulations, theses,
 *   share links         — backend modules keyed by user_id (account_deletion.USER_TABLES)
 *   e-mail addresses    — user_prefs.py (weekly summary, alert opt-ins)
 *   product events      — analytics.py, gated by auth.events_allowed
 *   rate limiting       — api.js X-Client-Id, rate_limit.py (in memory)
 *   browser storage     — supabaseClient.js session, api.js client id, usePersistentState.js
 *   providers           — Supabase, Render (+ Cloudflare in front), Vercel, Gmail
 *                         (alerts.py), Google Fonts (index.html), market data by ticker
 *   deletion            — account_deletion.py; advice_log keeps only a hash
 * Pages: pages/Privacy.jsx, pages/Terms.jsx.
 * Interim, not legal advice: Jasmeet and his parent confirm it before it is
 * relied on. The contact line appears only once CONTACT_EMAIL is set.
 */

export function Shell({ title, standalone, children }) {
  const body = (
    <article className="w-full max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8 text-gray-300">
      <header className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-bold text-white">{title}</h1>
        <p className="text-sm text-gray-400">Last updated {LEGAL_LAST_UPDATED}</p>
        {CONTACT_EMAIL && (
          <p className="text-sm text-gray-300">
            Questions or requests:{' '}
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-white underline underline-offset-4">{CONTACT_EMAIL}</a>
          </p>
        )}
      </header>
      {children}
      <footer className="flex flex-wrap gap-4 border-t border-gray-800 pt-5 text-sm">
        <Link to="/" className="text-gray-300 hover:text-white">← Back to Quant India</Link>
        <Link to="/privacy" className="text-gray-300 hover:text-white">Privacy notice</Link>
        <Link to="/terms" className="text-gray-300 hover:text-white">Terms</Link>
      </footer>
    </article>
  )
  return standalone ? <div className="min-h-screen bg-gray-950">{body}</div> : body
}

export function Section({ title, children }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-white">{title}</h2>
      <div className="space-y-3 text-[15px] leading-relaxed">{children}</div>
    </section>
  )
}

export function List({ children }) {
  return <ul className="list-disc pl-5 space-y-2 marker:text-gray-600">{children}</ul>
}

