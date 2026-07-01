import { useState } from 'react'
import Portfolio from './Portfolio'
import Watchlist from './Watchlist'

const TABS = [
  { label: 'Holdings', Component: Portfolio },
  { label: 'Watchlist', Component: Watchlist },
]

export default function MyStocks() {
  const [active, setActive] = useState(0)
  const { Component } = TABS[active]
  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-1 px-6 pt-5 pb-0 border-b border-gray-800 bg-gray-950">
        {TABS.map(({ label }, i) => (
          <button
            key={label}
            onClick={() => setActive(i)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              active === i
                ? 'bg-gray-900 text-green-400 border border-b-0 border-gray-800'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto">
        <Component />
      </div>
    </div>
  )
}
