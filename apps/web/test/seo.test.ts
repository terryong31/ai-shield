import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { FALLBACK_CAMPAIGN_LEVELS } from '../app/utils/campaignSelect'
import { TWITTER_CARD_PATH, buildGameJsonLd, buildPageSeo } from '../app/utils/seo'

const WEB_DIR = join(import.meta.dirname, '..')
const APP_DIR = join(WEB_DIR, 'app')
const PUBLIC_DIR = join(WEB_DIR, 'public')
const readApp = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')
const readPublic = (file: string) => readFileSync(join(PUBLIC_DIR, file), 'utf-8')

const ALL_PAGES: string[][] = [
  ['pages', 'index.vue'],
  ['pages', 'game.vue'],
  ['pages', 'plans.vue'],
  ['pages', 'settings.vue'],
  ['pages', 'auth', 'login.vue'],
  ['pages', 'auth', 'register.vue'],
  ['pages', 'auth', 'recover.vue'],
  ['pages', 'auth', 'confirmed.vue'],
  ['pages', 'auth', 'reset-password.vue'],
  ['pages', 'console', 'index.vue'],
  ['pages', 'console', 'settings.vue'],
  ['pages', '[...slug].vue']
]

const NOINDEX_PAGES: string[][] = [
  ['pages', 'settings.vue'],
  ['pages', 'auth', 'recover.vue'],
  ['pages', 'auth', 'confirmed.vue'],
  ['pages', 'auth', 'reset-password.vue'],
  ['pages', 'console', 'index.vue'],
  ['pages', 'console', 'settings.vue'],
  ['pages', '[...slug].vue']
]

const MAIN_LANDMARK_PAGES: string[][] = [
  ['pages', 'index.vue'],
  ['pages', 'plans.vue'],
  ['pages', 'settings.vue'],
  ['pages', 'auth', 'login.vue'],
  ['pages', 'auth', 'register.vue'],
  ['pages', 'auth', 'recover.vue'],
  ['pages', 'auth', 'confirmed.vue'],
  ['pages', 'auth', 'reset-password.vue'],
  ['pages', '[...slug].vue']
]

const H1_PAGES: string[][] = [
  ['pages', 'index.vue'],
  ['pages', 'game.vue'],
  ['pages', 'plans.vue'],
  ['pages', 'settings.vue']
]

