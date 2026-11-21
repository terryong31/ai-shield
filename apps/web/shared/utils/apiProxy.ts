/**
 * Same-origin proxy from the web server to the gateway (spec 0041). Pure over
 * web-standard Request/Response so it is testable with a fake fetch.
 */
const PREFIX = '/api/v1/'

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
  || name.startsWith('proxy-') || name.startsWith('x-forwarded-')

export function forwardableRequestHeaders(headers: Headers): Headers {
  const out = new Headers()
  headers.forEach((value, name) => {
    if (!isDroppedRequestHeader(name.toLowerCase())) out.append(name, value)
  })
  return out
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
  fetchImpl: typeof fetch = fetch
): Promise<Response> {
  const targetUrl = parseTarget(target)
  const upstreamUrl = resolveUpstreamUrl(targetUrl ?? new URL('http://invalid.local'), request.url)
  if (!upstreamUrl) return notFound()
  if (!targetUrl) return unavailable()

  const method = request.method.toUpperCase()
  const body = method === 'GET' || method === 'HEAD' ? undefined : await request.arrayBuffer()

  let upstream: Response
  try {
    upstream = await fetchImpl(upstreamUrl.href, {
      method,
      headers: forwardableRequestHeaders(request.headers),
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
