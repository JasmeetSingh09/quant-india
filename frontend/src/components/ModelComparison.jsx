import { useMutation } from '@tanstack/react-query'
import { compareModels } from '../api'
import Spinner from './Spinner'

/**
 * ModelComparison — four-factor, six-factor and portfolio-aware, on what can
 * actually be measured.
 *
 * The obvious version of this table has a return column. This one cannot, and
 * the reason is the point. Both alpha models read current fundamentals, so
 * ranking a past universe by them would use information published years later.
 * A blank performance column would suggest the number exists and is merely
 * missing; a filled one would be fabrication. So it is absent and the absence
 * is explained in the cell where it would have been.
 *
 * What is left is agreement: how much the extra two factors change the answer.
 * Two unvalidated models agreeing are not more likely to be right — they are
 * more likely to share an assumption.
 */
const SAMPLE = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ITC.NS', 'SUNPHARMA.NS']

const STATUS_CLS = {
  'VALIDATED': 'text-green-400 border-green-800/60 bg-green-950/20',
  'NOT VALIDATED': 'text-yellow-300 border-yellow-800/60 bg-yellow-950/20',
  'INSUFFICIENT DATA': 'text-gray-400 border-gray-700 bg-gray-900/40',
  'EXPERIMENTAL': 'text-blue-300 border-blue-900/60 bg-blue-950/20',
}

export default function ModelComparison() {
  const run = useMutation({ mutationFn: () => compareModels({ tickers: SAMPLE }) })
  const d = run.data

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">Model comparison</h2>
        <span className="text-[11px] text-gray-500">
          four-factor · six-factor · portfolio-aware
        </span>
      </div>

      {!d && (
        <>
          <p className="text-xs text-gray-400 leading-relaxed">
            Scores both alpha models on the same stocks at the same moment and
            reports how often they reach the same call.
          </p>
          <button onClick={() => run.mutate()} disabled={run.isPending}
                  className="btn-ghost text-xs">
            {run.isPending ? 'Scoring…' : 'Compare the models'}
          </button>
        </>
      )}

      {run.isPending && <Spinner size="sm" />}
      {run.isError && <p className="banner-error text-xs">{String(run.error)}</p>}

      {d && (
        <>
          <div className="table-wrap">
            <table className="w-full text-sm min-w-[34rem]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="text-left py-1">Model</th>
                  <th className="text-right py-1">Factors</th>
                  <th className="text-left py-1 pl-3">Evidence</th>
                  <th className="text-left py-1 pl-3">Return / Sharpe</th>
                </tr>
              </thead>
              <tbody>
                {d.models.map(m => (
                  <tr key={m.key} className="border-t border-gray-800 align-top">
                    <td className="py-2">
                      <span className="text-gray-200">{m.name}</span>
                      <span className="block text-[11px] text-gray-500">{m.where}</span>
                    </td>
                    <td className="py-2 text-right font-mono text-gray-400">{m.n_factors}</td>
                    <td className="py-2 pl-3">
                      <span className={`text-[11px] px-1.5 py-0.5 rounded border ${
                        STATUS_CLS[m.evidence_status] || STATUS_CLS['INSUFFICIENT DATA']}`}>
                        {m.evidence_status}
                      </span>
                      <span className="block text-[11px] text-gray-500 mt-1 max-w-sm leading-relaxed">
                        {m.evidence_note}
                      </span>
                    </td>
                    <td className="py-2 pl-3 text-[11px] text-gray-500 max-w-xs leading-relaxed">
                      {m.metrics_absent_because}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card-sm">
            <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">Agreement</p>
            <p className="text-sm font-mono text-gray-200">
              {d.agreement.same_call_pct}%
              <span className="text-xs text-gray-500 font-sans ml-2">
                ({d.agreement.n_same} of {d.agreement.n_compared} same call
                {d.agreement.opposite_calls > 0
                  ? `, ${d.agreement.opposite_calls} opposite`
                  : ''})
              </span>
            </p>
            <p className="text-[11px] text-gray-500 mt-1 leading-relaxed">
              {d.agreement.methodology}
            </p>
            <p className="text-[11px] text-gray-400 mt-1 leading-relaxed">
              {d.agreement.means}
            </p>
          </div>

          <div className="table-wrap">
            <table className="w-full text-xs min-w-[26rem]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="text-left py-1">Stock</th>
                  <th className="text-right py-1">4-factor</th>
                  <th className="text-right py-1">6-factor</th>
                  <th className="text-right py-1">Gap</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {d.sample.rows.map(r => (
                  <tr key={r.ticker} className="border-t border-gray-800">
                    <td className="py-1 font-sans">{r.ticker.replace('.NS', '')}</td>
                    <td className="py-1 text-right text-gray-400">
                      {r.v1_score} <span className="text-[10px]">{r.v1_call}</span>
                    </td>
                    <td className="py-1 text-right text-gray-300">
                      {r.v2_score} <span className="text-[10px]">{r.v2_call}</span>
                    </td>
                    <td className={`py-1 text-right ${
                      Math.abs(r.gap ?? 0) > 10 ? 'text-yellow-400' : 'text-gray-500'}`}>
                      {r.gap > 0 ? '+' : ''}{r.gap}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[11px] text-amber-200/80 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
            {d.no_performance_columns}
          </p>
        </>
      )}
    </div>
  )
}
