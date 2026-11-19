// 18+ confirmation (V4-02, decided 19 Nov 2026).
//
// Sign-up stores the flag in the new account's Supabase user_metadata, so it
// needs no database column. Accounts created before this were not backfilled:
// they carry no flag, and product events are simply not recorded for them.
// The server applies the same rule (backend auth.events_allowed), so this is
// only to avoid sending requests that would not be stored.
export const AGE_FLAG = 'age_18_confirmed'

export function ageConfirmationMetadata(now = new Date()) {
  return { [AGE_FLAG]: true, age_18_confirmed_at: now.toISOString() }
}

export function isAdultConfirmed(user) {
  return user?.user_metadata?.[AGE_FLAG] === true
}
