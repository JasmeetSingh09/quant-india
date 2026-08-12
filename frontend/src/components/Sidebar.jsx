import { useEffect, useRef } from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Search, PlayCircle,
  TrendingUp, BarChart3, FlaskConical,
  Briefcase, Calculator, Zap, LogOut, Sigma, Wand2,
  PanelLeftClose, PanelLeftOpen, X
} from 'lucide-react'
import { useAuth } from '../AuthContext'

const links = [
  { to: '/',            icon: LayoutDashboard, label: 'Dashboard'  },
  { to: '/build',       icon: Wand2,           label: 'Build'      },
  { to: '/stock',       icon: Search,          label: 'Stocks'     },
  { to: '/my-stocks',   icon: Briefcase,       label: 'My Stocks'  },
  { to: '/simulator',   icon: PlayCircle,      label: 'Simulator'  },
  { to: '/lab',         icon: TrendingUp,      label: 'Port. Lab'  }, // intentional abbrev — full label overflows w-56
  { to: '/markets',     icon: BarChart3,       label: 'Markets'    },
  { to: '/calculators', icon: Calculator,      label: 'Calculators'},
]

// Kept visually separate from the main flow. Options Lab and Research used to
// sit in the list above, which put seven-factor regressions and Black-Scholes
// at the same level as "My Stocks" for a first-time user.
const advancedLink = { to: '/advanced', icon: FlaskConical, label: 'Advanced' }

/**
 * Sidebar — one nav, two behaviours.
 *
 *   mobile  (isMobile)  : off-canvas drawer over a scrim; closes on nav, on Esc,
 *                         and on scrim tap. Hidden from the a11y tree when shut.
 *   desktop             : docked column that collapses to a 64px icon rail.
 *
 * Both states are driven by the parent (App) so the mobile top bar and the
 * desktop collapse button share a single source of truth.
 */
export default function Sidebar({ isMobile, open, collapsed, onClose, onToggleCollapse }) {
  const { user, signOut } = useAuth()
  const panelRef = useRef(null)

  // Esc closes the mobile drawer, and we lock body scroll behind it so the
  // page underneath doesn't scroll while the drawer is open.
  useEffect(() => {
    if (!isMobile || !open) return
    const onKey = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [isMobile, open, onClose])

  // Move focus into the drawer when it opens so keyboard/screen-reader users
  // land inside it rather than back at the top of the page.
  useEffect(() => {
    if (isMobile && open) panelRef.current?.focus()
  }, [isMobile, open])

  // Labels are hidden only on the desktop rail — the mobile drawer is always full width.
  const railed = collapsed && !isMobile
  const showLabels = !railed

  const width = isMobile ? 'w-[17rem]' : railed ? 'w-16' : 'w-56'

  const position = isMobile
    ? `fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ease-out
       ${open ? 'translate-x-0' : '-translate-x-full'}`
    : 'relative shrink-0 transition-[width] duration-200 ease-out'

  return (
    <>
      {/* Scrim — mobile only, fades with the drawer */}
      {isMobile && (
        <div
          onClick={onClose}
          aria-hidden="true"
          className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px] transition-opacity duration-200
            ${open ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
        />
      )}

      {/* min-w-0 below is load-bearing: as a flex child the aside defaults to
          min-width:auto (= min-content), which lets the nav labels' intrinsic
          width override `w-16` so the rail never actually narrows. */}
      <aside
        ref={panelRef}
        tabIndex={-1}
        aria-label="Main navigation"
        aria-hidden={isMobile && !open ? 'true' : undefined}
        inert={isMobile && !open ? '' : undefined}
        className={`${width} ${position} min-w-0 bg-gray-900/95 md:bg-gray-900/80 backdrop-blur-sm
          border-r border-gray-800 flex flex-col outline-none
          pb-[env(safe-area-inset-bottom)]`}
      >
        {/* Logo + control */}
        <div className={`flex items-center gap-2.5 border-b border-gray-800 py-5 ${railed ? 'px-3 justify-center' : 'px-5'}`}>
          <div className="w-8 h-8 shrink-0 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center shadow-sm shadow-green-900/50">
            <Zap size={15} className="text-white" />
          </div>
          {showLabels && (
            <div className="min-w-0 flex-1">
              <p className="font-bold text-sm text-white tracking-tight truncate">Quant India</p>
              <p className="text-[11px] text-gray-500 truncate">NSE Intelligence</p>
            </div>
          )}
          {isMobile ? (
            <button
              onClick={onClose}
              aria-label="Close navigation"
              className="shrink-0 p-2 -mr-1 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            >
              <X size={18} />
            </button>
          ) : (
            !railed && (
              <button
                onClick={onToggleCollapse}
                aria-label="Collapse sidebar"
                title="Collapse sidebar"
                className="shrink-0 p-1.5 rounded-lg text-gray-500 hover:text-gray-200 hover:bg-gray-800 transition-colors"
              >
                <PanelLeftClose size={16} />
              </button>
            )
          )}
        </div>

        {/* Expand button gets its own row when railed, so it stays reachable */}
        {railed && (
          <button
            onClick={onToggleCollapse}
            aria-label="Expand sidebar"
            title="Expand sidebar"
            className="mx-auto mt-3 p-2 rounded-lg text-gray-500 hover:text-gray-200 hover:bg-gray-800 transition-colors"
          >
            <PanelLeftOpen size={16} />
          </button>
        )}

        {/* Nav */}
        <nav className={`flex-1 py-4 space-y-0.5 overflow-y-auto overflow-x-hidden ${railed ? 'px-2' : 'px-3'}`}>
          {[...links, null, advancedLink].map(item => item === null ? (
            <div key="sep" className="pt-3 mt-3 border-t border-gray-800/80">
              {showLabels && (
                <p className="px-3 pb-1 text-[10px] uppercase tracking-wider text-gray-600">
                  Advanced
                </p>
              )}
            </div>
          ) : (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={isMobile ? onClose : undefined}
              title={railed ? item.label : undefined}
              className={({ isActive }) =>
                `group relative flex items-center rounded-lg text-sm font-medium transition-all
                 ${railed ? 'justify-center px-0 py-3' : 'gap-3 px-3 py-2.5'}
                 ${isMobile ? 'min-h-[44px]' : ''}
                 ${isActive
                    ? 'bg-green-600/15 text-green-400'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/70'}`
              }
            >
              {({ isActive }) => (
                <>
                  <span className={`absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-green-400 transition-all ${isActive ? 'opacity-100' : 'opacity-0'}`} />
                  <item.icon size={16} className={`shrink-0 ${isActive ? 'text-green-400' : 'text-gray-500 group-hover:text-gray-300'}`} />
                  {showLabels && <span className="truncate">{item.label}</span>}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className={`border-t border-gray-800 py-4 space-y-3 ${railed ? 'px-2' : 'px-5'}`}>
          {user && (
            railed ? (
              <button
                onClick={() => signOut()}
                title={`Sign out (${user.email})`}
                aria-label="Sign out"
                className="mx-auto flex p-2 rounded-lg text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors"
              >
                <LogOut size={14} />
              </button>
            ) : (
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-gray-400 truncate" title={user.email}>{user.email}</span>
                <button
                  onClick={() => signOut()}
                  title="Sign out"
                  aria-label="Sign out"
                  className="shrink-0 p-2 rounded-lg text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors"
                >
                  <LogOut size={14} />
                </button>
              </div>
            )
          )}
          {showLabels && (
            <div>
              <p className="text-[11px] text-gray-600">Data via NSE · NewsAPI</p>
              <p className="text-[11px] text-gray-600 mt-0.5">Not financial advice</p>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
