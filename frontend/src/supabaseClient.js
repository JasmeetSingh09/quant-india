import { createClient } from '@supabase/supabase-js'

// These are the PUBLIC (publishable/anon) Supabase values — safe to ship in the
// frontend bundle. Set them in Vercel as VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY;
// the fallbacks below let local dev work out of the box.
const url = import.meta.env.VITE_SUPABASE_URL || 'https://uoiielbtcfasjzpflimz.supabase.co'
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_rTmxamkNvht0jQp-516bGg_VAudLMDc'

export const supabase = createClient(url, anonKey, {
  auth: {
    persistSession: true,      // keep the user logged in across reloads
    autoRefreshToken: true,    // refresh the JWT before it expires
  },
})
