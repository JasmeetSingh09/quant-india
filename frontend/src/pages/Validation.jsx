import FactorEvidence from '../components/FactorEvidence'
import WalkForward from '../components/WalkForward'
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
      <ErrorBoundary name="walk-forward test"><WalkForward /></ErrorBoundary>
    </div>
  )
}
