import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { EXPORT_FILE_NAME, downloadJson } from '../app/utils/account'

const WEB = join(import.meta.dirname, '..')
const read = (...parts: string[]) => readFileSync(join(WEB, ...parts), 'utf-8')

describe('Privacy policy and player data (spec 0058)', () => {
  it('[WEB-PRIV-001] renders the policy with Nuxt UI, every required section and index robots', () => {
    const page = read('app', 'pages', 'privacy.vue')
    for (const section of [
      'Data we collect',
      'Cookies and browser storage',
      'Sub-processors',
      'Retention and deletion',
      'Your rights'
    ]) {
      expect(page, section).toContain(section)
    }
    expect(page).toMatch(/robots: 'index, follow'/)
    expect(page).toContain('<UPageHeader')
    expect(page).toContain('<UTable')
    expect(page).not.toMatch(/<table|<a\s/)
    for (const name of ['shield_player_session', 'shield_auth_browser', 'shield_session_hint', 'shield_session', 'shield_anon_draft']) {
      expect(page, name).toContain(name)
    }
    for (const processor of ['Supabase', 'Vercel', 'Redis', 'Stripe', 'Google', 'Groq', 'TypeSafe']) {
      expect(page, processor).toContain(processor)
    }
  })

  it('[WEB-PRIV-002] links the policy from every key page and lists it for crawlers', () => {
    for (const parts of [
      ['app', 'pages', 'index.vue'],
      ['app', 'pages', 'auth', 'login.vue'],
      ['app', 'pages', 'auth', 'register.vue'],
      ['app', 'pages', 'plans.vue'],
      ['app', 'pages', 'settings.vue']
    ]) {
      expect(read(...parts), parts.join('/')).toMatch(/to="\/privacy"/)
    }
    expect(read('app', 'pages', 'auth', 'register.vue')).toMatch(/Privacy Policy/)
    expect(read('app', 'pages', 'plans.vue')).toMatch(/Stripe[\s\S]{0,200}Privacy Policy|Privacy Policy[\s\S]{0,200}Stripe/)
    expect(read('public', 'sitemap.xml')).toContain('/privacy</loc>')
    expect(read('public', 'llms.txt')).toContain('/privacy')
    expect(read('app', 'app.vue')).toMatch(/INDEXABLE_PATHS = new Set\(\[[^\]]*'\/privacy'/)
  })

  it('[WEB-PRIV-003] downloads the account export as a JSON file without browser storage', () => {
    const settings = read('app', 'pages', 'settings.vue')
    expect(settings).toContain('label="Download my data"')
    expect(settings).toMatch(/await exportAccount\(\)/)
    expect(settings).toMatch(/downloadJson\(/)
    expect(settings).not.toMatch(/localStorage|sessionStorage/)
    expect(read('app', 'composables', 'useShieldApi.ts')).toMatch(/exportAccount: \(\) =>\s*api<AccountExportResponse>\('\/auth\/account\/export'\)/)

    const clicks: string[] = []
    const anchor = { href: '', download: '', click: () => clicks.push(anchor.download) }
    const revoke = vi.fn()
    downloadJson({ account: { email: 'ada@example.com' } }, EXPORT_FILE_NAME, {
      createElement: () => anchor,
      createObjectURL: () => 'blob:export',
      revokeObjectURL: revoke
    })
    expect(EXPORT_FILE_NAME).toBe('ai-shield-account-export.json')
    expect(clicks).toEqual(['ai-shield-account-export.json'])
    expect(anchor.href).toBe('blob:export')
    expect(revoke).toHaveBeenCalledWith('blob:export')
  })
})
