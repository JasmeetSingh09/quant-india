export default function Spinner({ size = 'md' }) {
  const s = { sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' }[size]
  return (
    <div className="flex items-center justify-center py-12">
      <div className={`${s} border-2 border-green-500 border-t-transparent rounded-full animate-spin`} />
    </div>
  )
}
