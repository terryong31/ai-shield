import * as z from 'zod'
import type { PlayerConfirmationResponse } from '~/types/api'

/** What a failed sign-in means for the page (spec 0027, 0047). */
export type LoginFailure = 'unconfirmed' | 'invalid' | 'blocked' | 'unavailable'

export const AUTH_BROWSER_COOKIE = 'shield_auth_browser'
export const UNCONFIRMED_EMAIL_DETAIL = 'Confirm your email before signing in.'

const BROWSER_TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,128}$/

function randomBrowserToken(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/**
 * Ensures a browser-side cookie exists so the gateway can verify that an email
 * confirmation link was opened in the same browser (spec 0047).
 */
export function ensureAuthBrowserCookie(existing?: string): string {
  if (typeof existing === 'string' && BROWSER_TOKEN_PATTERN.test(existing)) {
    return existing
  }
  if (typeof document !== 'undefined') {
    const match = document.cookie
      .split('; ')
      .find(part => part.startsWith(`${AUTH_BROWSER_COOKIE}=`))
    const current = match?.slice(AUTH_BROWSER_COOKIE.length + 1)
    if (current && BROWSER_TOKEN_PATTERN.test(current)) {
      return current
    }
    const token = randomBrowserToken()
    const secure = typeof window !== 'undefined' && window.location.protocol === 'https:'
      ? '; Secure'
      : ''
    document.cookie = `${AUTH_BROWSER_COOKIE}=${token}; Path=/; Max-Age=3600; SameSite=Lax${secure}`
    return token
  }
  return randomBrowserToken()
}

export const PASSWORD_REQUIREMENTS = [
  { regex: /.{8,}/, text: 'At least 8 characters' },
  { regex: /\d/, text: 'At least 1 number' },
  { regex: /[a-z]/, text: 'At least 1 lowercase letter' },
  { regex: /[A-Z]/, text: 'At least 1 uppercase letter' }
] as const

export function checkPasswordStrength(password: string): Array<{ met: boolean, text: string }> {
  return PASSWORD_REQUIREMENTS.map(req => ({ met: req.regex.test(password), text: req.text }))
}

export function passwordStrengthScore(password: string): number {
  return checkPasswordStrength(password).filter(req => req.met).length
}

export function isStrongPassword(password: string): boolean {
  return password.length <= 512 && PASSWORD_REQUIREMENTS.every(req => req.regex.test(password))
}

export function passwordStrengthColor(score: number): 'neutral' | 'error' | 'warning' | 'success' {
  if (score === 0) return 'neutral'
  if (score <= 1) return 'error'
  if (score <= 3) return 'warning'
  return 'success'
}

export function passwordStrengthText(score: number): string {
  if (score === 0) return 'Enter a password'
  if (score <= 2) return 'Weak password'
  if (score === 3) return 'Medium password'
  return 'Strong password'
}

export const strongPasswordSchema = z
  .string('Password is required')
  .min(8, 'At least 8 characters')
  .max(512, 'At most 512 characters')
  .regex(/\d/, 'At least 1 number')
  .regex(/[a-z]/, 'At least 1 lowercase letter')
  .regex(/[A-Z]/, 'At least 1 uppercase letter')

export const registerSchema = z.object({
  player_name: z.string('Player name is required').trim().min(1, 'Player name is required').max(64),
  email: z.email('Invalid email'),
  password: strongPasswordSchema
})

export const loginSchema = z.object({
  email: z.email('Invalid email'),
  password: z.string('Password is required').min(8, 'Must be at least 8 characters').max(512)
})

export const recoverSchema = z.object({
  email: z.email('Invalid email')
})

export const resetPasswordSchema = z.object({
  password: strongPasswordSchema,
  confirm: z.string('Confirm new password').min(1, 'Confirm new password')
}).refine(data => data.password === data.confirm, {
  message: 'The passwords do not match.',
  path: ['confirm']
})

export const passwordChangeSchema = z.object({
  current: z.string('Current password is required').min(1, 'Current password is required').max(512),
  next: strongPasswordSchema,
  confirm: z.string('Confirm new password').min(1, 'Confirm new password')
})
  .refine(data => data.next === data.confirm, {
    message: 'The passwords do not match.',
    path: ['confirm']
  })
  .refine(data => data.next !== data.current, {
    message: 'The new password must differ from the current one.',
    path: ['next']
  })

export type RegisterSchema = z.output<typeof registerSchema>
export type LoginSchema = z.output<typeof loginSchema>
export type RecoverSchema = z.output<typeof recoverSchema>
export type ResetPasswordSchema = z.output<typeof resetPasswordSchema>
export type PasswordChangeSchema = z.output<typeof passwordChangeSchema>

/** True when register answered "check your email" rather than signing the player in. */
export function isConfirmationSent(body: unknown): body is PlayerConfirmationResponse {
  return typeof body === 'object' && body !== null
    && (body as { status?: unknown }).status === 'confirmation_sent'
}

export function loginFailure(statusCode: number | undefined, detail?: string): LoginFailure {
  if (statusCode === 403) {
    if (detail === undefined || detail === UNCONFIRMED_EMAIL_DETAIL) {
      return 'unconfirmed'
    }
    return 'blocked'
  }
  if (statusCode === 401) return 'invalid'
  return 'unavailable'
}
