import FactorEvidence from '../components/FactorEvidence'
import MarketValidation from '../components/MarketValidation'
import WalkForward from '../components/WalkForward'
import FactorStrategies from '../components/FactorStrategies'
import UniverseSensitivity from '../components/UniverseSensitivity'
import ModelComparison from '../components/ModelComparison'
import ErrorBoundary from '../components/ErrorBoundary'

/**
 * Validation — the evidence overview first, then the one deep test.
 *
 * The order is the argument. The table says what is known about all six
 * factors, including that most of the model's weight has never been tested;
 * the walk-forward panel below it is the detail on the single factor that
 * could be. Opening with the deep test alone was what let five silent factors
 * read as though they had passed something.
 */
export default function Validation() {
  return (
    <div className="p-4 sm:p-6 space-y-4 max-w-5xl mx-auto">
      <ErrorBoundary name="factor evidence"><FactorEvidence /></ErrorBoundary>
      {/* Directly under the evidence table, because it is the same question
          asked of the live record rather than of the backtests: does this work
          across the market, or only where we happened to look. */}
      <ErrorBoundary name="market-wide validation"><MarketValidation /></ErrorBoundary>
      <ErrorBoundary name="walk-forward test"><WalkForward /></ErrorBoundary>
      {/* Last because it is the heaviest and the most specific: two factors
          actually traded as strategies, after the table that says which six
          exist and the test that says what happened to the one. */}
      <ErrorBoundary name="factor strategies"><FactorStrategies /></ErrorBoundary>
      {/* After the strategies, because it is the question their numbers raise:
          how much of that came from the configuration rather than the factor. */}
      <ErrorBoundary name="universe sensitivity"><UniverseSensitivity /></ErrorBoundary>
      <ErrorBoundary name="model comparison"><ModelComparison /></ErrorBoundary>
    </div>
  )
}
