import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { EXPORT_FILE_NAME, downloadJson } from '../app/utils/account'

const WEB = join(import.meta.dirname, '..')
const read = (...parts: string[]) => readFileSync(join(WEB, ...parts), 'utf-8')

describe('Privacy policy and player data (spec 0058; canonical host moved to apps/landing in specs 0060/0061)', () => {
  it('[WEB-PRIV-001] renders the canonical privacy policy in apps/landing with Nuxt UI, every required section and index robots', () => {
    const landing = join(WEB, '..', 'landing')
    expect(readFileSync(join(landing, 'app', 'pages', 'privacy.vue'), 'utf-8')).toContain('<LegalPage slug="privacy"')
    const legalPage = readFileSync(join(landing, 'app', 'components', 'LegalPage.vue'), 'utf-8')
    expect(legalPage).toMatch(/robots: 'index, follow'/)
    expect(legalPage).toContain('<UPageHeader')
    expect(legalPage).toContain('<ContentRenderer')
    expect(legalPage).not.toMatch(/<table|<a\s/)
    for (const locale of ['en', 'ms']) {
      const policy = readFileSync(join(landing, 'content', locale, 'privacy.md'), 'utf-8')
      // Markdown tables render through Nuxt UI's prose table; no raw HTML in the content.
      expect(policy, locale).toMatch(/^\| --- \|/m)
      expect(policy, locale).not.toMatch(/<table|<a\s/)
      for (const name of ['shield_player_session', 'shield_auth_browser', 'shield_session_hint', 'shield_session', 'shield_anon_draft']) {
        expect(policy, `${locale} ${name}`).toContain(name)
      }
      for (const processor of ['Supabase', 'Vercel', 'Redis', 'Stripe', 'Resend', 'Google', 'Groq', 'TypeSafe']) {
        expect(policy, `${locale} ${processor}`).toContain(processor)
      }
    }
  })

  it('[WEB-PRIV-002] links the canonical privacy policy from every key page and lists it for crawlers', () => {
    for (const parts of [
      ['app', 'pages', 'auth', 'register.vue'],
      ['app', 'pages', 'plans.vue'],
      ['app', 'pages', 'settings.vue']
    ]) {
      expect(read(...parts), parts.join('/')).toContain('/privacy')
    }
    expect(read('app', 'pages', 'auth', 'register.vue')).toMatch(/Privacy Policy/)
    expect(read('app', 'pages', 'plans.vue')).toMatch(/Stripe[\s\S]{0,250}Privacy Policy|Privacy Policy[\s\S]{0,250}Stripe/)
    expect(readFileSync(join(WEB, '..', 'landing', 'public', 'sitemap.xml'), 'utf-8')).toContain('/privacy</loc>')
    expect(read('public', 'llms.txt')).toContain('/privacy')
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
