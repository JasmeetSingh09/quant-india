import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import StockExplorer from './pages/StockExplorer'
import Screener from './pages/Screener'
import Calculators from './pages/Calculators'
import Simulator from './pages/Simulator'
import MyStocks from './pages/MyStocks'
import PortfolioLab from './pages/PortfolioLab'
import QuantResearch from './pages/QuantResearch'
import Markets from './pages/Markets'

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-950">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/"            element={<Dashboard />} />
          <Route path="/stock"       element={<StockExplorer />} />
          <Route path="/top-picks"   element={<Navigate to="/" replace />} />
          <Route path="/screener"    element={<Screener />} />
          <Route path="/my-stocks"   element={<MyStocks />} />
          <Route path="/simulator"   element={<Simulator />} />
          <Route path="/lab"         element={<PortfolioLab />} />
          <Route path="/research"    element={<QuantResearch />} />
          <Route path="/markets"     element={<Markets />} />
          <Route path="/calculators" element={<Calculators />} />

          {/* Redirects for old routes */}
          <Route path="/portfolio"   element={<Navigate to="/my-stocks" replace />} />
          <Route path="/watchlist"   element={<Navigate to="/my-stocks" replace />} />
          <Route path="/optimizer"   element={<Navigate to="/lab" replace />} />
          <Route path="/montecarlo"  element={<Navigate to="/lab" replace />} />
          <Route path="/risk"        element={<Navigate to="/lab" replace />} />
          <Route path="/factors"     element={<Navigate to="/research" replace />} />
          <Route path="/pairs"       element={<Navigate to="/research" replace />} />
          <Route path="/commodities" element={<Navigate to="/markets" replace />} />
          <Route path="/news"        element={<Navigate to="/markets" replace />} />
        </Routes>
      </main>
    </div>
  )
}
