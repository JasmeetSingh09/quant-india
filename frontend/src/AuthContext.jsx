import { createContext, useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from './supabaseClient'
import { ageConfirmationMetadata } from './ageGate'

const AuthContext = createContext({ user: null, session: null, loading: true })

// Where the reset-password e-mail sends people back to. This address must be
// in Supabase → Authentication → URL Configuration → Redirect URLs, or
// Supabase ignores it and uses the Site URL instead (19 Nov 2026).
const resetRedirect = () => `${window.location.origin}/reset-password`

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    // Load any persisted session on first mount…
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    // …then keep in sync on login / logout / token refresh.
    const { data: sub } = supabase.auth.onAuthStateChange((event, s) => {
      setSession(s)
      // A reset link signs the person in for one purpose: choosing a new
      // password. If the link landed anywhere else (Supabase falls back to
      // the Site URL when the redirect is not allowed), take them there.
      if (event === 'PASSWORD_RECOVERY' && window.location.pathname !== '/reset-password') {
        navigate('/reset-password', { replace: true })
      }
    })
    return () => sub.subscription.unsubscribe()
  }, [navigate])

  const value = {
    session,
    user: session?.user ?? null,
    loading,
    signIn:  (email, password) => supabase.auth.signInWithPassword({ email, password }),
    // Send the confirmation link back to THIS site. Without emailRedirectTo,
    // Supabase falls back to its project "Site URL" — which defaults to
    // a local development address, so the emailed link opens a dead page for real users.
    // NOTE: the origin must also be in Supabase → Auth → URL Configuration →
    // Redirect URLs, or Supabase ignores it and uses the Site URL anyway.
    // The 18+ confirmation is stored with the new account (user_metadata;
    // V4-02, 19 Nov 2026). Sign-up refuses to submit without it.
    signUp:  (email, password) => supabase.auth.signUp({
      email, password,
      options: { emailRedirectTo: window.location.origin, data: ageConfirmationMetadata() },
    }),
    signOut: () => supabase.auth.signOut(),
    // Standard Supabase reset (V4-07, 19 Nov 2026): e-mail a link, then the
    // link opens /reset-password signed in, where updatePassword sets the new one.
    requestPasswordReset: email =>
      supabase.auth.resetPasswordForEmail(email, { redirectTo: resetRedirect() }),
    updatePassword: password => supabase.auth.updateUser({ password }),
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
