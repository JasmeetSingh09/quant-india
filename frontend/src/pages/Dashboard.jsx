import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getMCX, getRegime, getMarketNews, getPrice, getPredictionTrack, getBenchmark } from '../api'
import Spinner from '../components/Spinner'
import RegimeBadge from '../components/RegimeBadge'
import Explainer from '../components/Explainer'
import CapTierPicks from '../components/CapTierPicks'
import Leaderboard from '../components/Leaderboard'
import EmailOptIn from '../components/EmailOptIn'
import { ChevronDown, TrendingUp, TrendingDown, Sparkles, ArrowUpRight, ArrowDownRight, RefreshCw, History } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import usePersistentState from '../usePersistentState'

const NIFTY_STOCKS = ['RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS','ICICIBANK.NS']

const FACTORS = [
  ['momentum',  'Momentum'],
  ['quality',   'Quality'],
  ['value',     'Value'],
  ['sentiment', 'Sentiment'],
]

function dominant(contrib = {}) {
  const e = Object.entries(contrib)
  if (!e.length) return null
  return e.reduce((a, b) => (Math.abs(b[1]) > Math.abs(a[1]) ? b : a))
}

function PickCard({ r, buy }) {
  const name = r.ticker.replace('.NS', '')
  const score = r.alpha_score
  const dom = dominant(r.contributions)
  return (
    <div className={`rounded-xl border p-3.5 bg-gray-900/60 ${buy ? 'border-green-700/40' : 'border-red-700/40'}`}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          {buy
            ? <ArrowUpRight className="text-green-400 shrink-0" size={15} />
            : <ArrowDownRight className="text-red-400 shrink-0" size={15} />}
          <span className="font-mono font-bold text-sm">{name}</span>
        </div>
        <span className={`text-base font-bold font-mono ${buy ? 'text-green-400' : 'text-red-400'}`}>
          {score > 0 ? '+' : ''}{score?.toFixed(0)}
        </span>
      </div>
      <div className="flex items-center justify-between text-[11px] mb-2">
        <span className={`badge-${buy ? 'green' : 'red'}`}>{r.signal}</span>
        <span className="text-gray-500" title="How much of the model's input data was available for this stock — not the chance the signal is right.">{Math.round((r.confidence || 0) * 100)}% data</span>
      </div>
      <div className="space-y-1">
        {FACTORS.map(([k, label]) => {
          const v = r.contributions?.[k] ?? 0
          const pos = v >= 0
          const w = Math.min(Math.abs(v) * 2, 100)
          return (
            <div key={k} className="flex items-center gap-2 text-[10px]">
              <span className="w-14 text-gray-500 shrink-0">{label}</span>
              <div className="flex-1 h-1 bg-gray-800 rounded-full overflow-hidden">
                <div className={`h-full ${pos ? 'bg-green-500' : 'bg-red-500'}`} style={{ width: `${w}%` }} />
              </div>
              <span className={`w-8 text-right font-mono shrink-0 ${pos ? 'text-green-400' : 'text-red-400'}`}>
                {pos ? '+' : ''}{v.toFixed(0)}
              </span>
            </div>
          )
        })}
      </div>
      {dom && (
        <p className="mt-1.5 text-[10px] text-gray-600">
          Driven by <span className="text-gray-400">{dom[0]}</span>
        </p>
      )}
    </div>
  )
}

function PriceTag({ ticker }) {
  const { data, isLoading } = useQuery({
    queryKey: ['price', ticker],
    queryFn: () => getPrice(ticker),
    // only poll while the delayed feed is active (stops ~15 min after market close)
    refetchInterval: q => (q.state.data?.feed_active ? 60000 : false),
  })
  if (isLoading) return (
    <div className="card-sm h-[72px] animate-pulse bg-gray-800/40" />
  )
  const pos = (data?.change_pct ?? 0) >= 0
  return (
    <div className="card-sm">
      <p className="text-xs text-gray-500">{ticker.replace('.NS', '')}</p>
      <p className="text-lg font-bold font-mono leading-tight mt-0.5">
        {data?.price != null ? `₹${data.price.toLocaleString('en-IN')}` : '—'}
      </p>
      <p className={`text-xs font-medium flex items-center gap-1 mt-1 ${pos ? 'text-green-400' : 'text-red-400'}`}>
        {pos ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
        {pos ? '+' : ''}{data?.change_pct?.toFixed(2) ?? '0.00'}%
      </p>
    </div>
  )
}

function CommodityRow({ c }) {
  const up = c.change_pct >= 0
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-800 last:border-0">
      <div>
        <p className="text-sm font-medium">{c.name}</p>
        <p className="text-xs text-gray-500">{c.unit}</p>
      </div>
      <div className="text-right">
        <p className="text-sm font-mono font-semibold">₹{c.price_inr?.toLocaleString('en-IN')}</p>
        <p className={`text-xs font-medium ${up ? 'text-green-400' : 'text-red-400'}`}>
          {up ? '+' : ''}{c.change_pct?.toFixed(2)}%
        </p>
      </div>
    </div>
  )
}

