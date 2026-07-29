export default function PageHeader({ title, subtitle, children }) {
  return (
    // Stacks on phones (actions drop below the title) and goes side-by-side
    // from `sm` up. min-w-0 lets long titles wrap instead of pushing the
    // action buttons off-screen.
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-5 sm:mb-6">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-bold text-white">{title}</h1>
        {subtitle && <p className="text-sm text-gray-400 mt-1">{subtitle}</p>}
      </div>
      {children && (
        <div className="flex flex-wrap items-center gap-2 sm:shrink-0">{children}</div>
      )}
    </div>
  )
}
