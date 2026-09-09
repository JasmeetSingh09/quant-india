import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getIntegrityEvidence } from '../api'
import { useEvidence } from './Evidence'

/**
 * EvidencePanel — two questions, kept apart on purpose.
 *
 *   Is the machinery computing what it claims?   answers today, mostly good
 *   Does the signal predict returns?             unresolved, until 2029 at best
 *
 * The evidence layer used to answer only the second. Every factor returns "not
 * established" and will keep doing so for years, so every badge was the same
 * colour on every stock every day. That is not an evidence layer, it is
 * wallpaper — people stop seeing it within a week, and then the amber that
 * actually matters is invisible too.
 *
 * Splitting the axes fixes that without softening anything. The first axis has
 * real greens backed by numbers measured at request time, which proves the
 * badges move; the second stays amber, and because the page is capable of
 * showing green, the amber reads as a finding rather than as decoration.
 *
 * The two must never bleed into one another. "Our arithmetic is reproducible"
 * is not evidence that the signal works, and a panel that let the first imply
 * the second would launder exactly the confusion the evidence layer exists to
 * prevent. Hence two headings, two questions, and a line under the first
 * saying what it is not.
 */

const DOT = {
  verified: 'text-emerald-400',
  // A claim about a proportion is badly served by a binary. Provenance at 73%
  // is neither verified nor failed, and showing red for it would misinform as
  // surely as showing green.
  partial: 'text-amber-400',
  failed: 'text-red-400',
  unknown: 'text-gray-600',
}

function Claim({ c }) {
  return (
    <div className="flex items-baseline gap-2 py-1">
      <span className={`${DOT[c.status] || DOT.unknown} text-[10px] leading-5`}>●</span>
      <div className="min-w-0">
        <p className="text-xs text-gray-300">{c.claim}</p>
        <p className="text-[11px] text-gray-500 font-mono">{c.measured}</p>
        {(c.status === 'failed' || c.status === 'partial') && c.method && (
          <p className={`text-[11px] mt-0.5 ${
            c.status === 'failed' ? 'text-red-400/80' : 'text-amber-400/70'}`}>{c.method}</p>
        )}
      </div>
    </div>
  )
}

export default function EvidencePanel() {
  const [open, setOpen] = useState(false)
  const { data: integ } = useQuery({
    queryKey: ['integrityEvidence'],
    queryFn: getIntegrityEvidence,
    staleTime: 30 * 60 * 1000,
    retry: false,
  })
  const { data: pred } = useEvidence()

  const claims = integ?.claims || []
  const anyFailed = (integ?.failed || 0) > 0
  const anyPartial = (integ?.partial || 0) > 0
  const factors = pred?.factors || []
  // Only claim a factor is tested-and-significant when the backend actually
  // carries that verdict. Reading it out of an absent field would be inventing
  // the one thing this panel exists to avoid inventing.
  const proven = factors.filter(f => f.result?.significant_at_5pct === true).length

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">
        Evidence
      </h2>

      {/* Axis 1 — the machinery. Has answers today. */}
      <div>
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-xs font-medium text-gray-300">
            Is the app computing what it claims?
          </p>
          <span className={`text-xs shrink-0 ${
            anyFailed ? 'text-red-400' : anyPartial ? 'text-amber-300' : 'text-emerald-400'}`}>
            {integ?.available
              ? integ.summary
              : integ?.computing ? 'checking…' : 'unavailable'}
          </span>
        </div>
        {integ?.available && (
          <>
            <button
              onClick={() => setOpen(o => !o)}
              className="text-[11px] text-gray-500 hover:text-gray-400 mt-0.5"
            >
              {open ? 'hide the checks' : 'show the checks'}
            </button>
            {open && (
              <div className="mt-1 border-l border-gray-800 pl-3">
                {claims.map(c => <Claim key={c.id} c={c} />)}
                <p className="text-[11px] text-gray-600 mt-2">{integ.note}</p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Axis 2 — prediction. Does not have answers, and says so. */}
      <div className="border-t border-gray-800 pt-3">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-xs font-medium text-gray-300">
            Does the signal predict returns?
          </p>
          <span className={`text-xs shrink-0 ${proven ? 'text-emerald-400' : 'text-amber-300'}`}>
            {factors.length
              ? (proven ? `${proven} of ${factors.length} demonstrated`
                        : 'not established')
              : '—'}
          </span>
        </div>
        <p className="text-[11px] text-gray-500 mt-1">
          A score is the output of the model. Whether that output forecasts
          anything is a separate question, and for this model it has not been
          answered. Treat a signal as a ranking, not a prediction.
        </p>
      </div>

      <p className="text-[11px] text-gray-600 border-t border-gray-800 pt-2">
        These are different questions. Sound arithmetic is not evidence that a
        signal works, and nothing on the first line should be read as support
        for the second.
      </p>
    </div>
  )
}
