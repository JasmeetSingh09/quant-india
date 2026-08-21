import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getMethodology } from '../api'
import { Info, ChevronDown } from 'lucide-react'

/**
 * Methodology — the four questions, on the tool they describe.
 *
 * Collapsed by default. The point is not to bury it: a panel that opens on
 * every page becomes furniture people scroll past, whereas one labelled with
 * the honest question tends to get opened by exactly the readers who should.
 *
 * "What should I not conclude?" is listed last and styled hardest, because it
 * is the answer a user is least likely to reach on their own and the one that
 * stops a number being trusted further than it deserves.
 */
export default function Methodology({ tool }) {
  const [open, setOpen] = useState(false)
  const { data } = useQuery({
    queryKey: ['methodology', tool],
    queryFn: () => getMethodology(tool),
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  })
  if (!data || data.error) return null

  return (
    <div className="border-t border-gray-800 pt-3">
      <button onClick={() => setOpen(o => !o)}
              aria-expanded={open}
              className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors">
        <Info size={13} />
        Method, assumptions, and what this does not tell you
        <ChevronDown size={13} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="mt-3 space-y-3 text-xs leading-relaxed">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">What it calculates</p>
            <p className="text-gray-300">{data.calculates}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">What data it uses</p>
            <p className="text-gray-300">{data.data}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">What it assumes</p>
            <ul className="space-y-1">
              {(data.assumes || []).map((a, i) => (
                <li key={i} className="text-gray-400 pl-3 relative">
                  <span className="absolute left-0 text-gray-600">·</span>{a}
                </li>
              ))}
            </ul>
          </div>
          <div className="border-l-2 border-amber-700/70 pl-2.5">
            <p className="text-[10px] uppercase tracking-widest text-amber-500/90 mb-1">
              What you should not conclude
            </p>
            <p className="text-amber-100/80">{data.do_not_conclude}</p>
          </div>
        </div>
      )}
    </div>
  )
}
