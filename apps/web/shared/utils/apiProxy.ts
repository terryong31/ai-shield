import { BOTID_PROTECTED_ROUTES } from './botid'

/**
 * Same-origin proxy from the web server to the gateway (spec 0041, 0043). Pure over
 * web-standard Request/Response so it is testable with a fake fetch.
 */
const PREFIX = '/api/v1/'
const WEBHOOK_PATH = '/api/v1/billing/webhook'
// Above the 1.25 MiB training CSV limit; the gateway keeps its own per-route caps (spec 0053).
export const MAX_PROXY_BODY_BYTES = 2 * 1024 * 1024

const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'transfer-encoding', 'upgrade', 'te', 'trailer'
])
const DROPPED_REQUEST = new Set(['host', 'content-length', 'forwarded'])
// fetch has already decoded the body, so the original encoding and length are wrong.
const DROPPED_RESPONSE = new Set(['content-encoding', 'content-length', 'set-cookie'])

const json = (status: number, detail: string) =>
  new Response(JSON.stringify({ detail }), {
    status,
    headers: { 'content-type': 'application/json' }
  })

const notFound = () => json(404, 'Not found.')
const tooLarge = () => json(413, 'Request body too large.')

/** The body, or null once it passes the limit; reads the stream so a missing length cannot hide it. */
async function readBoundedBody(request: Request, limit: number): Promise<ArrayBuffer | null> {
  if (!request.body) return new ArrayBuffer(0)
  const reader = request.body.getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    size += value.byteLength
    if (size > limit) {
      await reader.cancel()
      return null
    }
    chunks.push(value)
  }
  const out = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) {
    out.set(chunk, offset)
    offset += chunk.byteLength
  }
  return out.buffer
}
const unavailable = () => json(502, 'Gateway unavailable.')

const isSafeSegment = (segment: string): boolean => {
  if (segment === '') return false
  let decoded: string
  try {
    decoded = decodeURIComponent(segment)
  } catch {
    return false
  }
  return decoded !== '.' && decoded !== '..' && !/[/\\]/.test(decoded)
}

const parseTarget = (target: string): URL | null => {
  try {
    const url = new URL(target)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url : null
  } catch {
    return null
  }
}

const isDroppedRequestHeader = (name: string) =>
  HOP_BY_HOP.has(name) || DROPPED_REQUEST.has(name)
  || name.startsWith('proxy-') || name.startsWith('x-forwarded-') || name.startsWith('x-shield-')

export function forwardableRequestHeaders(headers: Headers): Headers {
  const out = new Headers()
  headers.forEach((value, name) => {
    if (!isDroppedRequestHeader(name.toLowerCase())) out.append(name, value)
  })
  return out
}

export function clientIpFromHeaders(
  headers: Headers | Record<string, string | string[] | undefined>,
  headerName: string | undefined,
  fallback: string
): string {
  const name = headerName?.trim().toLowerCase()
  if (!name) return fallback
  const raw = headers instanceof Headers
    ? headers.get(name)
    : headers[name] ?? headers[headerName!.trim()]
  const value = Array.isArray(raw) ? raw[0] : raw
  const first = typeof value === 'string' ? value.split(',', 1)[0]?.trim() : ''
  return first || fallback
}

export function isBotIdProtected(method: string, pathname: string): boolean {
  const upper = method.toUpperCase()
  return BOTID_PROTECTED_ROUTES.some(r => r.method === upper && r.path === pathname)
}

export interface ProxyGatewayOptions {
  clientIp?: string
  clientIpHeader?: string
  proxySecret?: string
  requireProxyTrust?: boolean
  checkBot?: () => Promise<{ isBot: boolean }>
}

