import TabShell from '../components/TabShell'
import Optimizer from './Optimizer'
import MonteCarlo from './MonteCarlo'
import RiskLab from './RiskLab'

const TABS = [
  { label: 'Optimize', Component: Optimizer },
  { label: 'Simulate', Component: MonteCarlo },
  { label: 'Risk',     Component: RiskLab },
]

export default function PortfolioLab() {
  return <TabShell tabs={TABS} persistKey="lab.active" />
}
