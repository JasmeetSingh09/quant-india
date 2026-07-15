import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import StockExplorer from './pages/StockExplorer'
import Calculators from './pages/Calculators'
import Simulator from './pages/Simulator'
import MyStocks from './pages/MyStocks'
import PortfolioLab from './pages/PortfolioLab'
import QuantResearch from './pages/QuantResearch'
import Markets from './pages/Markets'
import OptionsLab from './pages/OptionsLab'
import Login from './pages/Login'
import Landing from './pages/Landing'
import { useAuth } from './AuthContext'

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center p-8">
      <p className="text-5xl font-bold text-gray-700">404</p>
      <p className="text-gray-400">Page not found.</p>
      <a href="/" className="btn-primary text-sm">Go to Dashboard</a>
    </div>
  )
}

export default function App() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-950 text-gray-400">
        Loading…
      </div>
    )
  }

  // Anonymous visitors get the public, crawlable landing page (+ the login
  // route). The actual app tools stay gated — you must sign in to reach them.
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*"      element={<Landing />} />
      </Routes>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gray-950">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/"            element={<Dashboard />} />
          <Route path="/stock"       element={<StockExplorer />} />
          <Route path="/top-picks"   element={<Navigate to="/" replace />} />
          <Route path="/screener"    element={<Navigate to="/stock" replace />} />
          <Route path="/my-stocks"   element={<MyStocks />} />
          <Route path="/simulator"   element={<Simulator />} />
          <Route path="/lab"         element={<PortfolioLab />} />
          <Route path="/research"    element={<QuantResearch />} />
          <Route path="/markets"     element={<Markets />} />
          <Route path="/options"     element={<OptionsLab />} />
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
          <Route path="*"            element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}
