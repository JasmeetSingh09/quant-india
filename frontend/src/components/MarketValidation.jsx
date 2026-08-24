import { useMutation } from '@tanstack/react-query'
import { getMarketValidation } from '../api'
import Spinner from './Spinner'

/**
 * MarketValidation — three sample sizes, not one.
 *
 * The number a track record wants to show is the row count, because it is the
 * biggest. This page shows it first and then takes it apart: how many windows
 * genuinely do not overlap, and how many of those survive the fact that thirty
 * stocks on one day mostly measure the same market move.
 *
 * Underneath, the breakdowns exist because an aggregate cannot distinguish "the
 * model works" from "the model works in large-cap IT and there are a lot of
 * large-cap IT observations". Those are different findings.
 *
 * The verdict is a checklist rather than a score. A number like 94/100 would
 * hide the trade-offs and invite tuning until it looked good; every line here
 * can be checked against the tables above it.
 */
const VERDICT_CLS = {
  'INSUFFICIENT EVIDENCE': 'border-gray-700 bg-gray-900/50 text-gray-300',
  'PRELIMINARY': 'border-yellow-800/70 bg-yellow-950/20 text-yellow-200',
  'PROMISING': 'border-blue-800/70 bg-blue-950/25 text-blue-200',
  'ROBUST OUT-OF-SAMPLE EVIDENCE': 'border-green-800/70 bg-green-950/25 text-green-200',
}

const pct = v => v == null ? '—' : `${Number(v).toFixed(1)}%`
const num = (v, d = 2) => v == null ? '—' : Number(v).toFixed(d)

function Rows({ title, rows, floor }) {
  const shown = (rows || []).filter(r => r.n_independent > 0)
  if (!shown.length) return null
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">{title}</p>
      <div className="table-wrap">
        <table className="w-full text-xs min-w-[30rem]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-gray-600">
              <th className="text-left py-1">Group</th>
              <th className="text-right py-1">Independent</th>
              <th className="text-right py-1">Hit rate</th>
              <th className="text-right py-1">95% interval</th>
              <th className="text-right py-1">Avg excess</th>
              <th className="text-right py-1">p</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {shown.map(r => (
              <tr key={r.group} className="border-t border-gray-800">
                <td className="py-1 font-sans">
                  {r.group}
                  {r.insufficient &&
                    <span className="text-[10px] text-gray-600 ml-1">thin</span>}
                </td>
                <td className="py-1 text-right text-gray-400">{r.n_independent}</td>
                <td className={`py-1 text-right ${
                  r.insufficient ? 'text-gray-500' : 'text-gray-200'}`}>
                  {pct(r.hit_rate_pct)}
                </td>
                <td className="py-1 text-right text-gray-500">
                  {r.hit_ci_95 ? `${r.hit_ci_95[0]}–${r.hit_ci_95[1]}` : '—'}
                </td>
                <td className={`py-1 text-right ${
                  (r.avg_excess_pct ?? 0) > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {num(r.avg_excess_pct, 2)}
                </td>
                <td className="py-1 text-right text-gray-500">{num(r.p_value, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown.some(r => r.insufficient) && (
        <p className="text-[10px] text-gray-600 mt-1">
          Rows marked thin have fewer than {floor} independent observations. They
          are shown rather than hidden, but a hit rate off a handful of windows
          is not a finding.
        </p>
      )}
    </div>
  )
}

export default function MarketValidation() {
  const run = useMutation({ mutationFn: () => getMarketValidation(21) })
  const d = run.data

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">Market-wide validation</h2>
        <span className="text-[11px] text-gray-500">forward-graded · no look-ahead</span>
      </div>

      {!d && (
        <>
          <p className="text-xs text-gray-400 leading-relaxed">
            Grades every logged prediction against what actually happened, then
            splits the result by market-cap, sector and signal strength. Reports
            raw, independent and effective sample sizes separately.
          </p>
          <button onClick={() => run.mutate()} disabled={run.isPending}
                  className="btn-ghost text-xs">
            {run.isPending ? 'Grading…' : 'Run market-wide validation'}
          </button>
        </>
      )}

      {run.isPending && <Spinner size="sm" />}
      {run.isError && <p className="banner-error text-xs">{String(run.error)}</p>}

      {d && d.available === false && (
        <p className="text-xs text-gray-400 leading-relaxed">{d.reason}</p>
      )}

      {d && d.available && (
        <>
          <div className={`p-3 rounded-lg border ${
            VERDICT_CLS[d.verdict.label] || VERDICT_CLS['INSUFFICIENT EVIDENCE']}`}>
            <p className="text-[11px] uppercase tracking-wide text-gray-500">Verdict</p>
            <p className="text-base font-semibold">{d.verdict.label}</p>
            <p className="text-xs mt-1 leading-relaxed opacity-90">{d.verdict.means}</p>
          </div>

          {/* The three numbers, and why they are not the same number. */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[['Raw observations', d.sample.raw_observations],
              ['Independent windows', d.sample.independent_windows],
              ['Effective sample', d.sample.effective_sample_size],
              ['Unique stocks', d.sample.unique_stocks]].map(([label, v]) => (
              <div key={label} className="card-sm">
                <p className="text-[11px] text-gray-500">{label}</p>
                <p className="text-sm font-mono text-gray-200">{v}</p>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-gray-400 leading-relaxed">
            {d.sample.why_these_differ}
          </p>
          {d.sample.design_effect?.rho != null && (
            <p className="text-[10px] text-gray-600 leading-relaxed">
              Design effect {d.sample.design_effect.deff} from an intra-date
              correlation of {d.sample.design_effect.rho} across{' '}
              {d.sample.design_effect.n_clusters} dates. {d.sample.design_effect.note}
            </p>
          )}

          <Rows title="By market cap" rows={d.by_market_cap}
                floor={d.coverage.per_stratum_floor} />
          <Rows title="By sector" rows={d.by_sector}
                floor={d.coverage.per_stratum_floor} />
          <Rows title="By signal strength" rows={d.by_signal_bucket}
                floor={d.coverage.per_stratum_floor} />

          {/* The question the aggregate cannot answer. */}
          <div className="card-sm">
            <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
              Does a stronger score mean a better outcome?
            </p>
            <p className={`text-xs leading-relaxed ${
              d.monotonicity.testable
                ? (d.monotonicity.monotonic ? 'text-green-300' : 'text-yellow-200')
                : 'text-gray-500'}`}>
              {d.monotonicity.verdict || d.monotonicity.reason}
            </p>
          </div>

          <div>
            <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
              Evidence checklist
            </p>
            <div className="space-y-1">
              {d.checklist.map(c => (
                <div key={c.criterion} className="flex items-start gap-2 text-xs">
                  <span className={c.passed ? 'text-green-400' : 'text-gray-600'}>
                    {c.passed ? '✓' : '✗'}
                  </span>
                  <span className="w-40 shrink-0 text-gray-300">{c.criterion}</span>
                  <span className="text-gray-500 leading-relaxed">{c.detail}</span>
                </div>
              ))}
            </div>
          </div>

          <p className="text-[11px] text-amber-200/80 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
            {d.limits}
          </p>
        </>
      )}
    </div>
  )
}