describe('SEO metadata, Twitter card, sitemap, robots and llms.txt (spec 0016)', () => {
  it('[WEB-GAME-016] configures useSeoMeta, Twitter card, JSON-LD, semantic landmarks, sitemap.xml, robots.txt and llms.txt', () => {
    expect(TWITTER_CARD_PATH).toBe('/twitter-card.png')

    const indexed = buildPageSeo({
      title: 'Plans',
      description: 'Compare plans for ai-shield.',
      path: '/plans',
      siteUrl: 'https://shield.example.com/'
    })
    expect(indexed).toMatchObject({
      title: 'Plans',
      description: 'Compare plans for ai-shield.',
      ogTitle: 'Plans | ai-shield',
      ogDescription: 'Compare plans for ai-shield.',
      ogType: 'website',
      ogSiteName: 'ai-shield',
      ogUrl: 'https://shield.example.com/plans',
      ogImage: 'https://shield.example.com/twitter-card.png',
      ogImageAlt: expect.any(String),
      twitterCard: 'summary_large_image',
      twitterTitle: 'Plans | ai-shield',
      twitterDescription: 'Compare plans for ai-shield.',
      twitterImage: 'https://shield.example.com/twitter-card.png',
      twitterImageAlt: expect.any(String),
      robots: 'index, follow'
    })

    const hidden = buildPageSeo({
      title: 'Settings',
      description: 'Account settings.',
      path: '/settings',
      siteUrl: 'https://shield.example.com',
      noindex: true
    })
    expect(hidden.robots).toBe('noindex, nofollow')

    const jsonLd = buildGameJsonLd('https://shield.example.com')
    expect(jsonLd['@context']).toBe('https://schema.org')
    expect(jsonLd['@type']).toBe('VideoGame')
    expect(jsonLd.name).toBe('ai-shield')
    expect(jsonLd.applicationCategory).toBe('GameApplication')
    expect(jsonLd.image).toBe('https://shield.example.com/twitter-card.png')

    const nuxtConfig = readFileSync(join(WEB_DIR, 'nuxt.config.ts'), 'utf-8')
    expect(nuxtConfig).toContain('lang: \'en\'')
    expect(nuxtConfig).toContain('titleTemplate')
    expect(nuxtConfig).toContain('/favicon.svg')

    const appSource = readApp('app.vue')
    expect(appSource).toContain('useSeoMeta(')
    expect(appSource).toContain('useHead(')
    expect(appSource).toContain('canonical')
    expect(appSource).toContain('application/ld+json')
    expect(appSource).toContain('buildGameJsonLd')

    for (const parts of ALL_PAGES) {
      const source = readApp(...parts)
      expect(source, parts.join('/')).toContain('useSeoMeta(')
    }

    for (const parts of NOINDEX_PAGES) {
      const source = readApp(...parts)
      expect(source, parts.join('/')).toMatch(/noindex:\s*true|noindex,\s*nofollow/)
    }

    const gameSource = readApp('pages', 'game.vue')
    expect(gameSource).toMatch(/title:\s*\(\)\s*=>/)
    expect(gameSource).toMatch(/description:\s*\(\)\s*=>/)
    expect(gameSource).toMatch(/<h1[^>]*>\s*\{\{\s*currentLevel\.title\s*\}\}\s*<\/h1>/)

    for (const parts of MAIN_LANDMARK_PAGES) {
      const source = readApp(...parts)
      expect(source, parts.join('/')).toContain('<main')
    }

    for (const parts of H1_PAGES) {
      const source = readApp(...parts)
      expect(source, parts.join('/')).toContain('<h1')
    }

    expect(existsSync(join(PUBLIC_DIR, 'twitter-card.png'))).toBe(true)
    const pngBytes = readFileSync(join(PUBLIC_DIR, 'twitter-card.png'))
    expect(pngBytes.subarray(0, 8)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
    expect(pngBytes.readUInt32BE(16)).toBe(1200)
    expect(pngBytes.readUInt32BE(20)).toBe(630)

    expect(existsSync(join(PUBLIC_DIR, 'twitter-card.svg'))).toBe(true)
    const twitterCard = readPublic('twitter-card.svg')
    expect(twitterCard).toContain('<svg')
    expect(twitterCard).toContain('viewBox="0 0 1200 630"')
    expect(twitterCard).toContain('ai-shield')

    expect(existsSync(join(PUBLIC_DIR, 'favicon.svg'))).toBe(true)
    expect(readPublic('favicon.svg')).toContain('<svg')

    expect(existsSync(join(PUBLIC_DIR, 'robots.txt'))).toBe(true)
    const robots = readPublic('robots.txt')
    expect(robots).toContain('User-agent: *')
    expect(robots).toContain('Allow: /')
    expect(robots).toContain('Disallow: /_console')
    expect(robots).toContain('Disallow: /settings')
    expect(robots).toContain('Sitemap:')

    expect(existsSync(join(PUBLIC_DIR, 'sitemap.xml'))).toBe(true)
    const sitemap = readPublic('sitemap.xml')
    expect(sitemap).toContain('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    expect(sitemap).toContain('<loc>')
    expect(sitemap).toContain('/game')
    expect(sitemap).toContain('/plans')
    expect(sitemap).not.toContain('/_console')

    expect(existsSync(join(PUBLIC_DIR, 'llms.txt'))).toBe(true)
    const llms = readPublic('llms.txt')
    expect(llms.startsWith('# ai-shield')).toBe(true)
    expect(llms).toContain('\n> ')
    expect(llms).toContain('## Pages')
    expect(llms).toContain('## Game Levels')
    expect(llms).toContain('## Defence Tools')
    expect(llms).toContain('## Optional')
  })

  it('[WEB-GAME-017] sitemap.xml, robots.txt and llms.txt use the production site and match the current pages and levels', () => {
    const site = 'https://ai-shield-delta.vercel.app'
    const [sitemap, robots, llms] = ['sitemap.xml', 'robots.txt', 'llms.txt'].map(readPublic) as [string, string, string]
    for (const file of [sitemap, robots, llms]) expect(file).not.toContain('localhost')

    const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1]!)
    const levelUrls = FALLBACK_CAMPAIGN_LEVELS.map(level => `${site}/game?level=${level.id}`)
    expect(levelUrls.length).toBeGreaterThan(20)
    expect(new Set(urls)).toEqual(new Set([
      ...['/', '/game', '/plans', '/auth/login', '/auth/register'].map(path => `${site}${path}`),
      ...levelUrls
    ]))

    for (const path of ['/_console', '/settings', '/auth/recover', '/auth/confirmed', '/auth/reset-password', '/api/']) {
      expect(robots).toContain(`Disallow: ${path}`)
    }
    // A crawler follows only its own group, so every named bot shares the one group of rules.
    expect(robots.match(/Disallow: \/settings/g)).toHaveLength(1)
    for (const bot of ['*', 'GPTBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended']) {
      expect(robots).toContain(`User-agent: ${bot}`)
    }
    expect(robots).toContain(`Sitemap: ${site}/sitemap.xml`)

    for (const level of FALLBACK_CAMPAIGN_LEVELS) {
      expect(llms).toContain(`[${level.title}](${site}/game?level=${level.id})`)
    }
    expect(llms).toContain('$5')
    expect(llms).toContain('30 days')
  })
})
