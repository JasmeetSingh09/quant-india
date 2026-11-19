import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye, EyeOff, Check, X } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { passwordStrength, STRENGTH_COLORS, STRENGTH_TEXT } from '../passwordStrength'

/**
 * Choose a new password (V4-07, 19 Nov 2026). The link from the reset e-mail
 * opens this page with a short-lived recovery session (Supabase handles the
 * link itself); updatePassword then sets the new password on that account.
 *
 * Without a session the link was expired or already used, so the page offers
 * a new one instead of a form that cannot work. Same strength rule as sign-up.
 */
export default function ResetPassword() {
  const { user, updatePassword } = useAuth()
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [err, setErr] = useState(null)

  const strength = useMemo(() => passwordStrength(pw, user?.email || ''), [pw, user?.email])
  const mismatch = pw2.length > 0 && pw !== pw2

  const submit = async e => {
    e.preventDefault()
    if (!strength.ok) { setErr('Please choose a stronger password.'); return }
    if (pw !== pw2) { setErr('The two passwords do not match.'); return }
    setBusy(true); setErr(null)
    try {
      const { error } = await updatePassword(pw)
      if (error) {
        setErr(error.code === 'same_password'
          ? 'Choose a password different from your current one.'
          : 'We could not save your new password. Request a new reset link and try again.')
        return
      }
      setDone(true)
    } catch {
      setErr('We could not save your new password. Request a new reset link and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="card w-full max-w-sm space-y-5">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">Choose a new password</h1>
          {user && !done && (
            <p className="text-sm text-gray-400 mt-1 break-words">For {user.email}</p>
          )}
        </div>

        {!user ? (
          <div className="space-y-3 text-center" role="status">
            <p className="text-sm text-gray-300">
              This reset link has expired or was already used.
            </p>
            <Link to="/forgot-password" className="btn-primary w-full inline-flex justify-center">
              Send a new link
            </Link>
          </div>
        ) : done ? (
          <div className="space-y-3 text-center" role="status">
            <Check size={28} className="mx-auto text-green-400" aria-hidden="true" />
            <p className="text-base font-semibold text-white">Your password is updated</p>
            <p className="text-sm text-gray-400">You are signed in.</p>
            <Link to="/" className="btn-primary w-full inline-flex justify-center">Continue to the dashboard</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <div>
              <label htmlFor="new-password" className="text-xs text-gray-400">New password</label>
              <div className="relative">
                <input
                  id="new-password" type={showPw ? 'text' : 'password'} required minLength={8}
                  value={pw} onChange={e => setPw(e.target.value)}
                  className="input w-full pr-9" autoComplete="new-password"
                />
                <button
                  type="button" onClick={() => setShowPw(s => !s)}
                  className="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 rounded text-gray-400 hover:text-gray-200"
                  aria-label={showPw ? 'Hide password' : 'Show password'}
                >
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              {pw && (
                <div className="mt-2 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 flex gap-1">
                      {[0, 1, 2, 3].map(i => (
                        <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${
                          i < strength.score ? STRENGTH_COLORS[strength.score] : 'bg-gray-700'
                        }`} />
                      ))}
                    </div>
                    <span className={`text-[11px] font-medium ${STRENGTH_TEXT[strength.score]}`}>
                      {strength.label}
                    </span>
                  </div>
                  <ul className="space-y-0.5">
                    {strength.issues.map((iss, i) => (
                      <li key={i} className="flex items-center gap-1.5 text-[11px] text-gray-400">
                        <X size={11} className="text-red-400 shrink-0" /> {iss}
                      </li>
                    ))}
                    {strength.ok && (
                      <li className="flex items-center gap-1.5 text-[11px] text-green-400">
                        <Check size={11} className="shrink-0" /> Password looks good
                      </li>
                    )}
                  </ul>
                </div>
              )}
            </div>
            <div>
              <label htmlFor="new-password-2" className="text-xs text-gray-400">Type it again</label>
              <input
                id="new-password-2" type={showPw ? 'text' : 'password'} required
                value={pw2} onChange={e => setPw2(e.target.value)}
                className="input w-full" autoComplete="new-password"
                aria-invalid={mismatch || undefined}
                aria-describedby={mismatch ? 'new-password-2-msg' : undefined}
              />
              {mismatch && (
                <p id="new-password-2-msg" className="text-xs text-red-400 mt-1">The passwords do not match yet.</p>
              )}
            </div>
            {err && <p className="text-sm text-red-400" role="alert">{err}</p>}
            <button type="submit" disabled={busy || !strength.ok || pw !== pw2} className="btn-primary w-full">
              {busy ? 'Please wait…' : 'Save new password'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
