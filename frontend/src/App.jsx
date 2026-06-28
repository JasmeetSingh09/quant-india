import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import StockExplorer from './pages/StockExplorer'
import Screener from './pages/Screener'
import Portfolio from './pages/Portfolio'
import Calculators from './pages/Calculators'
import Watchlist from './pages/Watchlist'
import Simulator from './pages/Simulator'
import Optimizer from './pages/Optimizer'
import Commodities from './pages/Commodities'
import Research from './pages/Research'
import MonteCarlo from './pages/MonteCarlo'
import PairsTrading from './pages/PairsTrading'
import Factors from './pages/Factors'
import News from './pages/News'

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-950">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/"           element={<Dashboard />} />
          <Route path="/stock"      element={<StockExplorer />} />
          <Route path="/screener"   element={<Screener />} />
          <Route path="/portfolio"  element={<Portfolio />} />
          <Route path="/calculators" element={<Calculators />} />
          <Route path="/watchlist"  element={<Watchlist />} />
          <Route path="/simulator"  element={<Simulator />} />
          <Route path="/optimizer"  element={<Optimizer />} />
          <Route path="/commodities"element={<Commodities />} />
          <Route path="/research"   element={<Research />} />
          <Route path="/montecarlo" element={<MonteCarlo />} />
          <Route path="/pairs"      element={<PairsTrading />} />
          <Route path="/factors"    element={<Factors />} />
          <Route path="/news"       element={<News />} />
        </Routes>
      </main>
    </div>
  )
}
