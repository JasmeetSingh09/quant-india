import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../AuthContext'

export default function Login() {
  const { signIn, signUp } = useAuth()
  const [mode, setMode]   = useState('signin')   // 'signin' | 'signup'
  const [email, setEmail] = useState('')
  const [pw, setPw]       = useState('')
  const [busy, setBusy]   = useState(false)
  const [msg, setMsg]     = useState(null)
  const [err, setErr]     = useState(null)

  const submit = async e => {
    e.preventDefault()
    setBusy(true); setErr(null); setMsg(null)
    try {
      if (mode === 'signup') {
        const { error } = await signUp(email.trim(), pw)
        if (error) throw error
        setMsg('Account created. Check your email to confirm, then sign in.')
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
            <input
              type="password" required minLength={6} value={pw} onChange={e => setPw(e.target.value)}
              className="input w-full" placeholder="••••••••"
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            />
          </div>

          {err && <p className="text-sm text-red-400">{err}</p>}
          {msg && <p className="text-sm text-green-400">{msg}</p>}

          <button type="submit" disabled={busy} className="btn-primary w-full">
            {busy ? 'Please wait…' : mode === 'signup' ? 'Create account' : 'Sign in'}
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
