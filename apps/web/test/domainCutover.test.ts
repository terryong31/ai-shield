import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const webRoot = resolve(__dirname, '..')
const read = (...parts: string[]) => readFileSync(resolve(webRoot, ...parts), 'utf8')

describe('Custom domain cutover (spec 0061)', () => {
  it('[WEB-DOM-001] links to ai-shield.my legal pages, requires register consent checkbox, and discloses USD + refund on /plans', () => {
    const nuxtConfig = read('nuxt.config.ts')
    expect(nuxtConfig).toContain('landingUrl')

    for (const parts of [
      ['app', 'pages', 'auth', 'register.vue'],
      ['app', 'pages', 'plans.vue'],
      ['app', 'pages', 'settings.vue']
    ]) {
      const src = read(...parts)
      expect(src, parts.join('/')).toContain('/privacy')
      expect(src, parts.join('/')).toContain('/terms')
      expect(src, parts.join('/')).toContain('landingUrl')
    }

    const register = read('app', 'pages', 'auth', 'register.vue')
    expect(register).toContain('<UCheckbox')
    expect(register).toContain('acceptedTerms')

    const plans = read('app', 'pages', 'plans.vue')
    expect(plans).toContain('USD')
    expect(plans).toContain('/refund')
    expect(plans).toMatch(/immediately/i)
  })

  it('[WEB-DOM-002] returns 308 permanent redirects from /privacy and /terms to ai-shield.my', () => {
    expect(existsSync(resolve(webRoot, 'app', 'pages', 'privacy.vue'))).toBe(false)
    const rules = read('app', 'utils', 'securityHeaders.ts')
    expect(rules).toContain('\'/privacy\'')
    expect(rules).toContain('\'/terms\'')
    expect(rules).toContain('https://ai-shield.my/privacy')
    expect(rules).toContain('https://ai-shield.my/terms')
    expect(rules).toContain('308')
  })

  it('[WEB-DOM-003] updates robots.txt, sitemap.xml, llms.txt to play.ai-shield.my and adds security.txt', () => {
    for (const file of ['robots.txt', 'sitemap.xml', 'llms.txt']) {
      const content = read('public', file)
      expect(content, file).not.toContain('ai-shield-delta.vercel.app')
      expect(content, file).toContain('https://play.ai-shield.my')
    }
    expect(read('public', 'sitemap.xml')).not.toContain('/privacy</loc>')
    expect(read('public', 'llms.txt')).toContain('https://ai-shield.my/privacy')

    const securityTxt = read('public', '.well-known', 'security.txt')
    expect(securityTxt).toContain('Contact: mailto:security@ai-shield.my')
  })
})
