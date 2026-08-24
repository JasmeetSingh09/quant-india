import { useMutation } from '@tanstack/react-query'
import { getUniverseSensitivity } from '../api'
import Spinner from './Spinner'

/**
 * UniverseSensitivity — how much of the "edge" is a choice.
 *
 * This is the most important thing the backtest can report, and it is not a
 * return. The same 12-1 momentum strategy over the same years produces
 * anywhere from roughly nothing to more than twenty points of annual excess,
 * depending only on which universe is traded and whether that universe was
 * picked using information from the future.
 *
 * The spread is wider than any edge being claimed, which means the
 * configuration is doing more work than the factor. Showing the best row and
 * calling it a backtest is how a quant app fools itself, so every row is here
 * and the range is the headline.
 *
 * Note the drawdown column: it gets WORSE as the look-ahead is removed. That
 * is the tell. The flattering configurations were quietly selecting survivors.
 */
const num = (v, d = 2) => v == null ? '—' : Number(v).toFixed(d)

export default function UniverseSensitivity() {
  const run = useMutation({ mutationFn: getUniverseSensitivity })
  const d = run.data

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">How much of the edge is a choice?</h2>
        <span className="text-[11px] text-gray-500">same strategy · same years</span>
      </div>

      {!d && (
        <>
          <p className="text-xs text-gray-400 leading-relaxed">
            The same momentum strategy, run four ways: a narrow large-cap list, a
            wide list, and the wide list with a point-in-time liquidity screen so
            the past is traded using what was known at the time.
          </p>
          <button onClick={() => run.mutate()} disabled={run.isPending}
                  className="btn-ghost text-xs">
            {run.isPending ? 'Running four backtests…' : 'Run the sensitivity test'}
          </button>
          <p className="text-[11px] text-gray-600">
            Four full backtests over ~200 names. This takes several minutes.
          </p>
        </>
      )}

      {run.isPending && <Spinner size="sm" />}
      {run.isError && <p className="banner-error text-xs">{String(run.error)}</p>}

      {d && (
        <>
          <p className="text-sm text-amber-100/90 border-l-2 border-amber-600/70 pl-3 leading-relaxed">
            {d.headline}
          </p>

          <div className="table-wrap">
            <table className="w-full text-sm min-w-[40rem]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="text-left py-1">Configuration</th>
                  <th className="text-right py-1">Names</th>
                  <th className="text-right py-1">Look-ahead removed</th>
                  <th className="text-right py-1">CAGR</th>
                  <th className="text-right py-1">Sharpe</th>
                  <th className="text-right py-1">Max fall</th>
                  <th className="text-right py-1">vs Nifty</th>
                </tr>
              </thead>
              <tbody>
                {d.configurations.map(c => c.error ? (
                  <tr key={c.config} className="border-t border-gray-800">
                    <td className="py-1.5 text-gray-400">{c.config}</td>
                    <td colSpan={6} className="py-1.5 text-[11px] text-gray-500">{c.error}</td>
                  </tr>
                ) : (
                  <tr key={c.config} className="border-t border-gray-800">
                    <td className="py-1.5 text-gray-200">{c.config}</td>
                    <td className="py-1.5 text-right font-mono text-gray-400">{c.universe_size}</td>
                    <td className="py-1.5 text-right text-[11px]">
                      {c.point_in_time
                        ? <span className="text-green-400">yes</span>
                        : <span className="text-yellow-400/90">no</span>}
                    </td>
                    <td className="py-1.5 text-right font-mono text-gray-300">{num(c.cagr_pct)}%</td>
                    <td className="py-1.5 text-right font-mono text-gray-400">{num(c.sharpe, 3)}</td>
                    <td className="py-1.5 text-right font-mono text-red-400">{num(c.max_drawdown_pct)}%</td>
                    <td className="py-1.5 text-right font-mono text-gray-200">
                      {c.excess_vs_nifty_pct > 0 ? '+' : ''}{num(c.excess_vs_nifty_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-gray-400 leading-relaxed">{d.what_it_means}</p>

          <p className="text-[11px] text-amber-200/80 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
            {d.still_not_clean}
          </p>

          <p className="text-xs font-medium text-gray-200">{d.verdict}</p>
        </>
      )}
    </div>
  )
}
