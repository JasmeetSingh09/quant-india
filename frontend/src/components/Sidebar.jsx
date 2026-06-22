import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Search, Star, PlayCircle,
  TrendingUp, BarChart3, FlaskConical, Newspaper,
  Dices, GitCompareArrows, Layers, Zap
} from 'lucide-react'

const links = [
  { to: '/',            icon: LayoutDashboard, label: 'Dashboard'  },
  { to: '/stock',       icon: Search,          label: 'Stocks'     },
  { to: '/watchlist',   icon: Star,            label: 'Watchlist'  },
  { to: '/simulator',   icon: PlayCircle,      label: 'Simulator'  },
  { to: '/optimizer',   icon: TrendingUp,      label: 'Optimizer'  },
  { to: '/montecarlo',  icon: Dices,           label: 'Monte Carlo'},
  { to: '/pairs',       icon: GitCompareArrows,label: 'Pairs Trade'},
  { to: '/factors',     icon: Layers,          label: 'Factors'    },
  { to: '/commodities', icon: BarChart3,       label: 'Commodities'},
  { to: '/research',    icon: FlaskConical,    label: 'Research'   },
  { to: '/news',        icon: Newspaper,       label: 'News'       },
]

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-green-500 rounded-lg flex items-center justify-center">
            <Zap size={14} className="text-white" />
          </div>
          <div>
            <p className="font-bold text-sm text-white">Quant India</p>
            <p className="text-xs text-gray-500">NSE Intelligence</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-green-600/20 text-green-400 border border-green-600/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-gray-800">
        <p className="text-xs text-gray-600">Data via NSE · NewsAPI</p>
        <p className="text-xs text-gray-600 mt-0.5">Not financial advice</p>
      </div>
    </aside>
  )
}
