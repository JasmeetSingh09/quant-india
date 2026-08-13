import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getEmailPref, optInEmail } from '../api'
import { Mail, X } from 'lucide-react'

/**
 * EmailOptIn — asked once, never nagged.
 *
 * Shows only to a signed-in user who has never answered. Dismissing it stores
 * that choice locally so it does not reappear every visit: an opt-in prompt
 * that keeps returning is just a nag, and people learn to close it without
 * reading rather than to say yes.
 *
 * The address is never typed. It comes from the verified token on the server
 * side, so this component sends consent and nothing else — there is no field
 * here in which to enter somebody else's email.
 */
export default function EmailOptIn() {
  const qc = useQueryClient()
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem('ui.emailPromptDismissed') === '1')

  const { data } = useQuery({
    queryKey: ['emailPref'],
    queryFn: getEmailPref,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const mut = useMutation({
    mutationFn: optInEmail,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['emailPref'] }),
  })

  const close = () => {
    localStorage.setItem('ui.emailPromptDismissed', '1')
    setDismissed(true)
  }

  if (dismissed || !data || data.weekly || data.asked) return null

  return (
    <div className="card flex items-start gap-3">
      <Mail size={18} className="text-green-400 shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-gray-200 font-medium">
          Want a weekly summary of how your portfolio did?
        </p>
        <p className="text-xs text-gray-500 mt-1 leading-relaxed">
          One email on Sunday: what your paper portfolio did that week and which
          holding drove it. We only send when there is something to report, and
          turning it off deletes your address — we do not keep it.
        </p>
        {mut.isError && <p className="banner-error text-xs mt-2">{String(mut.error)}</p>}
        <div className="flex items-center gap-2 mt-3">
          <button onClick={() => mut.mutate()} disabled={mut.isPending}
                  className="btn-primary text-xs">
            {mut.isPending ? 'Saving…' : 'Yes, email me'}
          </button>
          <button onClick={close} className="btn-ghost text-xs">No thanks</button>
        </div>
      </div>
      <button onClick={close} aria-label="Dismiss"
              className="text-gray-600 hover:text-gray-300 shrink-0">
        <X size={15} />
      </button>
    </div>
  )
}
