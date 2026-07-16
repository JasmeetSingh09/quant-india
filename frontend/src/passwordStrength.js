/**
 * Password strength scoring for the signup form.
 *
 * NOTE: this is UX, not security — client-side checks can be bypassed. Real
 * enforcement must also be set in Supabase (Authentication → Policies →
 * password requirements). This stops users *choosing* a weak password.
 */

// The passwords attackers try first. Kept short and targeted rather than a
// giant list — these plus the pattern rules below catch the realistic cases.
const COMMON = new Set([
  'password', 'password1', 'password123', 'passw0rd', '12345678', '123456789',
  '1234567890', '123456', 'qwerty', 'qwerty123', 'qwertyuiop', 'abc123',
  'letmein', 'welcome', 'welcome1', 'monkey', 'dragon', 'iloveyou', 'admin',
  'admin123', 'login', 'starwars', 'football', 'baseball', 'sunshine',
  'princess', 'trustno1', 'master', 'shadow', 'superman', 'michael',
  'india123', 'indian123', 'test1234', 'changeme', 'secret', 'default',
])

/**
 * @returns {{score:0|1|2|3|4, label:string, issues:string[], ok:boolean}}
 * ok === true means the password is allowed for signup.
 */
export function passwordStrength(pw = '', email = '') {
  const issues = []
  const p = String(pw)

  if (p.length < 8) issues.push('Use at least 8 characters')

  const hasLower  = /[a-z]/.test(p)
  const hasUpper  = /[A-Z]/.test(p)
  const hasDigit  = /[0-9]/.test(p)
  const hasSymbol = /[^A-Za-z0-9]/.test(p)
  const classes = [hasLower, hasUpper, hasDigit, hasSymbol].filter(Boolean).length

  if (classes < 3) issues.push('Mix upper case, lower case, numbers or symbols')

  const lower = p.toLowerCase()
  if (COMMON.has(lower)) issues.push('This is a commonly used password')

  // repeated single char, or simple sequences
  if (/^(.)\1+$/.test(p)) issues.push('Avoid repeating one character')
  if (/^(?:0123|1234|2345|3456|4567|5678|6789|abcd|qwer)/.test(lower))
    issues.push('Avoid simple sequences like 1234 or qwerty')

  // don't let the password be (or contain) the email name
  const localPart = String(email).split('@')[0]?.toLowerCase()
  if (localPart && localPart.length >= 3 && lower.includes(localPart))
    issues.push("Don't use your email name in the password")

  // score
  let score = 0
  if (p.length >= 8) score++
  if (p.length >= 12) score++
  if (classes >= 3) score++
  if (classes === 4 && p.length >= 10) score++
  if (issues.some(i => i.includes('commonly used') || i.includes('sequences') || i.includes('repeating')))
    score = Math.min(score, 1)
  if (!p) score = 0
  score = Math.max(0, Math.min(4, score))

  const label = ['Very weak', 'Weak', 'Fair', 'Good', 'Strong'][score]
  // Allow signup only when there are no blocking issues.
  const ok = p.length >= 8 && classes >= 3 && issues.length === 0

  return { score, label, issues, ok }
}

export const STRENGTH_COLORS = [
  'bg-red-500', 'bg-red-500', 'bg-yellow-500', 'bg-lime-500', 'bg-green-500',
]
export const STRENGTH_TEXT = [
  'text-red-400', 'text-red-400', 'text-yellow-400', 'text-lime-400', 'text-green-400',
]
