import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Search, PlayCircle,
  TrendingUp, BarChart3, FlaskConical,
  Briefcase, Calculator, Zap
} from 'lucide-react'

const links = [
  { to: '/',            icon: LayoutDashboard, label: 'Dashboard'  },
  { to: '/stock',       icon: Search,          label: 'Stocks'     },
  { to: '/my-stocks',   icon: Briefcase,       label: 'My Stocks'  },
  { to: '/simulator',   icon: PlayCircle,      label: 'Simulator'  },
  { to: '/lab',         icon: TrendingUp,      label: 'Port. Lab'  },
  { to: '/research',    icon: FlaskConical,    label: 'Research'   },
  { to: '/markets',     icon: BarChart3,       label: 'Markets'    },
  { to: '/calculators', icon: Calculator,      label: 'Calculators'},
]

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 bg-gray-900/80 backdrop-blur-sm border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-gray-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center shadow-sm shadow-green-900/50">
            <Zap size={15} className="text-white" />
          </div>
          <div>
            <p className="font-bold text-sm text-white tracking-tight">Quant India</p>
            <p className="text-[11px] text-gray-500">NSE Intelligence</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive
                  ? 'bg-green-600/15 text-green-400'
                  : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/70'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className={`absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-green-400 transition-all ${isActive ? 'opacity-100' : 'opacity-0'}`} />
                <Icon size={16} className={isActive ? 'text-green-400' : 'text-gray-500 group-hover:text-gray-300'} />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-gray-800">
        <p className="text-[11px] text-gray-600">Data via NSE · NewsAPI</p>
        <p className="text-[11px] text-gray-600 mt-0.5">Not financial advice</p>
      </div>
    </aside>
  )
}
