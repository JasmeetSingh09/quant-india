import { useQuery } from '@tanstack/react-query'
import { getSimulations, getSimulationPnl, getAlphaV2, getPortfolioFit } from '../api'

/**
 * AlphaVsFit — two scores that answer different questions, never blended.
 *
 * Alpha asks "how attractive is this stock?" and is a prediction the track
 * record has not yet supported. Fit asks "does it belong in YOUR portfolio?"
 * and is arithmetic — sector overlap, correlation and concentration are true
 * whether or not the model can forecast anything.
 *
 * They are shown side by side because the interesting case is when they
 * disagree: a stock the model likes, which would make your portfolio worse. A
 * single combined number would hide exactly that.
 *
 * Renders nothing when the user has no portfolio, because fit against nothing
 * is not a question.
 */
export default function AlphaVsFit({ ticker }) {
  const { data: sims } = useQuery({
    queryKey: ['simulations'],
    queryFn: getSimulations,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  const list = Array.isArray(sims) ? sims : (sims?.simulations || [])
  const first = list[0]
  const simName = first?.name || first?.sim_name

  const { data: pnl } = useQuery({
    queryKey: ['simPnl', simName],
    queryFn: () => getSimulationPnl(simName),
    enabled: !!simName,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  const holdings = pnl?.positions?.length
    ? Object.fromEntries(pnl.positions.map(p => [p.ticker, p.allocation_pct ?? 0]))
    : null

  const { data: alpha } = useQuery({
    queryKey: ['alphaV2', ticker],
    queryFn: () => getAlphaV2(ticker),
    staleTime: 15 * 60 * 1000,
    retry: false,
  })

  const { data: fit } = useQuery({
    queryKey: ['fit', ticker, simName],
    queryFn: () => getPortfolioFit({ ticker, holdings, add_pct: 10 }),
    enabled: !!holdings && Object.keys(holdings || {}).length >= 2,
    staleTime: 15 * 60 * 1000,
    retry: false,
  })

  if (!holdings || !alpha || alpha.error) return null
  if (fit?.held) {
    return (
      <div className="card">
        <p className="text-sm text-gray-300">
          You already hold {ticker.replace('.NS', '')} at {fit.current_weight_pct}% of
          <span className="text-gray-500"> {simName}</span>.
        </p>
        <p className="text-xs text-gray-500 mt-1 leading-relaxed">{fit.note}</p>
      </div>
    )
  }
  if (!fit || fit.error || fit.fit_score == null) return null

  // Alpha is -100..+100; fit is 0..100. Shown on their own scales, never averaged.
  const alphaOn100 = Math.round((alpha.alpha_score + 100) / 2)
  const disagrees = (alpha.alpha_score > 15 && fit.fit_score < 50) ||
                    (alpha.alpha_score < -15 && fit.fit_score > 70)

  const tone = v => v >= 70 ? 'text-green-400' : v >= 45 ? 'text-gray-200' : 'text-red-400'

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">Attractive vs. right for you</h2>
        <span className="text-[11px] text-gray-500">against {simName}</span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="card-sm">
          <p className="text-[11px] text-gray-500">Alpha</p>
          <p className="text-lg font-bold text-gray-100">
            {alpha.alpha_score > 0 ? '+' : ''}{alpha.alpha_score}
            <span className="text-xs text-gray-500 font-normal"> / 100</span>
          </p>
          <p className="text-[10px] text-gray-600 leading-snug mt-0.5">
            How attractive the model finds it. Experimental — not validated.
          </p>
        </div>
        <div className="card-sm">
          <p className="text-[11px] text-gray-500">Portfolio fit</p>
          <p className={`text-lg font-bold ${tone(fit.fit_score)}`}>
            {fit.fit_score}<span className="text-xs text-gray-500 font-normal"> / 100</span>
          </p>
          <p className="text-[10px] text-gray-600 leading-snug mt-0.5">
            Whether it belongs in the portfolio you already hold.
          </p>
        </div>
      </div>

      {/* The case worth surfacing: the two scores pointing opposite ways. */}
      {disagrees && (
        <p className="text-xs text-amber-200/90 border-l-2 border-amber-700/70 pl-2.5 leading-relaxed">
          These disagree. A high alpha score does not mean you should buy it —
          {' '}{fit.main_reason}
        </p>
      )}

      <p className="text-xs text-gray-300 leading-relaxed">{fit.verdict}</p>

      <div className="space-y-1">
        {Object.entries(fit.components || {}).map(([k, c]) => c?.score == null ? null : (
          <div key={k} className="flex items-baseline gap-2 text-[11px]">
            <span className="w-24 shrink-0 text-gray-500 capitalize">{k.replace(/_/g, ' ')}</span>
            <span className={`w-10 text-right font-mono shrink-0 ${tone(c.score)}`}>
              {Math.round(c.score)}
            </span>
            <span className="text-gray-500 leading-snug">{c.detail}</span>
          </div>
        ))}
      </div>

      <p className="text-[10px] text-gray-600 leading-relaxed">{fit.means}</p>
    </div>
  )
}
