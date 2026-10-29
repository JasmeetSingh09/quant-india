import { useState } from 'react'
import { deleteAccount } from '../api'
import { useAuth } from '../AuthContext'

/**
 * DeleteAccount — the DPDP right to erasure, one click from the account email.
 *
 * Typing DELETE is the confirmation: the action removes the portfolios,
 * watchlist, theses, simulations, share links, email address and the sign-in
 * itself, and none of it can be restored.
 */
export default function DeleteAccount() {
  const { signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
              className="text-[11px] text-gray-600 hover:text-red-400 underline-offset-2 hover:underline">
        Delete account
      </button>
    )
  }

  const run = async () => {
    setBusy(true); setError(null)
    try {
      await deleteAccount()
      await signOut()
      window.location.assign('/')
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-red-900/60 bg-red-950/20 p-2.5">
      <p className="text-[11px] text-red-200/90 leading-relaxed">
        This permanently deletes your portfolios, watchlist, theses, simulations,
        share links, email settings and your sign-in. It cannot be undone.
      </p>
      <label className="block text-[11px] text-gray-400">
        Type DELETE to confirm
        <input value={typed} onChange={e => setTyped(e.target.value)}
               className="input mt-1 w-full text-xs" autoComplete="off" />
      </label>
      {error && <p className="text-[11px] text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button onClick={run} disabled={typed !== 'DELETE' || busy}
                className="text-[11px] px-2 py-1 rounded bg-red-700 text-white disabled:opacity-40">
          {busy ? 'Deleting…' : 'Delete my account'}
        </button>
        <button onClick={() => { setOpen(false); setTyped(''); setError(null) }}
                className="text-[11px] px-2 py-1 rounded text-gray-400 hover:text-gray-200">
          Cancel
        </button>
      </div>
    </div>
  )
}
