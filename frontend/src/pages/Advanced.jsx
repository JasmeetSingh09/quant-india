import TabShell from '../components/TabShell'
import OptionsLab from './OptionsLab'
import RiskLab from './RiskLab'
import Factors from './Factors'
import PairsTrading from './PairsTrading'
import Seasonality from './Seasonality'
import Research from './Research'
import Backtest from './Backtest'
import WalkForward from '../components/WalkForward'
import StrategyCompare from '../components/StrategyCompare'

/**
 * Advanced Centre — the quantitative tools, gathered in one place.
 *
 * These are kept OFF the beginner path deliberately. A new investor's job is
 * pick stocks -> build a portfolio -> simulate it -> change the weights, and
 * every extra nav item competes with that. Nothing here is removed or watered
 * down; it is one click away for anyone who wants it, and out of the way for
 * everyone who doesn't.
 */
const TABS = [
  // Validation first on purpose. Whether the model works is a more important
  // question than anything else these tools can compute, and burying it at the
  // end would say the opposite.
  { label: 'Validation',  Component: WalkForward },
  // Next to Validation for the same reason it is first: 'which method
  // should build this?' is a validation question, not a tooling one.
  { label: 'Methods',     Component: StrategyCompare },
  { label: 'Risk',        Component: RiskLab },
  { label: 'Factors',     Component: Factors },
  { label: 'Signals',     Component: Research },
  { label: 'Backtest',    Component: Backtest },
  { label: 'Pairs',       Component: PairsTrading },
  { label: 'Seasonality', Component: Seasonality },
  { label: 'Options',     Component: OptionsLab },
]

export default function Advanced() {
  return <TabShell tabs={TABS} persistKey="adv.active" />
}
