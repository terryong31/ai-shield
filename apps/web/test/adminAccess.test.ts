import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const ADMIN_APP_DIR = join(import.meta.dirname, '..', '..', 'admin', 'app')
const read = (...parts: string[]) => readFileSync(join(ADMIN_APP_DIR, ...parts), 'utf-8')

const CONSOLE_FILES = [
  ['composables', 'useAdminAccess.ts'],
  ['composables', 'useShieldApi.ts'],
  ['layouts', 'dashboard.vue'],
  ['pages', 'index.vue'],
  ['pages', 'settings.vue'],
  ['app.vue']
]

describe('admin console sign-in (spec 0012)', () => {
  it('[WEB-CLEAR-002] sends email and password once, stores neither, and never mentions a passphrase', () => {
    const api = read('composables', 'useShieldApi.ts')
    expect(api).toMatch(/grantClearance = async \(email: string, password: string\)/)
    expect(api).toMatch(/body: \{ email, password \}/)

    const access = read('composables', 'useAdminAccess.ts')
    expect(access).toMatch(/grantClearance\(email\.trim\(\), password\)/)
    expect(access).not.toMatch(/(localStorage|sessionStorage)\.setItem/)
    expect(access).not.toMatch(/useState<string>/)
    expect(access).not.toMatch(/useCookie/)

    const layout = read('layouts', 'dashboard.vue')
    expect(layout).toMatch(/useAdminAccess\(\)/)
    expect(layout).toMatch(/name: 'email'/)
    expect(layout).toMatch(/name: 'password'/)

    expect(existsSync(join(ADMIN_APP_DIR, 'composables', 'usePassphrase.ts'))).toBe(false)
    for (const parts of CONSOLE_FILES) {
      expect(read(...parts), parts.join('/')).not.toMatch(/passphrase/i)
    }
  })
})
