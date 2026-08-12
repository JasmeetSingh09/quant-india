import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Menu, Zap } from 'lucide-react'
import Sidebar from './components/Sidebar'
import useMediaQuery from './hooks/useMediaQuery'
import usePersistentState from './usePersistentState'
import Dashboard from './pages/Dashboard'
import StockExplorer from './pages/StockExplorer'
import Calculators from './pages/Calculators'
import Simulator from './pages/Simulator'
import MyStocks from './pages/MyStocks'
import PortfolioLab from './pages/PortfolioLab'
import Markets from './pages/Markets'
import Advanced from './pages/Advanced'
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
  const isMobile = useMediaQuery('(max-width: 1023px)')
  const [drawerOpen, setDrawerOpen] = useState(false)
  // Desktop collapse is a preference, so it survives reloads. The mobile drawer
  // deliberately does not — a phone should always open on the content.
  const [collapsed, setCollapsed] = usePersistentState('ui.sidebarCollapsed', false)
  const location = useLocation()

  // Close the drawer on navigation, and whenever we grow past the mobile
  // breakpoint (otherwise it stays mounted-open behind the desktop layout).
  useEffect(() => { setDrawerOpen(false) }, [location.pathname])
  useEffect(() => { if (!isMobile) setDrawerOpen(false) }, [isMobile])

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
    <div className="flex h-[100dvh] overflow-hidden bg-gray-950">
      <Sidebar
        isMobile={isMobile}
        open={drawerOpen}
        collapsed={collapsed}
        onClose={() => setDrawerOpen(false)}
        onToggleCollapse={() => setCollapsed(c => !c)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar — the only way to reach nav on a phone */}
        {isMobile && (
          <header className="flex items-center gap-3 px-4 h-14 shrink-0 border-b border-gray-800 bg-gray-900/90 backdrop-blur-sm pt-[env(safe-area-inset-top)]">
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              aria-expanded={drawerOpen}
              className="-ml-2 p-2 rounded-lg text-gray-300 hover:text-white hover:bg-gray-800 transition-colors"
            >
              <Menu size={20} />
            </button>
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-6 h-6 shrink-0 bg-gradient-to-br from-green-400 to-emerald-600 rounded-md flex items-center justify-center">
                <Zap size={12} className="text-white" />
              </div>
              <span className="font-bold text-sm text-white tracking-tight truncate">Quant India</span>
            </div>
          </header>
        )}

        <main className="flex-1 overflow-y-auto overflow-x-hidden">
        <Routes>
          <Route path="/"            element={<Dashboard />} />
          <Route path="/stock"       element={<StockExplorer />} />
          <Route path="/top-picks"   element={<Navigate to="/" replace />} />
          <Route path="/screener"    element={<Navigate to="/stock" replace />} />
          <Route path="/my-stocks"   element={<MyStocks />} />
          <Route path="/simulator"   element={<Simulator />} />
          <Route path="/lab"         element={<PortfolioLab />} />
          <Route path="/advanced"    element={<Advanced />} />
          <Route path="/markets"     element={<Markets />} />
          <Route path="/calculators" element={<Calculators />} />

          {/* Options Lab and Research now live inside the Advanced Centre.
              Keep the old paths working — they are bookmarked and linked. */}
          <Route path="/options"     element={<Navigate to="/advanced" replace />} />
          <Route path="/research"    element={<Navigate to="/advanced" replace />} />

          {/* Once signed in, /login and the landing page no longer exist in this
              route table. Without these the browser sits on /login after a
              successful sign-in, falls through to "*", and flashes the 404 page
              before anything navigates away. Send them to the dashboard. */}
          <Route path="/login"       element={<Navigate to="/" replace />} />
          <Route path="/signup"      element={<Navigate to="/" replace />} />

          {/* Redirects for old routes */}
          <Route path="/portfolio"   element={<Navigate to="/my-stocks" replace />} />
          <Route path="/watchlist"   element={<Navigate to="/my-stocks" replace />} />
          <Route path="/optimizer"   element={<Navigate to="/lab" replace />} />
          <Route path="/montecarlo"  element={<Navigate to="/lab" replace />} />
          <Route path="/risk"        element={<Navigate to="/advanced" replace />} />
          <Route path="/factors"     element={<Navigate to="/advanced" replace />} />
          <Route path="/pairs"       element={<Navigate to="/advanced" replace />} />
          <Route path="/commodities" element={<Navigate to="/markets" replace />} />
          <Route path="/news"        element={<Navigate to="/markets" replace />} />
          <Route path="*"            element={<NotFound />} />
        </Routes>
        </main>
      </div>
    </div>
  )
}
