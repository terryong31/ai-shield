import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { deleteConfirmed, passwordChangeReady } from '../app/utils/account'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')
const settings = () => read('pages', 'settings.vue')

describe('account settings (spec 0025)', () => {
  it('[WEB-ACCOUNT-001] shows an Account card below Theme, or a sign-in link for anonymous players', () => {
    const page = settings()
    const template = page.slice(page.indexOf('<template>'))
    expect(template.indexOf('Theme')).toBeLessThan(template.indexOf('Account'))
    expect(page).toMatch(/v-if="isLoggedIn"/)
    expect(page).toContain('{{ session.email }}')
    for (const label of ['Password', 'Reset progress', 'Delete account']) {
      expect(page).toContain(label)
    }
    expect(page).toMatch(/label="Sign in to manage your account"[\s\S]*?to="\/auth\/login"|to="\/auth\/login"[\s\S]*?label="Sign in to manage your account"/)
  })

  it('[WEB-ACCOUNT-002] email and password modals call the API and refuse mismatched passwords', () => {
    expect(passwordChangeReady({ current: 'OldPass1', next: 'NewPass1', confirm: 'NewPass1' })).toBe(true)
    expect(passwordChangeReady({ current: 'OldPass1', next: 'NewPass1', confirm: 'NewPass2' })).toBe(false)
    expect(passwordChangeReady({ current: 'OldPass1', next: 'Short1A', confirm: 'Short1A' })).toBe(false)
    expect(passwordChangeReady({ current: 'OldPass1', next: 'newpass123', confirm: 'newpass123' })).toBe(false)
    expect(passwordChangeReady({ current: 'OldPass1', next: 'NewPassword', confirm: 'NewPassword' })).toBe(false)
    expect(passwordChangeReady({ current: '', next: 'NewPass1', confirm: 'NewPass1' })).toBe(false)
    expect(passwordChangeReady({ current: 'SamePass1', next: 'SamePass1', confirm: 'SamePass1' })).toBe(false)

    const api = read('composables', 'useShieldApi.ts')
    expect(api).toMatch(/changePassword: \(body: AccountPasswordRequest\) =>/)
    expect(api).toMatch(/changeEmail: \(body: AccountEmailRequest\) =>/)
    expect(api).toMatch(/resetProgress: \(body: AccountResetRequest\) =>/)
    expect(api).toMatch(/deleteAccount: \(body: AccountDeleteRequest\) =>/)
    expect(api).toMatch(/'\/auth\/account', \{ method: 'DELETE', body \}/)

    const page = settings()
    expect(page).toMatch(/:disabled="!passwordChangeReady\(passwordForm\)"/)
    expect(page).toMatch(/await changePassword\(/)
    expect(page).toMatch(/await changeEmail\(/)
    expect(page).toMatch(/errorDetail\(err\)/)
  })

  it('[WEB-ACCOUNT-003] reset and delete list what is removed, need the password, and delete waits for DELETE', () => {
    expect(deleteConfirmed('DELETE')).toBe(true)
    expect(deleteConfirmed('delete')).toBe(false)
    expect(deleteConfirmed('DELETE ')).toBe(false)

    const page = settings()
    expect(page).toMatch(/title="Reset progress"[\s\S]*?leaderboard scores[\s\S]*?saved boards/)
    expect(page).toMatch(/title="Delete account"[\s\S]*?cannot be undone/)
    expect(page).toMatch(/:disabled="!deleteConfirmed\(deleteForm\.confirm\) \|\| !deleteForm\.password"/)
  })

  it('[WEB-ACCOUNT-004] reset keeps the player on /settings; delete signs out and returns to /', () => {
    const page = settings()
    expect(page).toMatch(/await resetProgress\([\s\S]*?toast\.add\(\{\s*title: 'Progress reset'/)
    expect(page).toMatch(/await deleteAccount\([\s\S]*?await continueAnonymously\(\)[\s\S]*?await navigateTo\('\/', \{ replace: true \}\)/)
  })
})
