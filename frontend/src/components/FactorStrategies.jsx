import { useMutation } from '@tanstack/react-query'
import { getFactorStrategies } from '../api'
import Spinner from './Spinner'

/**
 * FactorStrategies — the factor strategies that can honestly be backtested,
 * and the ones that cannot, in the same table.
 *
 * The obvious build is a lab comparing Value, Quality, Growth, Momentum and
 * Low Risk. Four of those cannot be built here without lying: they read the
 * current balance sheet or current news, so a 2019 ranking would be made from
 * information published years later. Their equity curves would look like
 * evidence and be artefacts.
 *
 * Leaving them out silently was the easy version, and it would have implied
 * the lab tested everything worth testing. They get rows saying why they are
 * absent, which is the more useful statement anyway.
 */
const num = (v, d = 2) => v == null ? '—' : Number(v).toFixed(d)

const VS = {
  ahead: 'text-green-400',
  behind: 'text-red-400',
  matched: 'text-gray-400',
}

export default function FactorStrategies() {
  const run = useMutation({ mutationFn: () => getFactorStrategies() })
  const d = run.data

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">Factor strategies, tested</h2>
        <span className="text-[11px] text-gray-500">walk-forward · costs included</span>
      </div>

      {!d && (
        <>
          <p className="text-xs text-gray-400 leading-relaxed">
            Hold the top fifth of the universe by one factor, rebalanced monthly,
            against the Nifty. Only the factors that can be rebuilt from prices
            alone are testable — the rest are listed with the reason.
          </p>
          <button onClick={() => run.mutate()} disabled={run.isPending}
                  className="btn-ghost text-xs">
            {run.isPending ? 'Running backtests…' : 'Run the comparison'}
          </button>
          <p className="text-[11px] text-gray-600">
            Downloads a full universe and replays seven years. Takes a minute.
          </p>
        </>
      )}

      {run.isPending && <Spinner size="sm" />}
      {run.isError && <p className="banner-error text-xs">{String(run.error)}</p>}

      {d && (
        <>
          <div className="table-wrap">
            <table className="w-full text-sm min-w-[38rem]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="text-left py-1">Strategy</th>
                  <th className="text-right py-1">CAGR</th>
                  <th className="text-right py-1">Vol</th>
                  <th className="text-right py-1">Sharpe</th>
                  <th className="text-right py-1">Max fall</th>
                  <th className="text-right py-1">vs Nifty</th>
                </tr>
              </thead>
              <tbody>
                {d.tested.map(s => (
                  <tr key={s.factor} className="border-t border-gray-800">
                    <td className="py-2">
                      <span className="capitalize text-gray-200">
                        {s.factor.replace(/_/g, ' ')}
                      </span>
                      <span className="block text-[11px] text-gray-500">{s.plain}</span>
                    </td>
                    <td className="py-2 text-right font-mono text-gray-200">{num(s.cagr_pct)}%</td>
                    <td className="py-2 text-right font-mono text-gray-400">{num(s.volatility_pct)}%</td>
                    <td className="py-2 text-right font-mono text-gray-300">{num(s.sharpe, 3)}</td>
                    <td className="py-2 text-right font-mono text-red-400">{num(s.max_drawdown_pct)}%</td>
                    <td className={`py-2 text-right font-mono ${VS[s.vs_benchmark] || 'text-gray-400'}`}>
                      {s.excess_vs_benchmark_pct > 0 ? '+' : ''}{num(s.excess_vs_benchmark_pct)}
                      <span className="block text-[10px]">{s.vs_benchmark}</span>
                    </td>
                  </tr>
                ))}
                {d.benchmark && (
                  <tr className="border-t border-gray-700">
                    <td className="py-2 text-gray-500">{d.benchmark.name}</td>
                    <td className="py-2 text-right font-mono text-gray-500">
                      {num(d.benchmark.cagr_pct)}%
                    </td>
                    <td colSpan={4}></td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Matching the index is not beating it, and the difference is one
              rounding decision wide. */}
          <p className="text-[11px] text-gray-500 leading-relaxed">{d.why_matched}</p>

          <p className="text-xs text-amber-200/85 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
            {d.no_winner_named}
          </p>

          <div>
            <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
              Cannot be backtested
            </p>
            <div className="space-y-1.5">
              {d.cannot_backtest.map(b => (
                <div key={b.factor} className="text-[11px]">
                  <span className="capitalize text-gray-300">{b.factor.replace(/_/g, ' ')}</span>
                  <span className="text-gray-600"> — {b.plain}</span>
                  <span className="block text-gray-500 leading-relaxed">{b.why}</span>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-gray-500 mt-2 leading-relaxed">{d.why_only_two}</p>
          </div>

          <p className="text-[10px] text-gray-600 leading-relaxed">{d.limits}</p>
        </>
      )}
    </div>
  )
}
