import TabShell from '../components/TabShell'
import Research from './Research'
import Factors from './Factors'
import PairsTrading from './PairsTrading'
import Seasonality from './Seasonality'

const TABS = [
  { label: 'Signals', Component: Research },
  { label: 'Factors', Component: Factors },
  { label: 'Pairs',   Component: PairsTrading },
  { label: 'Seasonality', Component: Seasonality },
]

export default function QuantResearch() {
  return <TabShell tabs={TABS} persistKey="research.active" />
}