/** Null when the request path is not a clean path under /api/v1/. */
export function resolveUpstreamUrl(target: URL, requestUrl: string): URL | null {
  const { pathname, search } = new URL(requestUrl)
  if (!pathname.startsWith(PREFIX)) return null
  if (!pathname.slice(PREFIX.length).split('/').every(isSafeSegment)) return null
  const base = `${target.origin}${target.pathname}`.replace(/\/+$/, '')
  const upstream = new URL(`${base}${pathname}${search}`)
  return upstream.origin === target.origin ? upstream : null
}

export async function proxyToGateway(
  request: Request,
  target: string,
  fetchImpl: typeof fetch = fetch,
  options: ProxyGatewayOptions = {}
): Promise<Response> {
  const targetUrl = parseTarget(target)
  const upstreamUrl = resolveUpstreamUrl(targetUrl ?? new URL('http://invalid.local'), request.url)
  if (!upstreamUrl) return notFound()
  if (!targetUrl) return unavailable()
  if (
    options.requireProxyTrust
    && (!options.clientIpHeader?.trim() || !options.proxySecret?.trim() || !options.clientIp?.trim())
  ) {
    console.error(
      '[shield-proxy] Missing NUXT_CLIENT_IP_HEADER, NUXT_API_PROXY_SECRET, or resolved client IP in production; refusing to proxy.'
    )
    return json(503, 'Gateway unavailable.')
  }

  const method = request.method.toUpperCase()
  const parsedRequestUrl = new URL(request.url)
  const { pathname } = parsedRequestUrl
  // Stripe signs its webhook and posts it server to server, with no browser headers;
  // the gateway checks the signature, so the webhook skips the browser checks.
  const isWebhook = method === 'POST' && pathname === WEBHOOK_PATH
  if (!isWebhook && (method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE')) {
    // Only same-origin pages and direct navigation may change state (spec 0053).
    const fetchSite = request.headers.get('sec-fetch-site')?.trim().toLowerCase()
    const originHeader = request.headers.get('origin')?.trim()
    const foreignSite = fetchSite !== undefined && fetchSite !== 'same-origin' && fetchSite !== 'none'
    const foreignOrigin = Boolean(originHeader) && originHeader !== parsedRequestUrl.origin
    const unlabelled = options.requireProxyTrust === true && !originHeader && fetchSite === undefined
    if (foreignSite || foreignOrigin || unlabelled) {
      return json(403, 'Cross-site request blocked.')
    }
  }
  const declaredLength = Number(request.headers.get('content-length') ?? '0')
  if (Number.isFinite(declaredLength) && declaredLength > MAX_PROXY_BODY_BYTES) {
    return tooLarge()
  }
  const reqHeaders = forwardableRequestHeaders(request.headers)

  if (options.clientIp) {
    reqHeaders.set('x-shield-client-ip', options.clientIp)
  }
  if (options.proxySecret) {
    reqHeaders.set('x-shield-proxy-secret', options.proxySecret)
  }

  if (isBotIdProtected(method, pathname) && options.checkBot) {
    try {
      const verdict = await options.checkBot()
      if (verdict.isBot) {
        return json(403, 'Request blocked.')
      }
      reqHeaders.set('x-shield-botid', 'pass')
    } catch {
      return json(503, 'Bot check unavailable. Try again.')
    }
  }

  let body: ArrayBuffer | undefined
  if (method !== 'GET' && method !== 'HEAD') {
    const bounded = await readBoundedBody(request, MAX_PROXY_BODY_BYTES)
    if (bounded === null) return tooLarge()
    body = bounded
  }

  let upstream: Response
  try {
    upstream = await fetchImpl(upstreamUrl.href, {
      method,
      headers: reqHeaders,
      body,
      redirect: 'manual'
    })
  } catch {
    return unavailable()
  }

  const headers = new Headers()
  upstream.headers.forEach((value, name) => {
    const lower = name.toLowerCase()
    if (!HOP_BY_HOP.has(lower) && !DROPPED_RESPONSE.has(lower)) headers.append(name, value)
  })
  for (const cookie of upstream.headers.getSetCookie()) headers.append('set-cookie', cookie)

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers
  })
}
