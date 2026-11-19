import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import { useAuth } from '../AuthContext'

/**
 * Ask for a password-reset link (V4-07, 19 Nov 2026) — the standard Supabase
 * flow: resetPasswordForEmail mails a link that opens /reset-password.
 *
 * The "check your email" answer is the same whether or not an account exists
 * for the address, so this page cannot be used to find out who has one.
 */
export default function ForgotPassword() {
  const { requestPasswordReset } = useAuth()
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sentTo, setSentTo] = useState(null)
  const [err, setErr] = useState(null)

  const submit = async e => {
    e.preventDefault()
    const addr = email.trim()
    if (!addr) return
    setBusy(true); setErr(null)
    try {
      const { error } = await requestPasswordReset(addr)
      // Supabase answers the same for unknown addresses; an error here is a
      // send limit or a network problem, never "no such account".
      if (error) throw error
      setSentTo(addr)
    } catch {
      setErr('We could not send the email just now. Wait a minute, then try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="card w-full max-w-sm space-y-5">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">Reset your password</h1>
          {!sentTo && (
            <p className="text-sm text-gray-400 mt-1">
              Enter your account's email and we'll send you a link to choose a new password.
            </p>
          )}
        </div>

        {sentTo ? (
          <div className="space-y-3 text-center" role="status">
            <MailCheck size={28} className="mx-auto text-green-400" aria-hidden="true" />
            <p className="text-base font-semibold text-white">Check your email</p>
            <p className="text-sm text-gray-300 break-words">
              If an account exists for <span className="font-medium text-white">{sentTo}</span>,
              we've sent it a link to reset your password.
            </p>
            <p className="text-xs text-gray-400">
              It can take a few minutes. Check your spam folder too. The link works once.
            </p>
            <button
              type="button" onClick={() => { setSentTo(null); setErr(null) }}
              className="text-sm text-gray-300 hover:text-white underline underline-offset-4"
            >
              Use a different email
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <div>
              <label htmlFor="reset-email" className="text-xs text-gray-400">Email</label>
              <input
                id="reset-email" type="email" required value={email}
                onChange={e => setEmail(e.target.value)}
                className="input w-full" placeholder="you@example.com" autoComplete="email"
              />
            </div>
            {err && <p className="text-sm text-red-400" role="alert">{err}</p>}
            <button type="submit" disabled={busy} className="btn-primary w-full">
              {busy ? 'Please wait…' : 'Send reset link'}
            </button>
          </form>
        )}

        <div className="text-center">
          <Link to="/login" className="text-xs text-gray-400 hover:text-gray-200">← Back to sign in</Link>
        </div>
      </div>
    </div>
  )
}
