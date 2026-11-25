import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import * as apiProxy from '../shared/utils/apiProxy'
import * as playerAuth from '../app/utils/playerAuth'

const ROOT = join(import.meta.dirname, '..')
const APP_DIR = join(ROOT, 'app')
const readApp = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')
const readRoot = (...parts: string[]) => readFileSync(join(ROOT, ...parts), 'utf-8')

describe('auth flows and hardening (spec 0047)', () => {
  it('[WEB-AUTH-001] /auth/confirmed strips query params, calls confirm with confirm:false, and shows signed-in state', () => {
    const page = readApp('pages', 'auth', 'confirmed.vue')
    expect(page).toContain('router.replace')
    expect(page).toContain('confirm: false')
    expect(page).toContain('signed_in')
    expect(page).toContain('/game')
  })

  it('[WEB-AUTH-002] /auth/confirmed shows manual confirmation screen on confirmation_required and submits confirm:true', () => {
    const page = readApp('pages', 'auth', 'confirmed.vue')
    expect(page).toContain('confirmation_required')
    expect(page).toContain('Confirm email')
    expect(page).toContain('confirm: true')
    expect(page).toContain('/auth/login')
  })

  it('[WEB-AUTH-003] /auth/confirmed renders error state for error query params or missing token/code', () => {
    const page = readApp('pages', 'auth', 'confirmed.vue')
    expect(page).toMatch(/error_code|error_description|error/)
    expect(page).toContain('i-lucide-mail-warning')
  })

  it('[WEB-AUTH-004] ensures shield_auth_browser cookie before auth email flows and sets Referrer-Policy on /auth/**', () => {
    const fn = (playerAuth as Record<string, unknown>).ensureAuthBrowserCookie as
      | ((existing?: string) => string)
      | undefined
    expect(typeof fn).toBe('function')
    const token = fn!('')
    expect(token).toMatch(/^[A-Za-z0-9_-]{32,128}$/)

    const authComposable = readApp('composables', 'usePlayerAuth.ts')
    expect(authComposable).toContain('ensureAuthBrowserCookie')

    const nuxtConfig = readRoot('nuxt.config.ts')
    expect(nuxtConfig).toContain('/auth/**')
    expect(nuxtConfig).toContain('Referrer-Policy')
    expect(nuxtConfig).toContain('no-referrer')
  })

  it('[WEB-AUTH-005] /auth/reset-password strips params, uses PasswordStrengthField, and calls resetPassword', () => {
    const resetPath = join(APP_DIR, 'pages', 'auth', 'reset-password.vue')
    expect(existsSync(resetPath)).toBe(true)
    const page = readFileSync(resetPath, 'utf-8')
    expect(page).toContain('router.replace')
    expect(page).toContain('<PasswordStrengthField')
    expect(page).toContain('resetPassword')
    expect(page).toContain('/auth/login')
  })

  it('[WEB-AUTH-006] /auth/recover validates email with Zod schema and /settings mentions both inboxes', () => {
    const recoverPage = readApp('pages', 'auth', 'recover.vue')
    expect(recoverPage).toContain(':schema="recoverSchema"')

    const settingsPage = readApp('pages', 'settings.vue')
    expect(settingsPage).toMatch(/both.*current.*new.*inboxes/i)
  })

  it('[WEB-AUTH-007] signInWithPassword and registerAccount do not trim passwords', () => {
    const authComposable = readApp('composables', 'usePlayerAuth.ts')
    expect(authComposable).not.toMatch(/password:\s*password\.trim\(\)/)
  })

  it('[WEB-AUTH-008] loginFailure distinguishes BotID 403 from unconfirmed-email 403', () => {
    const fn = playerAuth.loginFailure as (statusCode: number | undefined, detail?: string) => string
    expect(fn(403, 'Confirm your email before signing in.')).toBe('unconfirmed')
    expect(fn(403, 'Request blocked.')).toBe('blocked')
    expect(fn(401, 'Invalid email or password.')).toBe('invalid')
  })

  it('[WEB-AUTH-009] botid.client.ts uses enforce:pre, loadAccess moves to dashboard.vue, and proxy blocks cross-site mutations', async () => {
    const plugin = readApp('plugins', 'botid.client.ts')
    expect(plugin).toMatch(/enforce:\s*'pre'/)

    const appVue = readApp('app.vue')
    expect(appVue).not.toContain('loadAccess')

    const dashboardLayout = readApp('layouts', 'dashboard.vue')
    expect(dashboardLayout).toContain('loadAccess')

    const botidMod = await import('../shared/utils/botid')
    expect(botidMod.BOTID_PROTECTED_ROUTES).toHaveLength(9)

    const res = await apiProxy.proxyToGateway(
      new Request('https://shield-web.example/api/v1/auth/login', {
        method: 'POST',
        headers: { 'sec-fetch-site': 'cross-site' },
        body: '{}'
      }),
      'http://gateway.internal:8000'
    )
    expect(res.status).toBe(403)
    expect(await res.json()).toEqual({ detail: 'Cross-site request blocked.' })
  })
})
