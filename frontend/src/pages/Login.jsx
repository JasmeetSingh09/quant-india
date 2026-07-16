import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Eye, EyeOff, Check, X } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { passwordStrength, STRENGTH_COLORS, STRENGTH_TEXT } from '../passwordStrength'

export default function Login() {
  const { signIn, signUp } = useAuth()
  const [mode, setMode]   = useState('signin')   // 'signin' | 'signup'
  const [email, setEmail] = useState('')
  const [pw, setPw]       = useState('')
  const [showPw, setShowPw] = useState(false)
  const [busy, setBusy]   = useState(false)
  const [msg, setMsg]     = useState(null)
  const [err, setErr]     = useState(null)

  const strength = useMemo(() => passwordStrength(pw, email), [pw, email])
  const isSignup = mode === 'signup'
  // Only gate SIGNUP on strength — never block an existing user from signing in
  // just because the password they already have is weak.
  const blocked = isSignup && !strength.ok

  const submit = async e => {
    e.preventDefault()
    if (blocked) { setErr('Please choose a stronger password.'); return }
    setBusy(true); setErr(null); setMsg(null)
    try {
      if (mode === 'signup') {
        const { data, error } = await signUp(email.trim(), pw)
        if (error) throw error

        // Supabase hides "email already registered" behind an empty identities
        // array (to prevent account enumeration) rather than erroring.
        if (data?.user && data.user.identities?.length === 0) {
          setErr('That email is already registered — try signing in instead.')
          setMode('signin')
          return
        }
        // If the project has "Confirm email" OFF, signUp returns a session and
        // the user is ALREADY signed in — don't tell them to check their inbox.
        // AuthProvider picks the session up and App swaps to the app view.
        if (data?.session) return

        // Otherwise confirmation genuinely is required.
        setMsg('Account created. Check your email for the confirmation link, then sign in.')
        setMode('signin')
      } else {
        const { error } = await signIn(email.trim(), pw)
        if (error) throw error
        // AuthProvider picks up the session and App swaps to the app view.
      }
    } catch (e2) {
      setErr(e2?.message || 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="card w-full max-w-sm space-y-5">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">Quant India</h1>
          <p className="text-sm text-gray-400 mt-1">
            {mode === 'signup' ? 'Create your account' : 'Sign in to your account'}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            Signing in gives you a private watchlist, portfolio & simulations —
            and lets us email your price/sentiment alerts.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="text-xs text-gray-400">Email</label>
            <input
              type="email" required value={email} onChange={e => setEmail(e.target.value)}
              className="input w-full" placeholder="you@example.com" autoComplete="email"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Password</label>
            <div className="relative">
              <input
                type={showPw ? 'text' : 'password'} required
                minLength={isSignup ? 8 : undefined}
                value={pw} onChange={e => setPw(e.target.value)}
                className="input w-full pr-9" placeholder="••••••••"
                autoComplete={isSignup ? 'new-password' : 'current-password'}
              />
              <button
                type="button" onClick={() => setShowPw(s => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                title={showPw ? 'Hide password' : 'Show password'}
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>

            {/* Strength meter — signup only */}
            {isSignup && pw && (
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
                    <li key={i} className="flex items-center gap-1.5 text-[11px] text-gray-500">
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

          {err && <p className="text-sm text-red-400">{err}</p>}
          {msg && <p className="text-sm text-green-400">{msg}</p>}

          <button type="submit" disabled={busy || blocked} className="btn-primary w-full">
            {busy ? 'Please wait…' : isSignup ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <div className="text-center text-sm text-gray-400">
          {mode === 'signup' ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button
            onClick={() => { setMode(mode === 'signup' ? 'signin' : 'signup'); setErr(null); setMsg(null) }}
            className="text-blue-400 hover:text-blue-300 underline"
          >
            {mode === 'signup' ? 'Sign in' : 'Sign up'}
          </button>
        </div>

        <div className="text-center">
          <Link to="/" className="text-xs text-gray-500 hover:text-gray-300">← Back to home</Link>
        </div>
      </div>
    </div>
  )
}
