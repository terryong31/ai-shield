import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { emailChangeSchema } from '../app/utils/account'
import { scrubAnalyticsEvent } from '../app/utils/analytics'
import { isAllowedCheckoutUrl } from '../app/utils/billing'
import { authLinkErrorMessage } from '../app/utils/playerAuth'
import { securityRouteRules } from '../app/utils/securityHeaders'
import { serializeJsonLd } from '../app/utils/seo'
import { MAX_PROXY_BODY_BYTES, proxyToGateway } from '../shared/utils/apiProxy'

const root = join(import.meta.dirname, '..')
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf-8')

const WEB = 'https://ai-shield.test'
const TARGET = 'http://gateway.local'

function countingFetch() {
  const calls: string[] = []
  const impl = (async (url: string) => {
    calls.push(url)
    return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
  }) as unknown as typeof fetch
  return { calls, impl }
}

describe('Frontend security hardening (spec 0053)', () => {
  it('[WEB-SEC-001] sets the baseline security headers on every route', () => {
    const rules = securityRouteRules(false)
    const all = rules['/**']!.headers!
    const csp = all['Content-Security-Policy']!
    for (const directive of ['default-src \'self\'', 'object-src \'none\'', 'base-uri \'self\'', 'frame-ancestors \'none\'']) {
      expect(csp).toContain(directive)
    }
    expect(all['X-Frame-Options']).toBe('DENY')
    expect(all['X-Content-Type-Options']).toBe('nosniff')
    expect(all['Referrer-Policy']).toBe('strict-origin-when-cross-origin')
    expect(all['Permissions-Policy']).toContain('camera=()')
    expect(all['Cross-Origin-Opener-Policy']).toBe('same-origin')
    expect(all['Strict-Transport-Security']).toBeUndefined()

    expect(securityRouteRules(true)['/**']!.headers!['Strict-Transport-Security']).toBe('max-age=31536000; includeSubDomains')
    expect(rules['/auth/**']!.headers).toMatchObject({ 'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store' })
    expect(read('nuxt.config.ts')).toMatch(/routeRules: securityRouteRules\(/)

    // Nuxt Icon fetches icons outside the bundle from the Iconify API; dev analytics load a debug script.
    const prodCsp = securityRouteRules(true)['/**']!.headers!['Content-Security-Policy']!
    expect(prodCsp).toContain('https://api.iconify.design')
    expect(prodCsp).not.toContain('va.vercel-scripts.com')
    expect(csp).toContain('https://va.vercel-scripts.com')
  })

  it('[WEB-SEC-002] never caches the console, settings or plans pages', () => {
    const rules = securityRouteRules(true)
    for (const path of ['/_console', '/_console/**', '/settings', '/plans']) {
      expect(rules[path]?.headers?.['Cache-Control']).toBe('no-store')
    }
  })

  it('[WEB-SEC-003] shows only allowlisted messages for auth link errors', () => {
    const fallback = 'This confirmation link is invalid or has expired.'
    expect(authLinkErrorMessage('otp_expired', fallback)).toMatch(/expired/i)
    expect(authLinkErrorMessage('Call attacker', fallback)).toBe(fallback)
    expect(authLinkErrorMessage(undefined, fallback)).toBe(fallback)
    for (const page of ['confirmed.vue', 'reset-password.vue']) {
      const source = read('app', 'pages', 'auth', page)
      expect(source).not.toContain('error_description')
      expect(source).toMatch(/authLinkErrorMessage\(errorCode, /)
    }
  })

  it('[WEB-SEC-004] strips the query from analytics events on auth pages', () => {
    const scrubbed = scrubAnalyticsEvent({ type: 'pageview' as const, url: 'https://ai-shield.test/auth/confirmed?code=secret&flow=123' })
    expect(scrubbed?.url).toBe('https://ai-shield.test/auth/confirmed')
    const reset = scrubAnalyticsEvent({ type: 'pageview' as const, url: 'https://ai-shield.test/auth/reset-password?token_hash=secret' })
    expect(reset?.url).not.toContain('secret')
    const game = scrubAnalyticsEvent({ type: 'pageview' as const, url: 'https://ai-shield.test/game?level=easy-1' })
    expect(game?.url).toBe('https://ai-shield.test/game?level=easy-1')

    const plugin = read('app', 'plugins', 'analytics.client.ts')
    expect(plugin).toMatch(/injectAnalytics\(\{ beforeSend: scrubAnalyticsEvent \}\)/)
    expect(plugin).toMatch(/injectSpeedInsights\(\{ beforeSend: scrubAnalyticsEvent \}\)/)
    expect(read('nuxt.config.ts')).not.toMatch(/'@vercel\/analytics'|'@vercel\/speed-insights'/)
  })

  it('[WEB-SEC-005] rejects proxy bodies over 2 MiB without calling the gateway', async () => {
    expect(MAX_PROXY_BODY_BYTES).toBe(2 * 1024 * 1024)
    const declared = countingFetch()
    const byHeader = await proxyToGateway(new Request(`${WEB}/api/v1/game/train`, {
      method: 'POST',
      headers: { 'content-length': String(MAX_PROXY_BODY_BYTES + 1), 'sec-fetch-site': 'same-origin' },
      body: 'x'
    }), TARGET, declared.impl)
    expect(byHeader.status).toBe(413)
    expect(await byHeader.json()).toEqual({ detail: 'Request body too large.' })
    expect(declared.calls).toEqual([])

    const streamed = countingFetch()
    const byBody = await proxyToGateway(new Request(`${WEB}/api/v1/game/train`, {
      method: 'POST',
      headers: { 'sec-fetch-site': 'same-origin' },
      body: new Uint8Array(MAX_PROXY_BODY_BYTES + 1)
    }), TARGET, streamed.impl)
    expect(byBody.status).toBe(413)
    expect(streamed.calls).toEqual([])
  })

  it('[WEB-SEC-006] blocks same-site, cross-site and unlabelled state-changing requests', async () => {
    for (const site of ['same-site', 'cross-site']) {
      for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
        const { calls, impl } = countingFetch()
        const res = await proxyToGateway(new Request(`${WEB}/api/v1/game/run`, {
          method,
          headers: { 'sec-fetch-site': site },
          body: '{}'
        }), TARGET, impl)
        expect(res.status).toBe(403)
        expect(await res.json()).toEqual({ detail: 'Cross-site request blocked.' })
        expect(calls).toEqual([])
      }
    }
    const { calls, impl } = countingFetch()
    const bare = await proxyToGateway(new Request(`${WEB}/api/v1/game/run`, { method: 'POST', body: '{}' }), TARGET, impl, {
      requireProxyTrust: true,
      clientIpHeader: 'x-vercel-forwarded-for',
      proxySecret: 'secret',
      clientIp: '203.0.113.9'
    })
    expect(bare.status).toBe(403)
    expect(calls).toEqual([])

    // Stripe posts its webhook server to server, with no Origin or Sec-Fetch-Site.
    const stripe = countingFetch()
    const webhook = await proxyToGateway(new Request(`${WEB}/api/v1/billing/webhook`, {
      method: 'POST',
      headers: { 'stripe-signature': 't=1,v1=abc' },
      body: '{}'
    }), TARGET, stripe.impl, {
      requireProxyTrust: true,
      clientIpHeader: 'x-vercel-forwarded-for',
      proxySecret: 'secret',
      clientIp: '203.0.113.9'
    })
    expect(webhook.status).toBe(200)
    expect(stripe.calls).toEqual([`${TARGET}/api/v1/billing/webhook`])
  })

  it('[WEB-SEC-007] asks the admin to type CLEAR before clearing the scoreboard', () => {
    const page = read('app', 'pages', 'console', 'index.vue')
    expect(page).toMatch(/@click="isClearOpen = true"/)
    expect(page).toMatch(/:disabled="clearConfirm !== 'CLEAR'"/)
    expect(page).toMatch(/const handleClearScores = async \(\) => \{\s*if \(clearConfirm\.value !== 'CLEAR'\) return/)
  })

  it('[WEB-SEC-008] loads scores only after admin access is granted', () => {
    const page = read('app', 'pages', 'console', 'index.vue')
    expect(page).not.toMatch(/onMounted\(loadScores\)/)
    expect(page).toMatch(/watch\(\s*\(\) => access\.value\.allowed,\s*\(allowed\) => \{\s*if \(allowed\) void loadScores\(\)/)
    expect(page).toMatch(/const loadScores = async \(\) => \{\s*if \(!access\.value\.allowed\) return/)
  })

  it('[WEB-SEC-009] only follows https checkout.stripe.com redirects', () => {
    expect(isAllowedCheckoutUrl('https://checkout.stripe.com/c/pay/cs_test_1')).toBe(true)
    for (const url of ['javascript:alert(1)', 'http://checkout.stripe.com/c/pay', 'https://evil.example/c/pay', 'https://checkout.stripe.com.evil.example/x', 'not a url']) {
      expect(isAllowedCheckoutUrl(url)).toBe(false)
    }
    expect(read('app', 'pages', 'plans.vue')).toMatch(/if \(!isAllowedCheckoutUrl\(url\)\)/)
  })

  it('[WEB-SEC-010] escapes < in JSON-LD', () => {
    const out = serializeJsonLd({ name: '</script><script>alert(1)</script>' })
    expect(out).not.toContain('<')
    expect(out).toContain('\\u003c/script>')
    expect(JSON.parse(out)).toEqual({ name: '</script><script>alert(1)</script>' })
    expect(read('app', 'app.vue')).toMatch(/innerHTML: serializeJsonLd\(/)
  })

  it('[WEB-SEC-011] does not list the console in robots.txt', () => {
    expect(read('public', 'robots.txt')).not.toContain('/_console')
  })

  it('[WEB-SEC-012] validates the change-email form and pins every package', () => {
    expect(emailChangeSchema.safeParse({ email: 'ada@example.com', password: 'secret' }).success).toBe(true)
    expect(emailChangeSchema.safeParse({ email: 'not-an-email', password: 'secret' }).success).toBe(false)
    expect(emailChangeSchema.safeParse({ email: 'ada@example.com', password: '' }).success).toBe(false)
    expect(read('app', 'pages', 'settings.vue')).toMatch(/:schema="emailChangeSchema"/)
    const pkg = JSON.parse(read('package.json')) as { dependencies: Record<string, string>, devDependencies: Record<string, string> }
    for (const version of [...Object.values(pkg.dependencies), ...Object.values(pkg.devDependencies)]) {
      expect(version).not.toBe('latest')
    }
  })
})
