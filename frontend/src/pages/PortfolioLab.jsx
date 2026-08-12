import TabShell from '../components/TabShell'
import Optimizer from './Optimizer'
import MonteCarlo from './MonteCarlo'
import PortfolioTest from './PortfolioTest'

/**
 * Portfolio Lab — the core loop: build a portfolio, see what it could do,
 * change it. Risk and Backtest moved to the Advanced Centre; they are
 * analysis of a portfolio you already have, not steps in building one.
 */
const TABS = [
  { label: 'Optimize', Component: Optimizer },
  { label: 'Simulate', Component: MonteCarlo },
  { label: 'Portfolio Test', Component: PortfolioTest },
]

export default function PortfolioLab() {
  return <TabShell tabs={TABS} persistKey="lab.active" />
}
