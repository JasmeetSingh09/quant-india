/**
 * BlackLitterman — the three steps, shown as three steps.
 *
 * The optimiser was returning the whole chain and the page was rendering only
 * the last link: a set of weights, with the equilibrium they started from, the
 * views that moved them and the posterior they landed on all discarded. That
 * makes Black-Litterman look like any other black box that emits percentages,
 * when the entire reason to prefer it is that you can see where each number
 * came from and how far your opinion was allowed to move it.
 *
 * So: what the market already expects, what we think differs, where that
 * leaves us. With no views the third panel equals the first, and saying so
 * plainly is more useful than hiding the step.
 */
const pct = (v, d = 2) => v == null ? '—' : `${Number(v).toFixed(d)}%`
const short = t => t.replace('.NS', '')

export default function BlackLitterman({ bl }) {
  if (!bl || bl.error) return null

  const eqRet = bl.implied_equilibrium_returns || {}
  const postRet = bl.bl_posterior_returns || {}
  const eqW = bl.equilibrium_weights || {}
  const blW = bl.bl_pct || {}
  const shifts = bl.weight_shifts_pct || {}
  const views = bl.views_injected || {}
  const tickers = bl.tickers || Object.keys(blW)
  const hasViews = Object.keys(views).length > 0

  if (!tickers.length) return null

  return (
    <div className="card space-y-4">
      <div>
        <h3 className="font-semibold text-sm">Where these weights came from</h3>
        <p className="text-xs text-gray-500 mt-0.5">
          {bl.algorithm} · tau {bl.tau} · {bl.period}
        </p>
      </div>

      {/* Step 1 → 2 → 3, named. The numbering is real here: each column is
          computed from the one before it, and the order is the method. */}
      <div className="grid sm:grid-cols-3 gap-2 text-xs">
        {[
          ['1 · Market equilibrium',
           'Reverse-engineered from what the market already holds. No forecast — this is the return that would make current prices sensible.'],
          ['2 · Your views',
           hasViews
             ? `${Object.keys(views).length} view${Object.keys(views).length === 1 ? '' : 's'} from the sentiment factor, each with a confidence that limits how far it can move the answer.`
             : 'None supplied. Nothing overrides the market, so the answer stays at equilibrium.'],
          ['3 · Posterior',
           hasViews
             ? 'The blend. A view only moves the result as far as its confidence justifies.'
             : 'Identical to step 1, because there was nothing to blend in.'],
        ].map(([title, body]) => (
          <div key={title} className="card-sm">
            <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-1">{title}</p>
            <p className="text-[11px] text-gray-500 leading-relaxed">{body}</p>
          </div>
        ))}
      </div>

      <div className="table-wrap">
        <table className="w-full text-sm min-w-[42rem]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-gray-500">
              <th className="text-left py-1">Stock</th>
              <th className="text-right py-1">Market expects</th>
              <th className="text-right py-1">Your view</th>
              <th className="text-right py-1">Confidence</th>
              <th className="text-right py-1">After blending</th>
              <th className="text-right py-1">Market weight</th>
              <th className="text-right py-1">Final weight</th>
              <th className="text-right py-1">Shift</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {tickers.map(t => {
              const v = views[t]
              const sh = shifts[t]
              return (
                <tr key={t} className="border-t border-gray-800">
                  <td className="py-1.5 font-sans">{short(t)}</td>
                  <td className="py-1.5 text-right text-gray-300">{pct(eqRet[t])}</td>
                  <td className={`py-1.5 text-right ${v ? 'text-blue-300' : 'text-gray-600'}`}>
                    {v ? pct(v.expected_excess_pct) : '—'}
                  </td>
                  <td className="py-1.5 text-right text-gray-500">
                    {v ? Number(v.confidence).toFixed(2) : '—'}
                  </td>
                  <td className="py-1.5 text-right text-gray-200">{pct(postRet[t])}</td>
                  <td className="py-1.5 text-right text-gray-500">
                    {eqW[t] == null ? '—' : pct(eqW[t] * 100, 1)}
                  </td>
                  <td className="py-1.5 text-right text-gray-200">{pct(blW[t], 1)}</td>
                  <td className={`py-1.5 text-right ${
                    sh == null ? 'text-gray-600'
                    : sh > 0.05 ? 'text-green-400'
                    : sh < -0.05 ? 'text-red-400' : 'text-gray-500'}`}>
                    {sh == null ? '—' : `${sh > 0 ? '+' : ''}${sh.toFixed(1)} pts`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {!hasViews && (
        <p className="text-xs text-gray-400 border-l-2 border-gray-700 pl-2.5 leading-relaxed">
          No views were injected, so the final weights are the market portfolio.
          That is the method working, not failing: without an opinion there is no
          reason to bet against how everyone else is positioned.
        </p>
      )}

      {bl.interpretation && (
        <p className="text-xs text-gray-300 leading-relaxed">{bl.interpretation}</p>
      )}

      <p className="text-[10px] text-gray-600 leading-relaxed">
        Tau ({bl.tau}) sets how much the equilibrium is trusted against the views —
        smaller means the market has to be more wrong before your opinion moves the
        weights. Equilibrium returns are implied from market capitalisation, not
        forecast, so none of these numbers is a prediction of what a stock will do.
      </p>
    </div>
  )
}
