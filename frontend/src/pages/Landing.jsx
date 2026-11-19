import { useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getScanStatus, getFactorEvidence } from '../api'
import { EVIDENCE_CLASS, evidenceKey } from '../evidenceStatus'
import { Zap } from 'lucide-react'
import NotAdvice from '../components/NotAdvice'

// Written as steps a user takes, not tools we own. The old list named the
// machinery ("4-Factor Alpha Model", "FinBERT Sentiment"), which sold a
// stock-picking edge the track record does not support. Same technology
// underneath — described by what it lets someone learn.
// The icon tiles (a magic wand among them) went on 18 Nov 2026: the numbers in
// the titles already order the steps, and the tiles were the most generic
// thing on the page.
const STEPS = [
  { title: '1. Build a portfolio in five answers',
    desc: 'Tell us how much, for how long, and the worst loss you could live with. You get real NSE stocks with sensible position sizes — a starting point to learn from, not a tip sheet.' },
  { title: '2. See what could actually happen',
    desc: 'Thousands of simulated futures from years of real NSE history. Typical outcome, best case, and the one that matters: how bad the worst 5% looks.' },
  { title: '3. Find out what is wrong with it',
    desc: 'Every warning cites the number behind it — "this stock is 55% of your money", "these two move together 0.85, so they are one bet, not two".' },
  { title: '4. Change it and watch the effect',
    desc: 'Cut concentration, add or drop a stock, hold for longer. Each change shows what it does to BOTH your expected return and your worst case — because most improvements are trades, not free wins.' },
  { title: '5. Paper-trade it, risk-free',
    desc: 'Track your portfolio against real prices with no real money. Come back in a week and find out what actually happened.' },
]
const SCORECARD = {
  title: 'And we show our own scorecard',
  desc: "Our model's past calls are published with their real returns — including where the evidence is weak or missing. That is so you can judge the other numbers yourself.",
}

const UNDER_THE_HOOD = [
  ['Alpha model', 'Momentum (12-1, volatility-adjusted), quality (Piotroski F-score, ROE, FCF yield), value (P/E and P/B z-scores vs peers) and FinBERT news sentiment — combined into one score with every contribution shown.'],
  ['Portfolio optimisation', 'Markowitz mean-variance with Ledoit-Wolf shrinkage, Black-Litterman with He-Litterman equilibrium, Hierarchical Risk Parity, Equal Risk Contribution, Maximum Diversification and Min-CVaR via linear programming.'],
  ['Risk & simulation', 'Monte Carlo by normal, Student-t, i.i.d. and block bootstrap. VaR and CVaR, GARCH(1,1) volatility forecasting, risk decomposition by contribution, and Kelly-based position sizing.'],
  ['Factor research', 'Fama-French three-factor regressions with t-stats, cointegration testing for pairs, seasonality studies, and a market-risk reading tested on five markets (it replaced a regime model that a test found followed single days).'],
  ['Options', 'Black-Scholes-Merton pricing with the full Greeks and risk-neutral probabilities — verified against the textbook case at 10.4506 versus 10.45.'],
  ['Honesty by construction', 'Momentum tested point-in-time on 2011-2026 prices, delisted stocks included, with the rules written down before the run: the top fifth beat the bottom fifth by 1.5% a month before trading costs (a net-of-costs test is pre-registered and not yet run). Its edge did not show among the largest, most liquid stocks, and our other factors are not yet tested. We publish all of it.'],
]

// One grid for every section (18 Nov 2026 design review: the header, hero,
// steps and cards sat on three different left edges). 1168px of content,
// which leaves 136px each side at 1440; 16px margins on a phone.
const GRID = 'mx-auto w-full max-w-[1216px] px-4 sm:px-6'

const EVIDENCE_LABEL = {
  passed: 'Passed', failed: 'Did not pass', tested: 'Tested',
}

