import { useMutation, useQuery } from '@tanstack/react-query'
import { compareStrategies, getPortfolio } from '../api'
import Spinner from './Spinner'

/**
 * StrategyCompare — three construction methods, no winner named.
 *
 * The table deliberately omits a "best" column. Ranking strategies by past
 * return is the most reliable way to pick the one that disappoints next: the
 * highest return is usually the one that took the most risk, traded the most,
 * or was luckiest, and none of those repeat on demand.
 *
 * So return sits beside the things that explain it — volatility, drawdown,
 * turnover and the cost of that turnover — and the reader does the ranking with
 * everything in view.
 */
const num = (v, d = 2) => v == null ? '—' : Number(v).toFixed(d)

export default function StrategyCompare({ tickers: propTickers, currentWeights: propWeights }) {
  const run = useMutation({ mutationFn: compareStrategies })

  // Mounted as a bare tab with no props, so it sources the portfolio itself.
  // Props still win when something else wants to compare a different basket.
  const { data: pf, isLoading: pfLoading } = useQuery({
    queryKey: ['portfolio'], queryFn: getPortfolio, enabled: !propTickers,
  })
  const holdings = pf?.holdings || []
  const tickers = propTickers || holdings.map(h => h.ticker)
  const total = Number(pf?.total_current_value) || 0
  const currentWeights = propWeights || (total > 0
    ? Object.fromEntries(holdings.map(h => [h.ticker, (h.current_value / total) * 100]))
    : null)

  const enough = (tickers || []).length >= 3

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">How would other methods have built this?</h2>
        <span className="text-[11px] text-gray-500">same period · same costs</span>
      </div>

      {!run.data && (
        <>
          <p className="text-xs text-gray-400 leading-relaxed">
            Equal weight, mean-variance and Black-Litterman on the same holdings,
            measured identically. Equal weight is the baseline the others have to
            beat to justify their estimates.
          </p>
          {/* Which holdings, named. "Your holdings" is ambiguous the moment a
              paper simulation is running with a different set — and the
              Simulator is a separate store, so the two genuinely differ. A
              comparison that does not say what it compared invites the reader
              to assume the wrong basket. */}
          <div className="text-[11px] text-gray-500 leading-relaxed">
            {propTickers
              ? <>Comparing the <span className="text-gray-300">basket passed in</span> by this page.</>
              : <>Comparing your <span className="text-gray-300">saved Portfolio</span> — not
                 the Simulator, which keeps its own separate positions.</>}
            {tickers?.length > 0 && (
              <div className="mt-1 font-mono text-gray-400 break-words">
                {tickers.map(t => String(t).replace('.NS', '')).join(' · ')}
              </div>
            )}
          </div>
          <button onClick={() => run.mutate({ tickers, current_weights: currentWeights })}
                  disabled={run.isPending || pfLoading || !enough}
                  className="btn-ghost text-xs">
            {run.isPending ? 'Measuring…'
              : pfLoading ? 'Loading your saved Portfolio…'
              : enough ? `Compare methods on these ${tickers.length}`
              : `Needs at least 3 holdings in your saved Portfolio (has ${tickers?.length || 0})`}
          </button>
        </>
      )}

      {run.isPending && <Spinner size="sm" />}
      {run.isError && <p className="banner-error text-xs">{String(run.error)}</p>}

      {run.data && (
        <>
          <div className="table-wrap">
            <table className="w-full text-sm min-w-[44rem]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="text-left py-1">Method</th>
                  <th className="text-right py-1">CAGR</th>
                  <th className="text-right py-1">Vol</th>
                  <th className="text-right py-1">Sharpe</th>
                  <th className="text-right py-1">Sortino</th>
                  <th className="text-right py-1">Max fall</th>
                  <th className="text-right py-1">Turnover</th>
                  <th className="text-right py-1">Cost</th>
                  <th className="text-right py-1">vs Nifty</th>
                </tr>
              </thead>
              <tbody>
                {run.data.strategies.map(s => (
                  <tr key={s.strategy} className="border-t border-gray-800">
                    <td className="py-1.5 font-medium" title={s.why}>{s.strategy}</td>
                    <td className={`py-1.5 text-right font-mono ${
                      (s.cagr_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {num(s.cagr_pct)}%
                    </td>
                    <td className="py-1.5 text-right font-mono text-gray-400">{num(s.volatility_pct)}%</td>
                    <td className="py-1.5 text-right font-mono text-gray-300">{num(s.sharpe, 2)}</td>
                    <td className="py-1.5 text-right font-mono text-gray-300">{num(s.sortino, 2)}</td>
                    <td className="py-1.5 text-right font-mono text-red-400">{num(s.max_drawdown_pct)}%</td>
                    <td className="py-1.5 text-right font-mono text-gray-400">{num(s.turnover_pct, 0)}%</td>
                    <td className="py-1.5 text-right font-mono text-gray-500">{num(s.cost_of_turnover_pct, 2)}%</td>
                    <td className={`py-1.5 text-right font-mono ${
                      (s.excess_vs_nifty_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {s.excess_vs_nifty_pct == null ? '—' : `${num(s.excess_vs_nifty_pct)}%`}
                    </td>
                  </tr>
                ))}
                {run.data.benchmark && (
                  <tr className="border-t border-gray-700">
                    <td className="py-1.5 text-gray-500">Nifty 50</td>
                    <td className="py-1.5 text-right font-mono text-gray-500">
                      {num(run.data.benchmark.cagr_pct)}%
                    </td>
                    <td className="py-1.5 text-right font-mono text-gray-500">
                      {num(run.data.benchmark.volatility_pct)}%
                    </td>
                    <td className="py-1.5 text-right font-mono text-gray-500">
                      {num(run.data.benchmark.sharpe, 2)}
                    </td>
                    <td colSpan={5}></td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* The refusal, stated where a "winner" column would otherwise sit. */}
          <p className="text-xs text-amber-200/85 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
            {run.data.no_winner_named}
          </p>

          <div className="space-y-1">
            {run.data.strategies.map(s => (
              <p key={s.strategy} className="text-[11px] text-gray-500 leading-relaxed">
                <b className="text-gray-400">{s.strategy}:</b> {s.why}
              </p>
            ))}
          </div>

          <p className="text-[10px] text-gray-600 leading-relaxed">
            {run.data.period} · {run.data.limits}
          </p>
        </>
      )}
    </div>
  )
}
