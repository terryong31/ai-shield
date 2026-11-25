import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { SHIELD_API_PREFIX } from '../app/utils/apiPaths'
import { proxyToGateway } from '../shared/utils/apiProxy'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const TARGET = 'https://gw.example'
const WEB = 'https://web.example'

type Call = { url: string, init: RequestInit }

const fakeFetch = (respond: () => Response | Promise<Response> = () => new Response('ok')) => {
  const calls: Call[] = []
  const impl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} })
    return respond()
  }) as typeof fetch
  return { calls, impl }
}

const sentHeaders = (call: Call) => new Headers(call.init.headers)

const sourceFiles = (dir: string): string[] =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.(ts|vue)$/.test(name) ? [path] : []
  })

const expectRejected = async (path: string) => {
  const { calls, impl } = fakeFetch()
  const res = await proxyToGateway(new Request(`${WEB}${path}`), TARGET, impl)
  expect(res.status, path).toBe(404)
  expect(calls, path).toHaveLength(0)
}

describe('same-origin API proxy (spec 0041)', () => {
  it('[WEB-PROXY-001] the client uses the same-origin /api/v1 prefix and never reads public.apiBaseUrl', () => {
    expect(SHIELD_API_PREFIX).toBe('/api/v1')
    for (const file of sourceFiles(APP_DIR)) {
      expect(readFileSync(file, 'utf-8'), file).not.toContain('apiBaseUrl')
    }
    expect(readFileSync(join(APP_DIR, 'composables', 'useShieldApi.ts'), 'utf-8')).toContain('SHIELD_API_PREFIX')
  })

  it('[WEB-PROXY-002] useLeaderboard reads only through useShieldApi and has no stream path', () => {
    const composable = readFileSync(join(APP_DIR, 'composables', 'useLeaderboard.ts'), 'utf-8')
    expect(composable).toContain('useShieldApi()')
    expect(composable).not.toContain('EventSource')
    expect(composable).not.toContain('/game/scores/stream')
    expect(composable).not.toMatch(/https?:\/\//)
  })

  it('[WEB-PROXY-003] forwards to the target with path and query, with or without a trailing slash', async () => {
    for (const target of [TARGET, `${TARGET}/`]) {
      const { calls, impl } = fakeFetch()
      await proxyToGateway(new Request(`${WEB}/api/v1/game/levels?difficulty=Easy`), target, impl)
      expect(calls[0]?.url).toBe('https://gw.example/api/v1/game/levels?difficulty=Easy')
    }
  })

  it('[WEB-PROXY-004] rejects dot-segment escapes without calling the gateway', async () => {
    for (const path of ['/api/v1/../admin', '/api/v1/%2e%2e/admin', '/api/v1/%2E%2E/admin', '/api/v1/.%2e/admin']) {
      await expectRejected(path)
    }
  })

  it('[WEB-PROXY-005] rejects empty segments, backslashes and encoded slashes', async () => {
    for (const path of ['/api/v1//evil.example/x', '/api/v1/..\\admin', '/api/v1/a%2fb', '/api/v1/a%5cb']) {
      await expectRejected(path)
    }
  })

  it('[WEB-PROXY-006] rejects paths outside the prefix', async () => {
    for (const path of ['/api/v1', '/api/v1evil', '/api/v2/x']) {
      await expectRejected(path)
    }
  })

  it('[WEB-PROXY-007] forwards method, body bytes, Cookie, Content-Type and Authorization', async () => {
    const { calls, impl } = fakeFetch()
    const body = JSON.stringify({ email: 'a@example.com' })
    await proxyToGateway(new Request(`${WEB}/api/v1/auth/login`, {
      method: 'POST',
      body,
      headers: { 'Cookie': 'shield_player=abc', 'Content-Type': 'application/json', 'Authorization': 'Bearer t' }
    }), TARGET, impl)
    const call = calls[0]!
    expect(call.init.method).toBe('POST')
    expect(new TextDecoder().decode(call.init.body as ArrayBuffer)).toBe(body)
    const headers = sentHeaders(call)
    expect(headers.get('cookie')).toBe('shield_player=abc')
    expect(headers.get('content-type')).toBe('application/json')
    expect(headers.get('authorization')).toBe('Bearer t')
  })

  it('[WEB-PROXY-008] sends GET and HEAD without a body', async () => {
    for (const method of ['GET', 'HEAD']) {
      const { calls, impl } = fakeFetch()
      await proxyToGateway(new Request(`${WEB}/api/v1/game/levels`, { method }), TARGET, impl)
      expect(calls[0]?.init.method).toBe(method)
      expect(calls[0]?.init.body ?? undefined).toBeUndefined()
    }
  })

  it('[WEB-PROXY-009] drops Host, hop-by-hop headers and Content-Length', async () => {
    const { calls, impl } = fakeFetch()
    await proxyToGateway(new Request(`${WEB}/api/v1/game/levels`, {
      headers: {
        'HOST': 'web.example', 'Connection': 'keep-alive', 'keep-alive': 'timeout=5',
        'Transfer-Encoding': 'chunked', 'UPGRADE': 'websocket', 'Te': 'trailers', 'Trailer': 'x',
        'Proxy-Authorization': 'Basic x', 'Content-Length': '0'
      }
    }), TARGET, impl)
    const headers = sentHeaders(calls[0]!)
    for (const name of ['host', 'connection', 'keep-alive', 'transfer-encoding', 'upgrade', 'te', 'trailer', 'proxy-authorization', 'content-length']) {
      expect(headers.has(name), name).toBe(false)
    }
  })

  it('[WEB-PROXY-010] drops client-supplied Forwarded and X-Forwarded-* headers', async () => {
    const { calls, impl } = fakeFetch()
    await proxyToGateway(new Request(`${WEB}/api/v1/game/levels`, {
      headers: { 'Forwarded': 'for=1.2.3.4', 'X-Forwarded-For': '1.2.3.4', 'x-forwarded-host': 'evil.example' }
    }), TARGET, impl)
    const headers = sentHeaders(calls[0]!)
    for (const name of ['forwarded', 'x-forwarded-for', 'x-forwarded-host']) {
      expect(headers.has(name), name).toBe(false)
    }
  })

  it('[WEB-PROXY-011] returns the gateway status, every Set-Cookie and the body', async () => {
    for (const status of [201, 401, 500]) {
      const { impl } = fakeFetch(() => new Response('{"ok":true}', {
        status,
        headers: [['set-cookie', 'a=1; HttpOnly'], ['set-cookie', 'b=2; Secure'], ['content-type', 'application/json']]
      }))
      const res = await proxyToGateway(new Request(`${WEB}/api/v1/auth/session`), TARGET, impl)
      expect(res.status).toBe(status)
      expect(res.headers.getSetCookie()).toEqual(['a=1; HttpOnly', 'b=2; Secure'])
      expect(await res.text()).toBe('{"ok":true}')
    }
  })

  it('[WEB-PROXY-012] strips Content-Encoding, Content-Length and Connection from the response', async () => {
    const { impl } = fakeFetch(() => new Response('decoded', {
      headers: { 'Content-Encoding': 'gzip', 'Content-Length': '7', 'Connection': 'close' }
    }))
    const res = await proxyToGateway(new Request(`${WEB}/api/v1/game/levels`), TARGET, impl)
    for (const name of ['content-encoding', 'content-length', 'connection']) {
      expect(res.headers.has(name), name).toBe(false)
    }
  })

  it('[WEB-PROXY-013] streams an event-stream body before the upstream closes', async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const stream = new ReadableStream<Uint8Array>({
      start: (c) => {
        controller = c
      }
    })
    controller.enqueue(new TextEncoder().encode('event: leaderboard\n\n'))
    const { impl } = fakeFetch(() => new Response(stream, {
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' }
    }))
    const res = await proxyToGateway(new Request(`${WEB}/api/v1/game/scores/stream`), TARGET, impl)
    const first = await res.body!.getReader().read()
    expect(new TextDecoder().decode(first.value)).toBe('event: leaderboard\n\n')
    expect(res.headers.get('content-type')).toBe('text/event-stream')
    expect(res.headers.get('cache-control')).toBe('no-cache')
    controller.close()
  })

  it('[WEB-PROXY-014] does not follow redirects', async () => {
    const { calls, impl } = fakeFetch(() => new Response(null, {
      status: 302, headers: { Location: 'https://elsewhere.example/' }
    }))
    const res = await proxyToGateway(new Request(`${WEB}/api/v1/auth/confirm`), TARGET, impl)
    expect(calls[0]?.init.redirect).toBe('manual')
    expect(res.status).toBe(302)
    expect(res.headers.get('location')).toBe('https://elsewhere.example/')
  })

  it('[WEB-PROXY-015] fails closed with a generic 502 on network errors and bad targets', async () => {
    const failing = (async () => {
      throw new TypeError('fetch failed: https://gw.example')
    }) as typeof fetch
    const cases: Array<[string, typeof fetch]> = [
      [TARGET, failing], ['', fakeFetch().impl], ['not a url', fakeFetch().impl], ['file:///etc', fakeFetch().impl]
    ]
    for (const [target, impl] of cases) {
      const res = await proxyToGateway(new Request(`${WEB}/api/v1/game/levels`), target, impl)
      expect(res.status, target).toBe(502)
      expect(res.headers.get('content-type')).toContain('application/json')
      const text = await res.text()
      expect(JSON.parse(text)).toEqual({ detail: 'Gateway unavailable.' })
      if (target) expect(text).not.toContain(target)
    }
  })
})