/**
 * The factor evidence from the Advanced page, as the first thing a visitor
 * reads beside the headline: what the model is made of, how much of the
 * score each part carries, and which parts have actually been tested. Same
 * endpoint, same words and the same status colours as the Advanced board.
 * Renders nothing until the data arrives — an evidence claim invented here
 * would defeat the point of the list.
 */
function EvidenceList({ data }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-5 sm:p-6">
      <h2 className="text-base font-semibold text-white">What we actually know about each factor</h2>
      <p className="text-xs text-gray-400 mt-1">Evidence status, by weight in the model</p>

      {/* One grid for all rows, so every weight ends on one right edge and
          every status chip on another. Phones: two lines per row, the chip
          under the weight. */}
      <div className="mt-4 grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_auto_auto] gap-x-4">
        {data.factors.map(f => {
          const key = evidenceKey(f)
          const label = EVIDENCE_LABEL[key]
            || (f.status === 'testable_now' ? 'Testable from prices' : 'Cannot test yet')
          return (
            <div key={f.factor}
                 className="col-span-full grid grid-cols-subgrid gap-y-1.5 border-t border-gray-800 py-3">
              <div className="min-w-0 row-span-2 sm:row-span-1">
                <p className="capitalize text-sm text-gray-100">{f.factor.replace(/_/g, ' ')}</p>
                <p className="text-xs text-gray-400 mt-0.5">{f.plain}</p>
              </div>
              <div className="text-right"
                   title="Weight in the live four-factor model, which produces every score and ranking on the site; the six-factor model's weight in brackets.">
                <p className="font-mono font-medium text-base leading-none text-white tabular-nums">
                  {f.weight_v1_pct == null ? '—' : `${f.weight_v1_pct}%`}
                </p>
                {f.weight_pct != null && (
                  <p className="text-xs text-gray-400 mt-1 whitespace-nowrap">({f.weight_pct}% in 6-factor)</p>
                )}
              </div>
              <span className={`col-start-2 sm:col-start-3 sm:row-start-1 justify-self-end self-start
                               whitespace-nowrap text-xs leading-none px-2 py-1.5 rounded border ${EVIDENCE_CLASS[key]}`}>
                {label}
              </span>
            </div>
          )
        })}
      </div>

      {(data.why_this_table_exists || data.unblocking?.note) && (
        <details className="group border-t border-gray-800 pt-3">
          <summary className="cursor-pointer select-none list-none text-xs text-gray-300 underline underline-offset-4 decoration-gray-600 hover:text-white [text-wrap-style:balance]">
            <span className="group-open:hidden">Why this table exists, and when the rest can be&nbsp;tested&nbsp;▸</span>
            <span className="hidden group-open:inline">Hide ▾</span>
          </summary>
          <p className="mt-2 text-xs text-gray-400 leading-relaxed">{data.why_this_table_exists}</p>
          {data.unblocking?.note && (
            <p className="mt-2 text-xs text-gray-400 leading-relaxed">{data.unblocking.note}</p>
          )}
        </details>
      )}
    </div>
  )
}

// The panel's frame while the list loads or when it cannot be read: his
// heading and subtitle, no rows (nothing is claimed without the data), at the
// loaded panel's height.
function EvidenceShell({ busy }) {
  return (
    <div aria-busy={busy ? 'true' : undefined}
         className="rounded-xl border border-gray-800 bg-gray-900/70 p-5 sm:p-6 min-h-[729px] sm:min-h-[517px]">
      <h2 className="text-base font-semibold text-white">What we actually know about each factor</h2>
      <p className="text-xs text-gray-400 mt-1">Evidence status, by weight in the model</p>
      <div className="mt-4 border-t border-gray-800" />
    </div>
  )
}

