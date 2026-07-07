import TabShell from '../components/TabShell'
import Research from './Research'
import Factors from './Factors'
import PairsTrading from './PairsTrading'

const TABS = [
  { label: 'Signals', Component: Research },
  { label: 'Factors', Component: Factors },
  { label: 'Pairs',   Component: PairsTrading },
]

export default function QuantResearch() {
  return <TabShell tabs={TABS} persistKey="research.active" />
}
