import usePersistentState from '../usePersistentState'

/**
 * TabShell — shared tab-page layout used by MyStocks, Markets,
 * PortfolioLab, and QuantResearch.
 *
 * Props:
 *   tabs       — array of { label: string, Component: React.FC }
 *   persistKey — localStorage key; if provided the active tab survives navigation.
 *                Stored as the label string so reordering tabs doesn't break state.
 */
export default function TabShell({ tabs, persistKey }) {
  const defaultLabel = tabs[0]?.label ?? ''
  const [activeLabel, setActiveLabel] = usePersistentState(
    persistKey ?? `__tabshell_${tabs.map(t => t.label).join('_')}`,
    defaultLabel,
  )

  // If a persisted label no longer exists in tabs, fall back to first tab
  const idx = tabs.findIndex(t => t.label === activeLabel)
  const safeIdx = idx >= 0 ? idx : 0
  const { Component } = tabs[safeIdx]

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar — scrolls horizontally on phones rather than wrapping or
          squashing. `scrollbar-none` keeps it clean; it's swipeable by touch. */}
      <div className="flex gap-1 px-4 sm:px-6 pt-4 sm:pt-5 pb-0 border-b border-gray-800 bg-gray-950/80
                      overflow-x-auto scrollbar-none">
        {tabs.map(({ label }) => (
          <button
            key={label}
            onClick={() => setActiveLabel(label)}
            className={`shrink-0 whitespace-nowrap px-3 sm:px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              label === tabs[safeIdx].label
                ? 'bg-gray-900 text-green-400 border border-b-0 border-gray-800 shadow-[0_1px_0_#030712]'
                : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/40'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <Component />
      </div>
    </div>
  )
}