export default function Landing() {
  const navigate = useNavigate()
  const goSignIn = () => navigate('/login')

  // Read live rather than hardcode. The number here said 2,401 for long enough
  // that it drifted 303 clear of the truth without anything noticing, because
  // a literal in a JSX array cannot correct itself. The scan publishes what it
  // actually scored, so ask it.
  const { data: scan } = useQuery({
    queryKey: ['universe-status'],
    queryFn: getScanStatus,
    staleTime: 60 * 60 * 1000,
    retry: 1,
  })
  // Same key and request as the Advanced board, so a visitor who signs in
  // does not fetch it twice.
  const { data: evidence, isLoading: evidenceLoading } = useQuery({
    queryKey: ['factorEvidence'],
    queryFn: () => getFactorEvidence(false),
    staleTime: 30 * 60 * 1000,
    retry: false,
  })
  const hasEvidence = evidence?.factors?.length > 0
  // The panel always holds its place (heading, subtitle and the measured
  // height of the six rows): while the list loads, and also when it cannot be
  // read (API down or rate-limited), when it stays as a quiet frame instead of
  // disappearing. Inserting or removing it late measured layout shifts of
  // 0.277 and 0.305 on a phone (18 Nov 2026).
  // The axios interceptor already returns the body (api.js), so the count is
  // scan.succeeded. Reading scan.data.succeeded was always undefined and the
  // page showed the fallback, 2,704, while the scan scored 2,462 (2026-10-14).
  const scored = scan?.succeeded
  // No number when the live count is unavailable (V4-10, 18 Nov 2026): the old
  // fallback, 2,704, was higher than any real scan and looked exactly like a
  // live figure. "Thousands" is the page's own word for it (the lead above).
  const scoredLabel = scored != null ? Number(scored).toLocaleString('en-IN') : 'Thousands'

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      {/* Top bar */}
      <header className={`${GRID} flex items-center justify-between py-4`}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center">
            <Zap size={15} className="text-white" />
          </div>
          <span className="font-bold text-white tracking-tight">Quant India</span>
        </div>
        <button onClick={goSignIn} className="btn-primary text-sm">Sign in</button>
      </header>

      {/* Hero: the headline, and beside it (under it on smaller screens) the
          evidence list — what the model is, said with what is known about it. */}
      <section className={`${GRID} pt-10 sm:pt-16 pb-12 sm:pb-16 grid gap-y-10 xl:grid-cols-12 xl:gap-x-12 xl:items-start`}>
        <div className="xl:col-span-5">
          <h1 className="text-[30px] leading-[1.15] sm:text-5xl sm:leading-[1.08] font-bold text-white tracking-tight max-w-[14em]">
            The maths behind quant portfolios, applied to the NSE
          </h1>
          <p className="mt-6 text-base text-gray-400 leading-relaxed max-w-[36rem]">
            A four-factor alpha model scoring thousands of NSE stocks daily. Nine portfolio
            optimisers — Markowitz, Black-Litterman, HRP, Min-CVaR. Monte Carlo,
            GARCH volatility, Fama-French factors and a tested market-risk reading.
            Build a portfolio with them, see exactly what could go wrong, and
            paper-trade it before risking a rupee.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button onClick={goSignIn} className="btn-primary">Get started — it's free</button>
            <a href="#features" className="btn-ghost">See what's inside</a>
          </div>
          <p className="mt-4 text-xs text-gray-400">Signals &amp; research only — not financial advice.</p>
          <NotAdvice className="mt-1" />
        </div>
        <div className="xl:col-span-7">
          {hasEvidence ? <EvidenceList data={evidence} /> : <EvidenceShell busy={evidenceLoading} />}
        </div>
      </section>

      {/* Hard numbers. Each one is verifiable in the app or the repo — this is
          the technical credibility the honest positioning has to sit on.
          Plain figures on hairlines, not four tinted boxes. */}
      <section className={GRID}>
        <dl className="grid grid-cols-2 lg:grid-cols-4 gap-x-6">
          {[
            [scoredLabel, 'NSE stocks scored daily'],
            ['9', 'portfolio optimisers'],
            ['168,388', 'test assertions passing'],
            ['4', 'factors per alpha score'],
          ].map(([n, l]) => (
            <div key={l} className="flex flex-col-reverse border-t border-gray-800 py-5 lg:border-t-0 lg:border-l lg:pl-6 lg:py-2">
              <dt className="text-xs text-gray-400 mt-2">{l}</dt>
              <dd className="font-mono font-medium text-[30px] leading-none text-white tabular-nums">{n}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* How it works */}
      <section id="features" className={`${GRID} pt-20 pb-12 scroll-mt-4`}>
        <h2 className="text-[30px] leading-tight font-bold text-white">How it works</h2>
        <p className="text-base text-gray-400 mt-2">
          Five steps, about ten minutes, no money at risk.
        </p>
        {/* One numbered row from 1280px: the titles share a line and the
            texts start together (subgrid), whatever wraps. Narrower, each
            step is a row, its text in the same column as Under the hood. */}
        <ol className="mt-8 grid gap-x-6 xl:grid-cols-5 xl:grid-rows-[auto_1fr]">
          {STEPS.map(({ title, desc }) => (
            <li key={title}
                className="border-t border-gray-800 py-5 xl:pb-0 grid gap-y-2 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] md:gap-x-6 lg:grid-cols-5 xl:row-span-2 xl:grid-rows-subgrid xl:grid-cols-1">
              <h3 className="text-base font-semibold text-white leading-snug">{title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed lg:col-span-3 xl:col-span-1">{desc}</p>
            </li>
          ))}
        </ol>
        <div className="mt-8 rounded-xl border border-gray-800 bg-gray-900/70 p-5 sm:p-6 md:grid md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] md:gap-x-6 lg:grid-cols-5">
          <h3 className="text-base font-semibold text-white">{SCORECARD.title}</h3>
          <p className="text-sm text-gray-400 leading-relaxed mt-2 md:mt-0 lg:col-span-3">{SCORECARD.desc}</p>
        </div>
      </section>

      {/* Under the hood: one row per area, title beside its text, rather than
          a band of six cards. */}
      <section className={`${GRID} py-12`}>
        <h2 className="text-[30px] leading-tight font-bold text-white">Under the hood</h2>
        <p className="text-base text-gray-400 mt-2">
          Textbook methods, implemented and tested — not a black box.
        </p>
        <dl className="mt-8 border-b border-gray-800">
          {UNDER_THE_HOOD.map(([title, desc]) => (
            <div key={title} className="border-t border-gray-800 py-5 md:grid md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] md:gap-x-6 lg:grid-cols-5">
              <dt className="text-base font-semibold text-white">{title}</dt>
              <dd className="mt-2 md:mt-0 text-sm text-gray-400 leading-relaxed lg:col-span-3">{desc}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Closing CTA */}
      <section className={`${GRID} pt-8 pb-20`}>
        <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-6 sm:p-8 lg:flex lg:items-center lg:justify-between lg:gap-12">
          <div className="max-w-2xl">
            <h2 className="text-xl sm:text-[30px] sm:leading-tight font-bold text-white">Build a private watchlist, portfolio &amp; get alerts</h2>
            <p className="mt-3 text-base text-gray-400 leading-relaxed">
              Create a free account to track your holdings, run simulations, and receive
              price &amp; sentiment alerts by email.
            </p>
          </div>
          <button onClick={goSignIn} className="btn-primary mt-6 lg:mt-0 shrink-0">Create your account</button>
        </div>
      </section>

      <footer className="border-t border-gray-800">
        <p className={`${GRID} py-6 text-xs text-gray-400`}>
          Quant India · Data: Yahoo Finance, NSE &amp; news publishers · Not financial advice
          <span className="block sm:inline mt-2 sm:mt-0">
            <span className="hidden sm:inline"> · </span>
            <Link to="/privacy" className="text-gray-300 hover:text-white underline underline-offset-4">Privacy</Link>
            {' · '}
            <Link to="/terms" className="text-gray-300 hover:text-white underline underline-offset-4">Terms</Link>
          </span>
        </p>
      </footer>
    </div>
  )
}
