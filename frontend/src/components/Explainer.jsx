/**
 * Explainer — a friendly "what just happened, in plain English" box.
 * Use after a tool's result to make complex output beginner-readable.
 *
 *   <Explainer title="What this means">
 *     <p>...plain english...</p>
 *   </Explainer>
 */
export default function Explainer({ title = 'What this means', children }) {
  return (
    <div className="mt-3 rounded-xl border border-blue-800/40 bg-blue-900/15 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-blue-300 mb-2">
        <span>💡</span> {title}
      </p>
      <div className="text-sm text-gray-300 leading-relaxed space-y-2">
        {children}
      </div>
    </div>
  )
}
