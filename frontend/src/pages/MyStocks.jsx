import TabShell from '../components/TabShell'
import Portfolio from './Portfolio'
import Watchlist from './Watchlist'

const TABS = [
  { label: 'Holdings',  Component: Portfolio },
  { label: 'Watchlist', Component: Watchlist },
]

export default function MyStocks() {
  return <TabShell tabs={TABS} persistKey="mystocks.active" />
}
