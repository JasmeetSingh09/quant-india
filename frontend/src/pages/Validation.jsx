import FactorEvidence from '../components/FactorEvidence'
import MarketValidation from '../components/MarketValidation'
import WalkForward from '../components/WalkForward'
import FactorStrategies from '../components/FactorStrategies'
import UniverseSensitivity from '../components/UniverseSensitivity'
import ModelComparison from '../components/ModelComparison'
import ErrorBoundary from '../components/ErrorBoundary'

// The deeper tests start folded (16 Nov 2026 review: the tab opened as a wall
// of technical panels). Each title is the plain question the panel answers.
// Folded panels still mount, so their data is ready when opened.
function Fold({ title, sub, children }) {
  return (
    <details className="group rounded-xl border border-gray-800 bg-gray-900/40">
      <summary className="flex items-center justify-between gap-3 px-4 py-3 cursor-pointer select-none list-none">
        <span>
          <span className="block text-sm font-medium text-gray-200">{title}</span>
          <span className="block text-[11px] text-gray-500">{sub}</span>
        </span>
        <span className="text-gray-500 text-xs shrink-0 group-open:rotate-90 transition-transform">▸</span>
      </summary>
      <div className="px-2 pb-2">{children}</div>
    </details>
  )
}

/**
 * Validation — the evidence overview first, then the one deep test.
 *
 * The order is the argument. The table says what is known about all six
 * factors, including that most of the model's weight cannot be tested on the
 * data that exists; the walk-forward panel below it is the detail on momentum.
 * Opening with the deep test alone was what let five silent factors read as
 * though they had passed something.
 *
 * Two of the six — momentum and low_risk — are reconstructible from stored
 * prices and are tested point-in-time. The other four need fundamentals as
 * filed and news as published, and are marked untestable rather than
 * approximated from today's values.
 */
export default function Validation() {
  return (
    <div className="p-4 sm:p-6 space-y-4 max-w-5xl mx-auto">
      <ErrorBoundary name="factor evidence"><FactorEvidence /></ErrorBoundary>
      {/* Directly under the evidence table, because it is the same question
          asked of the live record rather than of the backtests: does this work
          across the market, or only where we happened to look. */}
      <h2 className="pt-2 text-xs font-semibold uppercase tracking-wider text-gray-500">The tests behind it</h2>
      {/* Directly under the evidence table, because it is the same question
          asked of the live record rather than of the backtests: does this work
          across the market, or only where we happened to look. */}
      <Fold title="Does it hold across the whole market?" sub="Market-wide validation · the live record, graded forward">
        <ErrorBoundary name="market-wide validation"><MarketValidation /></ErrorBoundary>
      </Fold>
      <Fold title="Does momentum work on years it never saw?" sub="Walk-forward test · out of sample">
        <ErrorBoundary name="walk-forward test"><WalkForward /></ErrorBoundary>
      </Fold>
      {/* After the table that says which six exist and the test that says what
          happened to the one: two factors actually traded as strategies. */}
      <Fold title="What if you had traded the factors?" sub="Factor strategies · trading costs included">
        <ErrorBoundary name="factor strategies"><FactorStrategies /></ErrorBoundary>
      </Fold>
      {/* The question the strategies' numbers raise: how much of that came from
          the configuration rather than the factor. */}
      <Fold title="How much depends on which stocks are included?" sub="Universe sensitivity · same strategy, same years">
        <ErrorBoundary name="universe sensitivity"><UniverseSensitivity /></ErrorBoundary>
      </Fold>
      <Fold title="Four factors or six: how do the models compare?" sub="Model comparison">
        <ErrorBoundary name="model comparison"><ModelComparison /></ErrorBoundary>
      </Fold>
    </div>
  )
}
