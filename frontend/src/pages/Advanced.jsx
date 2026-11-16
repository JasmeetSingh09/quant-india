import TabShell from '../components/TabShell'
import usePersistentState from '../usePersistentState'
import OptionsLab from './OptionsLab'
import RiskLab from './RiskLab'
import Factors from './Factors'
import PairsTrading from './PairsTrading'
import Seasonality from './Seasonality'
import Research from './Research'
import Backtest from './Backtest'
import Validation from './Validation'
import StrategyCompare from '../components/StrategyCompare'
import CorrelationOverTime from '../components/CorrelationOverTime'

/**
 * Advanced Centre — the quantitative tools, gathered in one place.
 *
 * These are kept OFF the beginner path deliberately. A new investor's job is
 * pick stocks -> build a portfolio -> simulate it -> change the weights, and
 * every extra nav item competes with that. Nothing here is removed or watered
 * down; it is one click away for anyone who wants it, and out of the way for
 * everyone who doesn't.
 *
 * Three groups, each a plain question, instead of ten tabs in one row
 * (16 Nov 2026 review: ten technical tab names read as a wall). Every tool is
 * still one click from its group.
 */
const GROUPS = [
  {
    label: 'Does the model work?',
    // Validation first on purpose. Whether the model works is a more important
    // question than anything else these tools can compute, and burying it at
    // the end would say the opposite. 'Which method should build this?' is a
    // validation question too, so Methods sits beside it.
    tabs: [
      { label: 'Validation', Component: Validation },
      { label: 'Methods',    Component: StrategyCompare },
      { label: 'Signals',    Component: Research },
      { label: 'Backtest',   Component: Backtest },
    ],
  },
  {
    label: 'Risk & diversification',
    tabs: [
      { label: 'Risk',        Component: RiskLab },
      // Diversification is judged in falling markets, not on average.
      { label: 'Correlation', Component: CorrelationOverTime },
      { label: 'Factors',     Component: Factors },
    ],
  },
  {
    label: 'Market patterns',
    tabs: [
      { label: 'Pairs',       Component: PairsTrading },
      { label: 'Seasonality', Component: Seasonality },
      { label: 'Options',     Component: OptionsLab },
    ],
  },
]

export default function Advanced() {
  const [groupLabel, setGroupLabel] = usePersistentState('adv.group', GROUPS[0].label)
  const group = GROUPS.find(g => g.label === groupLabel) || GROUPS[0]

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 sm:px-6 pt-4 sm:pt-5">
        <div role="tablist" aria-label="Advanced tools"
             className="inline-flex flex-wrap max-w-full gap-1 p-1 rounded-xl bg-gray-900 border border-gray-800">
          {GROUPS.map(g => (
            <button key={g.label} role="tab" aria-selected={g.label === group.label}
              onClick={() => setGroupLabel(g.label)}
              className={`shrink-0 whitespace-nowrap px-3 sm:px-4 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                g.label === group.label
                  ? 'bg-green-600 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              }`}>
              {g.label}
            </button>
          ))}
        </div>
      </div>
      {/* Keyed by group so each group keeps its own remembered sub-tab. */}
      <div className="flex-1 min-h-0">
        <TabShell key={group.label} tabs={group.tabs} persistKey={`adv.active.${group.label}`} />
      </div>
    </div>
  )
}
