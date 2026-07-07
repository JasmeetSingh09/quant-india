/**
 * Spinner — sizes: sm (tight, inline), md (card-level), lg (full-page).
 * sm has no surrounding padding so it fits inside compact sections.
 */
export default function Spinner({ size = 'md' }) {
  const ring = { sm: 'w-4 h-4 border-2', md: 'w-7 h-7 border-2', lg: 'w-10 h-10 border-[3px]' }[size] ?? 'w-7 h-7 border-2'
  const pad  = { sm: '', md: 'py-8', lg: 'py-16' }[size] ?? 'py-8'
  return (
    <div className={`flex items-center justify-center ${pad}`}>
      <div className={`${ring} border-green-500 border-t-transparent rounded-full animate-spin`} />
    </div>
  )
}
