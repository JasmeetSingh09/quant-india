import { createContext, useContext, useEffect, useState } from 'react'
import { supabase } from './supabaseClient'

const AuthContext = createContext({ user: null, session: null, loading: true })

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Load any persisted session on first mount…
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    // …then keep in sync on login / logout / token refresh.
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  const value = {
    session,
    user: session?.user ?? null,
    loading,
    signIn:  (email, password) => supabase.auth.signInWithPassword({ email, password }),
    // Send the confirmation link back to THIS site. Without emailRedirectTo,
    // Supabase falls back to its project "Site URL" — which defaults to
    // http://localhost:3000, so the emailed link opens a dead page for real users.
    // NOTE: the origin must also be in Supabase → Auth → URL Configuration →
    // Redirect URLs, or Supabase ignores it and uses the Site URL anyway.
    signUp:  (email, password) => supabase.auth.signUp({
      email, password,
      options: { emailRedirectTo: window.location.origin },
    }),
    signOut: () => supabase.auth.signOut(),
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