function NewsCard({ article }) {
  const mins = article.published_minutes_ago
  const timeStr = mins == null ? '' : mins < 60 ? `${mins}m ago` : `${Math.floor(mins / 60)}h ago`
  return (
    <a href={article.url} target="_blank" rel="noreferrer"
      className="block p-3 rounded-lg hover:bg-gray-800 transition-colors border border-transparent hover:border-gray-700">
      <p className="text-sm font-medium leading-snug line-clamp-2">{article.title}</p>
      <div className="flex items-center gap-2 mt-1.5">
        <span className="text-xs text-gray-500">{article.source}</span>
        <span className="text-gray-700">·</span>
        <span className="text-xs text-gray-500">{timeStr}</span>
        {article.macro_impacts?.length > 0 && (
          <span className="badge-yellow ml-auto">Macro Impact</span>
        )}
      </div>
    </a>
  )
}

function TrackRecord() {
  const navigate = useNavigate()
  // Defaults to 21 because that is the horizon every signal card advertises.
  // It defaulted to 3, so a card badged "21d" sat directly above a record
  // measuring a completely different question — the shortest window flatters
  // the sample count, which is exactly the wrong thing to optimise for here.
  const [days, setDays] = useState(21)
  const { data, isLoading } = useQuery({
    queryKey: ['predTrack', days],
    queryFn: () => getPredictionTrack(days),
    staleTime: 10 * 60 * 1000,
  })
  const sc = data?.scorecard
  const rawPreds = data?.predictions || []
  // The model re-logs a snapshot daily, so each stock appears once per snapshot
  // date. Every row is now measured over the SAME fixed horizon, so "longest
  // held" no longer distinguishes them — keep the most recent snapshot instead.
  const preds = Object.values(rawPreds.reduce((acc, r) => {
    const cur = acc[r.ticker]
    if (!cur || (r.date ?? '') > (cur.date ?? '')) acc[r.ticker] = r
    return acc
  }, {}))
  const pct = v => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
  const col = v => v == null ? 'text-gray-400' : v >= 0 ? 'text-green-400' : 'text-red-400'
  // Direction-aware. A negative excess return is BAD for a BUY and GOOD for a
  // SELL — the stock underperformed the index, which is what the SELL called.
  // Painting it red either way says "bad" about the model being right, which is
  // the same mistake as scoring a SELL by whether the stock went up.
  const colFor = (v, wantsDown) =>
    v == null ? 'text-gray-400'
      : (wantsDown ? v <= 0 : v >= 0) ? 'text-green-400' : 'text-red-400'

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-semibold flex items-center gap-2">
          <History size={18} className="text-blue-400" /> Track Record — did past picks actually work?
        </h2>
        <div className="flex items-center gap-1 text-xs">
          {/* Exact horizon now, not a minimum: each pick is priced N days after
              it was logged, so the three buttons really are three horizons. */}
          <span className="text-gray-500 mr-1">Horizon</span>
          {[3, 7, 14, 21].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-2 py-1 rounded ${days === d ? 'bg-blue-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}>
              {d}d
            </button>
          ))}
        </div>
      </div>

      {isLoading ? <Spinner size="sm" /> : !sc ? (
        <div className="space-y-2">
          <p className="text-sm text-gray-500">{data?.status || 'No matured predictions in this window yet — check back as the record accrues.'}</p>
          {data?.days_of_history != null && (
            <p className="text-xs text-gray-600">
              {data.total_logged} logged · {data.distinct_days} distinct day(s) · {data.days_of_history} day(s) of history · DB: {data.db_backend}
            </p>
          )}
          {data?.diagnostic && (
            <div className="text-xs text-yellow-300 border border-yellow-700/40 bg-yellow-950/20 rounded-lg p-2.5">
              ⚠ {data.diagnostic}
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Each side is scored on its own terms. A SELL is right when the
              stock FALLS, so colouring its average with the same rule as a BUY
              would paint a failed SELL green. The hit rate sits beside every
              average because a mean alone cannot tell 51% wins from 90% wins,
              and those are completely different signals. */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[['BUY', sc.by_signal?.buy, 'rose'], ['SELL', sc.by_signal?.sell, 'fell']].map(
              ([side, d, want]) => !d ? null : (
              <div key={side} className="card-sm">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="stat-label">{side} signals</p>
                  <span className="text-[11px] text-gray-500">{d.signals} signals</span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-2">
                  <div>
                    <p className="text-[11px] text-gray-500">Hit rate</p>
                    <p className={`text-base font-medium ${
                      d.hit_rate_pct >= 55 ? 'text-green-400/90'
                      : d.hit_rate_pct >= 45 ? 'text-gray-300' : 'text-red-400/90'}`}>
                      {d.hit_rate_pct}%
                    </p>
                    {/* The uncertainty is set at the same weight as the number,
                        so "53.8%" cannot be scanned as accuracy on its own. */}
                    {d.significance && !d.significance.significant_at_5pct && (
                      <p className="text-[11px] text-amber-300/80 font-medium">
                        Very uncertain · {d.signals} signals
                      </p>
                    )}
                    <p className="text-[10px] text-gray-600">share that {want}</p>
                    {d.significance && (
                      <p className="text-[10px] text-gray-500 mt-0.5"
                         title={d.significance.plain}>
                        95% CI {d.significance.ci95_low_pct}–{d.significance.ci95_high_pct}%
                        {' · '}
                        <span className={d.significance.significant_at_5pct
                          ? 'text-green-400' : 'text-gray-500'}>
                          {d.significance.significant_at_5pct
                            ? `p=${d.significance.p_value}` : 'not significant'}
                        </span>
                      </p>
                    )}
                  </div>
                  <div>
                    <p className="text-[11px] text-gray-500">Avg return</p>
                    <p className="text-lg font-semibold text-gray-200">{pct(d.avg_return_pct)}</p>
                    <p className="text-[10px] text-gray-600">median {pct(d.median_return_pct)}</p>
                  </div>
                  <div className="col-span-2 pt-1 border-t border-gray-800">
                    <p className="text-[11px] text-gray-500">
                      vs Nifty <span className={colFor(d.avg_excess_vs_nifty_pct, want === 'fell')}
                        title={want === 'fell'
                          ? 'For a SELL, underperforming the index is the signal being right.'
                          : 'For a BUY, beating the index is the signal being right.'}>
                        {pct(d.avg_excess_vs_nifty_pct)}</span>
                      <span className="text-gray-600"> · best {pct(d.best_pct)} · worst {pct(d.worst_pct)}</span>
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {sc.by_signal?.note && (
            <p className="text-[11px] text-gray-500 leading-relaxed">{sc.by_signal.note}</p>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="card-sm">
              <p className="stat-label">BUY − SELL spread<span className="text-gray-600"> (edge)</span></p>
              <p className={`stat-value ${col(sc.buy_minus_sell_pct)}`}>{pct(sc.buy_minus_sell_pct)}</p>
            </div>
            <div className="card-sm">
              <p className="stat-label">Avg excess vs Nifty</p>
              <p className={`stat-value ${col(sc.avg_excess_vs_nifty_pct)}`}>{pct(sc.avg_excess_vs_nifty_pct)}</p>
            </div>
          </div>

          {/* Picks are logged daily, so consecutive observations of one stock
              share almost all of their measurement window. Printing the raw
              count invites the reader to hear that many independent bets. */}
          {/* The honest sample, beside the full one. Shown together because the
              interesting thing is how far they disagree — when they do, the
              overlap was doing the work. */}
          {sc.independent_sample?.by_signal && (
            <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-3">
              <p className="text-[11px] uppercase tracking-wide text-amber-400/90 mb-1">
                Preliminary — {sc.independent_sample.observations} independent windows
              </p>
              <p className="text-[11px] text-amber-200/70 mb-2 leading-relaxed">
                Too little independent data to say whether the model has predictive
                skill. Read the percentages below as noisy, not as accuracy.
              </p>
              <div className="grid grid-cols-2 gap-3">
                {[['BUY', sc.independent_sample.by_signal.buy, 'rose'],
                  ['SELL', sc.independent_sample.by_signal.sell, 'fell']].map(
                  ([side, d, want]) => !d ? null : (
                  <div key={side}>
                    <p className="text-[11px] text-gray-500">{side} · {d.signals} signals</p>
                    <p className={`text-lg font-semibold ${
                      d.hit_rate_pct >= 55 ? 'text-green-400'
                      : d.hit_rate_pct >= 45 ? 'text-gray-200' : 'text-red-400'}`}>
                      {d.hit_rate_pct}%
                    </p>
                    <p className="text-[10px] text-gray-600">share that {want}</p>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
                {sc.independent_sample.note}
              </p>
            </div>
          )}

          {sc.independence?.overlapping && (
            <div className="rounded-lg p-3 text-xs border border-amber-800/60 bg-amber-900/10 text-amber-200/90 leading-relaxed">
              <b>Sample size:</b> {sc.independence.note}
            </div>
          )}

          <div className={`rounded-lg p-3 text-sm border ${
            (sc.buy_minus_sell_pct ?? 0) > 0 ? 'border-green-800 bg-green-900/15 text-green-300'
                                             : 'border-yellow-800 bg-yellow-900/15 text-yellow-200'}`}>
            <b>Verdict:</b> {sc.verdict}
            <span className="block text-xs text-gray-400 mt-1">
              {days !== 21 && (
                <span className="block text-amber-300/80 mb-1">
                  Showing a {days}-day horizon. Signals are issued on a 21-day view,
                  so this measures a different question than the cards above.
                </span>
              )}
              {sc.independence?.period && (
                <span className="block text-gray-500 mb-1">
                  {sc.independence.period} · {sc.independence.distinct_stocks} stocks · {days}-day horizon
                </span>
              )}
              {sc.matured_predictions} signal observations
              {sc.independence?.effective_independent_estimate
                ? ` (~${sc.independence.effective_independent_estimate} independent)` : ''}
              {' '}· alpha↔return correlation {sc.alpha_vs_return_correlation ?? '—'}
              {' '}(a value near 0 means the score barely predicts returns — expected on small samples).
            </span>
          </div>

          <div className="overflow-x-auto">
            <div className="table-wrap">
              <table className="w-full min-w-[34rem] text-sm">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-gray-800">
                  <th className="text-left py-2">Stock</th>
                  <th className="text-left">Signal</th>
                  <th className="text-right">Actual return</th>
                  <th className="text-right">vs Nifty</th>
                  <th className="text-right">Held</th>
                  <th className="text-right">Logged</th>
                </tr>
              </thead>
              <tbody>
                {preds.slice().sort((a,b) => (b.forward_return_pct ?? 0) - (a.forward_return_pct ?? 0)).map((r, i) => {
                  const isBuy = r.signal && r.signal.includes('BUY')
                  const isSell = r.signal && r.signal.includes('SELL')
                  return (
                    <tr key={i}
                        onClick={() => navigate(`/stock?ticker=${encodeURIComponent(r.ticker)}`)}
                        className="border-b border-gray-800 last:border-0 hover:bg-gray-800/50 cursor-pointer">
                      <td className="py-1.5 font-mono text-green-400 hover:underline">{r.ticker.replace('.NS','')}</td>
                      <td><span className={`badge-${isBuy ? 'green' : isSell ? 'red' : 'yellow'}`}>{r.signal}</span></td>
                      <td className={`text-right font-mono ${col(r.forward_return_pct)}`}>{pct(r.forward_return_pct)}</td>
                      <td className={`text-right font-mono ${col(r.excess_pct)}`}>{pct(r.excess_pct)}</td>
                      <td className="text-right text-gray-400">{r.days_held}d</td>
                      <td className="text-right text-gray-500 text-xs">{r.date}</td>
                    </tr>
                  )
                })}
              </tbody>
              </table>
            </div>
          </div>
          <p className="text-xs text-gray-600">
            "Actual return" = how the stock moved from the day it was logged until now. A BUY that went up
            (green) or a SELL that went down was "right." One row per stock (its longest-held snapshot); the
            model re-logs daily, so the headline stats above still use every snapshot. Small samples are noisy.
          </p>
        </>
      )}
    </div>
  )
}

/**
 * RegimeBanner — what the market is doing, readable at a glance.
 *
 * The regime was previously a grid of statistics near the bottom of the page,
 * which buried the one thing a user wants before looking at any signal. The
 * probability is shown as the model's own words rather than a bare percentage:
 * a filtered HMM posterior saturates, and printing "100%" reads as "the market
 * cannot turn", which no model can claim.
 */
function RegimeBanner({ regime, loading }) {
  if (loading || !regime?.current_regime) return null
  const label = regime.current_regime
  const tone = label === 'Bull' ? 'green' : label === 'Bear' ? 'red' : 'yellow'
  const ring = { green: 'border-green-800/60 bg-green-900/15',
                 red: 'border-red-800/60 bg-red-900/15',
                 yellow: 'border-yellow-800/60 bg-yellow-900/15' }[tone]
  const text = { green: 'text-green-400', red: 'text-red-400', yellow: 'text-yellow-400' }[tone]
  const prob = regime.current_proba_display
    ?? (regime.current_proba?.[label] != null
        ? `${(regime.current_proba[label] * 100).toFixed(1)}%` : null)

  return (
    <div className={`card border ${ring} flex flex-col gap-2`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-baseline gap-3">
          <span className={`text-xl font-bold tracking-tight ${text}`}>{label.toUpperCase()} REGIME</span>
          {prob && <span className="text-sm text-gray-400 font-mono">{prob} model probability</span>}
        </div>
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">
          3-state Gaussian HMM · Nifty 50
        </span>
      </div>
      {regime.current_proba_note && (
        <p className="text-xs text-gray-400 leading-relaxed">{regime.current_proba_note}</p>
      )}
      <p className="text-[11px] text-gray-600">
        Describes which regime best explains recent returns. It is not a forecast,
        and it is not a reason on its own to buy or sell anything.
      </p>
    </div>
  )
}

/**
 * NiftyLevel — the benchmark's own state, next to its constituents.
 *
 * Showing four individual holdings without the index they belong to leaves the
 * reader to infer the market's direction from a sample of four.
 */
function NiftyLevel() {
  const { data } = useQuery({
    queryKey: ['benchmarkToday'],
    queryFn: () => getBenchmark(5),
    staleTime: 10 * 60 * 1000,
    retry: false,
  })
  if (!data || data.return_pct == null) return null
  const up = data.return_pct >= 0
  return (
    <span className="text-xs text-gray-400">
      Nifty 50 (5d){' '}
      <span className={`font-mono font-semibold ${up ? 'text-green-400' : 'text-red-400'}`}>
        {up ? '+' : ''}{data.return_pct}%
      </span>
    </span>
  )
}

export default function Dashboard() {
  // Collapsed by default: the three questions come first, context follows.
  const [showContext, setShowContext] = usePersistentState('dash.showContext', false)
  const { data: mcx,    isLoading: mcxLoading,    isError: mcxError    } = useQuery({ queryKey: ['mcx'],     queryFn: getMCX,        refetchInterval: 120000 })
  const { data: regime, isLoading: regimeLoading, isError: regimeError } = useQuery({ queryKey: ['regime'],  queryFn: getRegime,     staleTime: 300000 })
  const { data: news,   isLoading: newsLoading,   isError: newsError   } = useQuery({ queryKey: ['mktNews'], queryFn: getMarketNews, staleTime: 60000 })

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Market Dashboard</h1>
          <p className="text-gray-400 text-sm mt-0.5">
            {new Date().toLocaleDateString('en-IN', { weekday:'long', year:'numeric', month:'long', day:'numeric' })}
          </p>
        </div>
        {regime && !regimeLoading && (
          <div className="text-right">
            <p className="text-xs text-gray-500 mb-1">Market Regime</p>
            <RegimeBadge regime={regime.current_regime} proba={regime.current_proba} />
          </div>
        )}
      </div>

      {/* The dashboard answers three questions in order: what is the market
          doing, what should I look at, and does the model actually work.
          Everything else is context and sits below the fold, because a page
          that shows nine things equally urgently shows nothing. */}

      {/* Market context and the user's own portfolios lead, as requested — the
          two things someone checks first on arriving. The model's own three
          questions follow directly underneath. */}
      <div>
        <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Nifty 50 — Top Holdings</h2>
          <NiftyLevel />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {NIFTY_STOCKS.map(t => <PriceTag key={t} ticker={t} />)}
        </div>
      </div>

      <Leaderboard n={5} />

      {/* 1. What is the market doing? */}
      <RegimeBanner regime={regime} loading={regimeLoading} />

      {/* 2. What should I look at? */}
      <CapTierPicks n={10} />

      {/* 3. Does the model actually work? Directly under the picks on purpose:
          a signal and its measured track record belong on the same screen. */}
      <TrackRecord />

      {/* Asked once, then never again — see the component. */}
      <EmailOptIn />

      {/* Market context, collapsed by default. Commodities, news and the regime
          detail inform a decision rather than driving one, and leaving nine
          sections expanded meant the three that matter competed with six that
          did not. Nothing is removed — it opens in one click. */}
      <button onClick={() => setShowContext(c => !c)}
              aria-expanded={showContext}
              className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors border-t border-gray-800 pt-3 w-full">
        {showContext ? 'Hide' : 'Show'} market context — commodities, news, regime detail
        <ChevronDown size={13} className={`transition-transform ${showContext ? 'rotate-180' : ''}`} />
      </button>

      {showContext && (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* MCX Commodities */}
        <div className="card col-span-1">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">MCX Commodities</h2>
            <Link to="/markets" className="text-xs text-green-400 hover:text-green-300">View all →</Link>
          </div>
          {mcxLoading ? <Spinner size="sm" /> : mcxError ? (
            <p className="text-xs text-red-400 py-4 text-center">Could not load commodity data.</p>
          ) : (
            <>
              <p className="text-xs text-gray-500 mb-3">
                USD/INR: <span className="text-gray-300 font-mono">{mcx?.usd_inr_rate}</span>
              </p>
              {mcx?.commodities?.map(c => <CommodityRow key={c.key} c={c} />)}
            </>
          )}
        </div>

        {/* Market News */}
        <div className="card col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">Market News</h2>
            <Link to="/markets" className="text-xs text-green-400 hover:text-green-300">View all →</Link>
          </div>
          {newsLoading ? <Spinner size="sm" /> : newsError ? (
            <p className="text-xs text-red-400 py-4 text-center">Could not load news.</p>
          ) : (
            <div className="space-y-1">
              {news?.articles?.slice(0, 6).map((a, i) => <NewsCard key={i} article={a} />)}
            </div>
          )}
        </div>
      </div>
      )}

      {/* Regime detail */}
      {regimeError && (
        <p className="text-xs text-red-400 text-center py-2">Could not load market regime data.</p>
      )}
      {regime && !regimeLoading && (
        <div className="card">
          <h2 className="font-semibold mb-4">Market Regime Analysis <span className="text-xs text-gray-500 font-normal ml-2">3-State Gaussian HMM on Nifty 50</span></h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Object.entries(regime.regime_stats || {}).map(([label, stats]) => (
              <div key={label} className={`card-sm border ${
                label==='Bull'?'border-green-800/50':label==='Bear'?'border-red-800/50':'border-yellow-800/50'
              }`}>
                <p className={`font-semibold text-sm ${
                  label==='Bull'?'text-green-400':label==='Bear'?'text-red-400':'text-yellow-400'
                }`}>{label}</p>
                <p className="text-xs text-gray-500 mt-1">{stats.pct_of_time}% of time · {stats.n_days}d</p>
                {/* Lead with the daily figure. Annualising a 34-day regime is an
                    extrapolation, not a CAGR the market ever delivered, so it is
                    shown as a conditional and clearly de-emphasised. */}
                <p className={`text-sm font-mono mt-1 ${stats.avg_daily_ret>=0?'text-green-400':'text-red-400'}`}>
                  {stats.avg_daily_ret>0?'+':''}{stats.avg_daily_ret}%<span className="text-gray-500">/day</span>
                </p>
                <p className="text-[11px] text-gray-500 mt-0.5 font-mono">
                  vol {stats.avg_daily_vol}%/day
                </p>
                <p className="text-[11px] text-gray-600 mt-1 leading-snug">
                  if sustained 1y: {stats.annualised_ret>0?'+':''}{Math.round(stats.annualised_ret)}%
                </p>
              </div>
            ))}
            <div className="card-sm">
              <p className="text-xs text-gray-500">Interpretation</p>
              <p className="text-xs text-gray-300 mt-1 leading-relaxed">{regime.interpretation}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
