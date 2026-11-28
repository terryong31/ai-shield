import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { CHANGELOG_ENTRIES } from '../app/data/changelog'
import { landingHeaders } from '../app/utils/securityHeaders'
import en from '../i18n/locales/en'
import ms from '../i18n/locales/ms'

const landingRoot = resolve(__dirname, '..')
const read = (...parts: string[]) => readFileSync(resolve(landingRoot, ...parts), 'utf8')

function collectKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  const keys: string[] = []
  for (const [k, v] of Object.entries(obj).sort(([a], [b]) => a.localeCompare(b))) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      keys.push(...collectKeys(v as Record<string, unknown>, path))
    } else {
      keys.push(path)
    }
  }
  return keys
}

describe('Standalone landing site, bilingual legal pages, and changelog (spec 0060)', () => {
  it('[WEB-LAND-001] configures security headers, canonical/hreflang/OG metadata, and semantic landmarks', () => {
    const prod = landingHeaders(true)
    expect(prod['Strict-Transport-Security']).toBe('max-age=31536000; includeSubDomains')
    expect(prod['Content-Security-Policy']).toContain('default-src \'self\'')
    expect(prod['X-Frame-Options']).toBe('DENY')
    expect(prod['X-Content-Type-Options']).toBe('nosniff')
    expect(prod['Referrer-Policy']).toBe('strict-origin-when-cross-origin')
    expect(prod['Permissions-Policy']).toContain('camera=()')
    expect(prod['Cross-Origin-Opener-Policy']).toBe('same-origin')

    const dev = landingHeaders(false)
    expect(dev['Strict-Transport-Security']).toBeUndefined()
    expect(dev['Content-Security-Policy']).toContain('ws: wss:')

    const nuxtConfig = read('nuxt.config.ts')
    expect(nuxtConfig).toContain('@nuxtjs/i18n')
    expect(nuxtConfig).toContain('@nuxt/a11y')
    expect(nuxtConfig).toContain('https://ai-shield.my')

    expect(collectKeys(ms)).toEqual(collectKeys(en))

    expect(read('app', 'app.vue')).toContain('<NuxtRouteAnnouncer')
    expect(read('app', 'components', 'AppHeader.vue')).toContain('<UHeader')
    expect(read('app', 'layouts', 'default.vue')).toContain('<UMain')
    expect(read('app', 'components', 'AppFooter.vue')).toContain('<UFooter')

    for (const page of ['index.vue', 'pricing.vue', 'changelog.vue']) {
      expect(read('app', 'pages', page), page).toContain('useSeoMeta')
    }
    for (const page of ['privacy', 'terms', 'refund']) {
      expect(read('app', 'pages', `${page}.vue`), page).toContain(`<LegalPage slug="${page}"`)
    }
    expect(read('app', 'components', 'LegalPage.vue')).toContain('useSeoMeta')
  })

  it('[WEB-LAND-002] provides bilingual EN/BM privacy policy with Spec 0058 disclosures, Resend, BYOK, Vercel Analytics, and 72h PDPC breach notice', () => {
    for (const locale of ['en', 'ms']) {
      const privacy = read('content', locale, 'privacy.md')
      expect(privacy, locale).toContain('shield_player_session')
      expect(privacy, locale).toContain('shield_anon_draft')
      expect(privacy, locale).toContain('Resend')
      expect(privacy, locale).toContain('OpenAI')
      expect(privacy, locale).toContain('Anthropic')
      expect(privacy, locale).toContain('OpenRouter')
      expect(privacy, locale).toContain('Vercel')
      expect(privacy, locale).toContain('support@ai-shield.my')
      expect(privacy, locale).toMatch(/effective: \d{4}-\d{2}-\d{2}/)
      expect(privacy, locale).toContain('version:')
    }

    const enPrivacy = read('content', 'en', 'privacy.md')
    const msPrivacy = read('content', 'ms', 'privacy.md')
    expect(enPrivacy).toContain('72 hours')
    expect(enPrivacy).toContain('Personal Data Protection Commissioner')
    expect(msPrivacy).toContain('72 jam')
    expect(msPrivacy).toContain('Pesuruhjaya Perlindungan Data Peribadi')
  })

  it('[WEB-LAND-003] provides Terms of Service, statutory-minimum Refund Policy, and RFC 9116 security.txt', () => {
    const terms = read('content', 'en', 'terms.md')
    expect(terms).toContain('Terry Ong')
    expect(terms).toContain('Malaysia')
    expect(terms).toContain('USD')

    const refund = read('content', 'en', 'refund.md')
    expect(refund).toContain('Consumer Protection Act 1999')
    expect(refund).toContain('3 business days')
    expect(refund).toContain('5–10 business days')
    expect(refund).toContain('support@ai-shield.my')

    for (const page of ['terms', 'refund']) {
      expect(read('content', 'ms', `${page}.md`), page).toContain('support@ai-shield.my')
    }

    const securityTxt = read('public', '.well-known', 'security.txt')
    expect(securityTxt).toContain('Contact: mailto:security@ai-shield.my')
    expect(securityTxt).toContain('Canonical: https://ai-shield.my/.well-known/security.txt')
    expect(securityTxt).toContain('Expires:')
  })

  it('[WEB-LAND-004] renders reverse-chronological client-facing changelog entries', () => {
    const changelog = read('app', 'pages', 'changelog.vue')
    expect(changelog).toContain('UChangelogVersions')
    expect(changelog).toContain('UChangelogVersion')

    expect(CHANGELOG_ENTRIES.length).toBeGreaterThanOrEqual(3)
    for (const [index, entry] of CHANGELOG_ENTRIES.entries()) {
      expect(entry.version.trim()).not.toBe('')
      expect(entry.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(entry.badge.trim()).not.toBe('')
      expect(entry.title.en.trim()).not.toBe('')
      expect(entry.title.ms.trim()).not.toBe('')
      expect(entry.description.en.trim()).not.toBe('')
      expect(entry.description.ms.trim()).not.toBe('')
      if (index > 0) {
        expect(entry.date <= CHANGELOG_ENTRIES[index - 1]!.date).toBe(true)
      }
    }
  })

  it('[WEB-ACCESS-001] configures automated axe-core WCAG 2.2 AA Playwright audit across all EN and MS landing routes', () => {
    expect(existsSync(resolve(landingRoot, 'playwright.config.ts'))).toBe(true)
    expect(existsSync(resolve(landingRoot, 'test', 'a11y.spec.ts'))).toBe(true)
    const a11y = read('test', 'a11y.spec.ts')
    expect(a11y).toContain('@axe-core/playwright')
    expect(a11y).toContain('wcag22aa')
    for (const route of [
      '/', '/pricing', '/changelog', '/privacy', '/terms', '/refund',
      '/ms', '/ms/pricing', '/ms/changelog', '/ms/privacy', '/ms/terms', '/ms/refund'
    ]) {
      expect(a11y).toContain(`'${route}'`)
    }
  })
})
