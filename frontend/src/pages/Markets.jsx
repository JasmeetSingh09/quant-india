import TabShell from '../components/TabShell'
import Commodities from './Commodities'
import News from './News'

const TABS = [
  { label: 'Commodities', Component: Commodities },
  { label: 'News',        Component: News },
]

export default function Markets() {
  return <TabShell tabs={TABS} persistKey="markets.active" />
}
