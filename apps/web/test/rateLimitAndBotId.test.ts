import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import * as apiProxy from '../shared/utils/apiProxy'
import { errorDetail } from '../app/utils/account'

const ROOT = join(import.meta.dirname, '..')
const WEB = 'https://shield-web.example'
const TARGET = 'http://gateway.internal:8000'

type ProxyFn = (
  req: Request,
  target: string,
  fetchImpl?: typeof fetch,
  options?: {
    clientIp?: string
    clientIpHeader?: string
    proxySecret?: string
    requireProxyTrust?: boolean
    checkBot?: () => Promise<{ isBot: boolean }>
  }
) => Promise<Response>

describe('rate limiting, client IP and BotID (spec 0043)', () => {
  it('[WEB-RATE-001] forwards x-shield-client-ip and x-shield-proxy-secret when provided', async () => {
    let forwarded = new Headers()
    const fakeFetch: typeof fetch = async (_url, init) => {
      forwarded = new Headers(init?.headers)
      return new Response('ok', { status: 200 })
    }

    const res = await (apiProxy.proxyToGateway as ProxyFn)(
      new Request(`${WEB}/api/v1/game/levels`),
      TARGET,
      fakeFetch,
      { clientIp: '203.0.113.7', proxySecret: 's3cret' }
    )
    expect(res.status).toBe(200)
    expect(forwarded.get('x-shield-client-ip')).toBe('203.0.113.7')
    expect(forwarded.get('x-shield-proxy-secret')).toBe('s3cret')
  })

  it('[WEB-RATE-002] strips client-supplied x-shield-client-ip and x-shield-proxy-secret', async () => {
    let forwarded = new Headers()
    const fakeFetch: typeof fetch = async (_url, init) => {
      forwarded = new Headers(init?.headers)
      return new Response('ok', { status: 200 })
    }

    await (apiProxy.proxyToGateway as ProxyFn)(
      new Request(`${WEB}/api/v1/game/levels`, {
        headers: {
          'x-shield-client-ip': '198.51.100.99',
          'x-shield-proxy-secret': 'forged'
        }
      }),
      TARGET,
      fakeFetch
    )
    expect(forwarded.get('x-shield-client-ip')).toBeNull()
    expect(forwarded.get('x-shield-proxy-secret')).toBeNull()
  })

  it('[WEB-RATE-003] extracts the first IP entry from the configured header or falls back', () => {
    const fn = (apiProxy as Record<string, unknown>).clientIpFromHeaders as
      | ((headers: Headers, headerName: string | undefined, fallback: string) => string)
      | undefined
    expect(typeof fn).toBe('function')
    const h = new Headers({ 'x-vercel-forwarded-for': '203.0.113.7, 10.0.0.1' })
    expect(fn!(h, 'x-vercel-forwarded-for', '127.0.0.1')).toBe('203.0.113.7')
    expect(fn!(h, undefined, '127.0.0.1')).toBe('127.0.0.1')
    expect(fn!(new Headers(), 'x-vercel-forwarded-for', '127.0.0.1')).toBe('127.0.0.1')
  })

  it('[WEB-RATE-004] formats 429 rate-limit responses to surface the gateway detail', () => {
    expect(errorDetail({ statusCode: 429, data: { detail: 'Too many requests. Try again in 42 seconds.' } }))
      .toBe('Too many requests. Try again in 42 seconds.')
    expect(errorDetail({})).toBe('Something went wrong. Try again.')

    const playerAuthSource = readFileSync(join(ROOT, 'app', 'composables', 'usePlayerAuth.ts'), 'utf-8')
    const gameSource = readFileSync(join(ROOT, 'app', 'pages', 'game.vue'), 'utf-8')
    expect(playerAuthSource).toContain('errorDetail')
    expect(gameSource).toContain('errorDetail')
  })

  it('[WEB-BOTID-001] defines the 5 BOTID_PROTECTED_ROUTES and passes them to initBotId in botid.client.ts', async () => {
    const botidMod = await import('../shared/utils/botid')
    expect(botidMod.BOTID_PROTECTED_ROUTES).toEqual([
      { path: '/api/v1/auth/anonymous', method: 'POST' },
      { path: '/api/v1/auth/register', method: 'POST' },
      { path: '/api/v1/auth/login', method: 'POST' },
      { path: '/api/v1/game/run', method: 'POST' },
      { path: '/api/v1/game/train', method: 'POST' }
    ])
    const pluginSource = readFileSync(join(ROOT, 'app', 'plugins', 'botid.client.ts'), 'utf-8')
    expect(pluginSource).toContain('botid/client/core')
    expect(pluginSource).toContain('initBotId')
    expect(pluginSource).toContain('BOTID_PROTECTED_ROUTES')
  })

  it('[WEB-BOTID-002] returns 403 and skips fetch when checkBot reports isBot: true', async () => {
    const fakeFetch = vi.fn<typeof fetch>()
    const res = await (apiProxy.proxyToGateway as ProxyFn)(
      new Request(`${WEB}/api/v1/game/run`, { method: 'POST', body: '{}' }),
      TARGET,
      fakeFetch,
      { checkBot: async () => ({ isBot: true }), proxySecret: 's3cret' }
    )
    expect(res.status).toBe(403)
    expect(await res.json()).toEqual({ detail: 'Request blocked.' })
    expect(fakeFetch).not.toHaveBeenCalled()
  })

  it('[WEB-BOTID-003] sets x-shield-botid: pass and proxy secret when checkBot returns isBot: false', async () => {
    let forwarded = new Headers()
    const fakeFetch: typeof fetch = async (_url, init) => {
      forwarded = new Headers(init?.headers)
      return new Response('ok', { status: 200 })
    }
    const res = await (apiProxy.proxyToGateway as ProxyFn)(
      new Request(`${WEB}/api/v1/game/run`, { method: 'POST', body: '{}' }),
      TARGET,
      fakeFetch,
      { checkBot: async () => ({ isBot: false }), proxySecret: 's3cret' }
    )
    expect(res.status).toBe(200)
    expect(forwarded.get('x-shield-botid')).toBe('pass')
    expect(forwarded.get('x-shield-proxy-secret')).toBe('s3cret')
  })

  it('[WEB-BOTID-004] skips checkBot and omits x-shield-botid on unprotected routes', async () => {
    const isProtected = (apiProxy as Record<string, unknown>).isBotIdProtected as
      | ((method: string, pathname: string) => boolean)
      | undefined
    expect(typeof isProtected).toBe('function')
    expect(isProtected!('GET', '/api/v1/game/levels')).toBe(false)
    expect(isProtected!('GET', '/api/v1/game/run')).toBe(false)
    expect(isProtected!('POST', '/api/v1/game/run')).toBe(true)

    const checkBot = vi.fn(async () => ({ isBot: false }))
    let forwarded = new Headers()
    const fakeFetch: typeof fetch = async (_url, init) => {
      forwarded = new Headers(init?.headers)
      return new Response('ok', { status: 200 })
    }

    await (apiProxy.proxyToGateway as ProxyFn)(new Request(`${WEB}/api/v1/game/levels`), TARGET, fakeFetch, { checkBot })
    await (apiProxy.proxyToGateway as ProxyFn)(new Request(`${WEB}/api/v1/game/run`), TARGET, fakeFetch, { checkBot })
    expect(checkBot).not.toHaveBeenCalled()
    expect(forwarded.get('x-shield-botid')).toBeNull()
  })

  it('[WEB-BOTID-005] always strips client-supplied x-shield-botid: pass before proxy checks', async () => {
    let forwarded = new Headers()
    const fakeFetch: typeof fetch = async (_url, init) => {
      forwarded = new Headers(init?.headers)
      return new Response('ok', { status: 200 })
    }

    await (apiProxy.proxyToGateway as ProxyFn)(
      new Request(`${WEB}/api/v1/game/levels`, { headers: { 'x-shield-botid': 'pass' } }),
      TARGET,
      fakeFetch,
      { checkBot: async () => ({ isBot: false }) }
    )
    expect(forwarded.get('x-shield-botid')).toBeNull()
  })

  it('[WEB-BOTID-006] returns 503 and skips fetch when checkBot throws', async () => {
    const fakeFetch = vi.fn<typeof fetch>()
    const res = await (apiProxy.proxyToGateway as ProxyFn)(
      new Request(`${WEB}/api/v1/game/run`, { method: 'POST', body: '{}' }),
      TARGET,
      fakeFetch,
      { checkBot: async () => { throw new Error('botid failed') } }
    )
    expect(res.status).toBe(503)
    expect(await res.json()).toEqual({ detail: 'Bot check unavailable. Try again.' })
    expect(fakeFetch).not.toHaveBeenCalled()
  })

  it('[WEB-RATE-005] fails closed with 503 when production proxy lacks clientIpHeader, proxySecret, or clientIp', async () => {
    const fakeFetch = vi.fn<typeof fetch>(async () => new Response('ok', { status: 200 }))
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      for (const opts of [
        { requireProxyTrust: true, clientIpHeader: '', proxySecret: 's3cret', clientIp: '1.2.3.4' },
        { requireProxyTrust: true, clientIpHeader: 'x-vercel-forwarded-for', proxySecret: '   ', clientIp: '1.2.3.4' },
        { requireProxyTrust: true, clientIpHeader: 'x-vercel-forwarded-for', proxySecret: 's3cret', clientIp: '' },
        { requireProxyTrust: true }
      ]) {
        const res = await (apiProxy.proxyToGateway as ProxyFn)(
          new Request(`${WEB}/api/v1/game/levels`),
          TARGET,
          fakeFetch,
          opts
        )
        expect(res.status).toBe(503)
        expect(await res.json()).toEqual({ detail: 'Gateway unavailable.' })
      }
      expect(fakeFetch).not.toHaveBeenCalled()
      expect(errSpy).toHaveBeenCalledTimes(4)

      const ok = await (apiProxy.proxyToGateway as ProxyFn)(
        new Request(`${WEB}/api/v1/game/levels`),
        TARGET,
        fakeFetch,
        {
          requireProxyTrust: true,
          clientIpHeader: 'x-vercel-forwarded-for',
          proxySecret: 's3cret',
          clientIp: '1.2.3.4'
        }
      )
      expect(ok.status).toBe(200)
      expect(fakeFetch).toHaveBeenCalledTimes(1)

      const routeSource = readFileSync(join(ROOT, 'server', 'routes', 'api', 'v1', '[...path].ts'), 'utf-8')
      expect(routeSource).toContain('requireProxyTrust')
      expect(routeSource).toContain('clientIpHeader')
    } finally {
      errSpy.mockRestore()
    }
  })

  it('[WEB-RATE-006] defaults clientIpHeader to x-vercel-forwarded-for and avoids socket IP fallback in production', () => {
    const nuxtConfig = readFileSync(join(ROOT, 'nuxt.config.ts'), 'utf-8')
    expect(nuxtConfig).toMatch(/clientIpHeader:\s*'x-vercel-forwarded-for'/)

    const envExample = readFileSync(join(ROOT, '.env.example'), 'utf-8')
    expect(envExample).toMatch(/^NUXT_CLIENT_IP_HEADER=x-vercel-forwarded-for$/m)

    const routeSource = readFileSync(join(ROOT, 'server', 'routes', 'api', 'v1', '[...path].ts'), 'utf-8')
    expect(routeSource).toContain('requireProxyTrust ? \'\'')
  })
})
