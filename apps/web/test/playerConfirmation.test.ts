import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  checkPasswordStrength,
  isConfirmationSent,
  isStrongPassword,
  loginFailure,
  loginSchema,
  passwordChangeSchema,
  passwordStrengthScore,
  registerSchema
} from '../app/utils/playerAuth'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

describe('player email confirmation (spec 0027)', () => {
  it('[WEB-VERIFY-001] register shows "Check your email" with a resend button and stays signed out', () => {
    expect(isConfirmationSent({ status: 'confirmation_sent' })).toBe(true)
    expect(isConfirmationSent({ authenticated: true, email: 'a@b.co' })).toBe(false)
    expect(isConfirmationSent(null)).toBe(false)

    const api = read('composables', 'useShieldApi.ts')
    expect(api).toMatch(/resendConfirmation: \(body: PlayerResendRequest\) =>/)
    expect(api).toMatch(/'\/auth\/resend-confirmation', \{ method: 'POST', body \}/)

    const auth = read('composables', 'usePlayerAuth.ts')
    expect(auth).toMatch(/if \(isConfirmationSent\(result\)\) return 'confirmation_sent'/)
    expect(auth).toMatch(/const resendConfirmationEmail = async \(email: string\)/)

    const page = read('pages', 'auth', 'register.vue')
    expect(page).toMatch(/title="Check your email"/)
    expect(page).toMatch(/\{\{ sentTo \}\}/)
    expect(page).toMatch(/label="Resend email"/)
    expect(page).toMatch(/@click="resendConfirmationEmail\(sentTo\)"/)
    expect(page).toMatch(/if \(outcome === 'signed_in'\) \{\s*await goBack\('\/'\)/)
  })

  it('[WEB-VERIFY-002] login shows "Confirm your email first" with a resend button on 403', () => {
    expect(loginFailure(403)).toBe('unconfirmed')
    expect(loginFailure(401)).toBe('invalid')
    expect(loginFailure(503)).toBe('unavailable')
    expect(loginFailure(undefined)).toBe('unavailable')

    const auth = read('composables', 'usePlayerAuth.ts')
    expect(auth).toMatch(/if \(failure === 'unconfirmed'\) return 'unconfirmed'/)

    const page = read('pages', 'auth', 'login.vue')
    expect(page).toMatch(/title="Confirm your email first"/)
    expect(page).toMatch(/label="Resend email"/)
    expect(page).toMatch(/@click="resendConfirmationEmail\(unconfirmedEmail\)"/)
  })

  it('[WEB-VERIFY-003] /auth/confirmed says the email is confirmed and links to sign in', () => {
    const page = read('pages', 'auth', 'confirmed.vue')
    expect(page).toMatch(/title="Email confirmed"/)
    expect(page).toMatch(/to: '\/auth\/login'/)
    expect(page).not.toMatch(/useRoute|location\.hash|window\.location|localStorage|sessionStorage|useCookie/)
  })

  it('[WEB-AUTH-001] enforces Zod validation and renders the Nuxt UI password strength indicator on register and settings', () => {
    const partial = checkPasswordStrength('Abcdef1')
    expect(partial.filter(r => r.met)).toHaveLength(3)
    expect(passwordStrengthScore('Abcdef1')).toBe(3)
    expect(isStrongPassword('Abcdef1')).toBe(false)

    const full = checkPasswordStrength('Abcdefg1')
    expect(full.filter(r => r.met)).toHaveLength(4)
    expect(passwordStrengthScore('Abcdefg1')).toBe(4)
    expect(isStrongPassword('Abcdefg1')).toBe(true)

    expect(registerSchema.safeParse({
      player_name: 'Ada',
      email: 'ada@example.com',
      password: 'weakpass1'
    }).success).toBe(false)
    expect(registerSchema.safeParse({
      player_name: 'Ada',
      email: 'ada@example.com',
      password: 'StrongPass1'
    }).success).toBe(true)

    expect(loginSchema.safeParse({ email: 'bad-email', password: 'password123' }).success).toBe(false)
    expect(loginSchema.safeParse({ email: 'ada@example.com', password: 'short1A' }).success).toBe(false)
    expect(loginSchema.safeParse({ email: 'ada@example.com', password: 'password123' }).success).toBe(true)

    expect(passwordChangeSchema.safeParse({
      current: 'OldPass1',
      next: 'weak',
      confirm: 'weak'
    }).success).toBe(false)
    expect(passwordChangeSchema.safeParse({
      current: 'OldPass1',
      next: 'StrongPass1',
      confirm: 'StrongPass2'
    }).success).toBe(false)
    expect(passwordChangeSchema.safeParse({
      current: 'OldPass1',
      next: 'OldPass1',
      confirm: 'OldPass1'
    }).success).toBe(false)
    expect(passwordChangeSchema.safeParse({
      current: 'OldPass1',
      next: 'StrongPass1',
      confirm: 'StrongPass1'
    }).success).toBe(true)

    const registerSource = read('pages', 'auth', 'register.vue')
    expect(registerSource).toContain(':schema="registerSchema"')
    expect(registerSource).toContain('#password-field')
    expect(registerSource).toContain('<PasswordStrengthField')

    const loginSource = read('pages', 'auth', 'login.vue')
    expect(loginSource).toContain(':schema="loginSchema"')

    const settingsSource = read('pages', 'settings.vue')
    expect(settingsSource).toContain(':schema="passwordChangeSchema"')
    expect(settingsSource).toContain('<PasswordStrengthField')

    const fieldSource = read('components', 'PasswordStrengthField.vue')
    expect(fieldSource).toContain('<UInput')
    expect(fieldSource).toContain('<UProgress')
    expect(fieldSource).toContain('aria-label="Password requirements"')
    expect(fieldSource).toContain('checkPasswordStrength')
    expect(fieldSource).toContain('i-lucide-circle-check')
    expect(fieldSource).toContain('i-lucide-circle-x')

    const playerAuthSource = read('utils', 'playerAuth.ts')
    for (const label of [
      'At least 8 characters',
      'At least 1 number',
      'At least 1 lowercase letter',
      'At least 1 uppercase letter'
    ]) {
      expect(playerAuthSource).toContain(label)
    }
  })
})
