import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getWalkForward } from '../api'
import Spinner from './Spinner'

/**
 * WalkForward — the out-of-sample test, including when it fails.
 *
 * This is the strongest evidence the project can produce about whether its
 * largest factor works, and on the current data the answer is that it does not.
 * Showing that is the entire value: a validation panel that only appears when
 * the result is flattering is not validation, it is marketing.
 *
 * Loaded on request because it rebuilds several years of rankings.
 */
export default function WalkForward() {
  const [run, setRun] = useState(false)
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['walkForward'],
    queryFn: getWalkForward,
    enabled: run,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">Does momentum actually work?</h2>
        <span className="text-[11px] text-gray-500">Out-of-sample test</span>
      </div>

      {!run && (
        <>
          <p className="text-xs text-gray-400 leading-relaxed">
            Ranks stocks on momentum as it would have looked at each past date,
            holds for a fixed period, then measures what happened next — stepping
            forward so no two test windows overlap. No date ever sees data from
            after itself.
          </p>
          <p className="text-xs text-gray-500 leading-relaxed mt-1.5">
            A null result here means we found no evidence of predictive power in the
            configurations tested. It is not a proof that the factor cannot work.
          </p>
          <button onClick={() => setRun(true)} className="btn-ghost text-xs">
            Run the test
          </button>
        </>
      )}

      {run && isLoading && (
        <div className="flex items-center gap-2">
          <Spinner size="sm" />
          <span className="text-xs text-gray-500">
            Rebuilding several years of rankings — about a minute.
          </span>
        </div>
      )}

      {isError && <p className="banner-error text-xs">{String(error)}</p>}

      {data && !data.error && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[['Windows', data.windows, null],
              ['Mean spread', `${data.mean_spread_pct > 0 ? '+' : ''}${data.mean_spread_pct}%`,
               data.mean_spread_pct > 0],
              ['Win rate', `${data.win_rate_pct}%`, data.win_rate_pct > 55],
              ['Info ratio', data.information_ratio, data.information_ratio > 0.5]]
              .map(([label, val, good]) => (
              <div key={label} className="card-sm">
                <p className="text-[11px] text-gray-500">{label}</p>
                <p className={`text-sm font-mono ${
                  good === null ? 'text-gray-200'
                  : good ? 'text-green-400' : 'text-gray-300'}`}>{val}</p>
              </div>
            ))}
          </div>

          {/* The verdict, at the same weight as the numbers — a reader who scans
              only the figures should not come away more optimistic than the test. */}
          <p className={`text-xs leading-relaxed p-2.5 rounded-lg border ${
            data.significance?.significant_at_5pct
              ? 'border-green-800 bg-green-950/25 text-green-100'
              : 'border-amber-800/70 bg-amber-950/20 text-amber-100/90'}`}>
            {data.verdict}
          </p>

          <div className="text-[11px] text-gray-500 space-y-1">
            <p>
              {data.period} · best window {data.best_window_pct}% · worst {data.worst_window_pct}%
              {data.significance && ` · 95% CI ${data.significance.ci95_low_pct}–${data.significance.ci95_high_pct}%`}
            </p>
            <p className="leading-relaxed"><b className="text-gray-400">Why only momentum:</b> {data.why_only_momentum}</p>
            <p className="leading-relaxed"><b className="text-gray-400">Limits:</b> {data.limits}</p>
          </div>
        </>
      )}
    </div>
  )
}
