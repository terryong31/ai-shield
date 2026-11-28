const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'host',
  'content-length'
])

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const target = String(config.apiProxyTarget ?? '').trim().replace(/\/+$/, '')
  const adminSecret = String(config.apiAdminProxySecret ?? '').trim()
  const request = toWebRequest(event)
  const incomingUrl = new URL(request.url)
  const upstreamUrl = `${target}${incomingUrl.pathname}${incomingUrl.search}`

  const headers = new Headers()
  for (const [key, value] of request.headers.entries()) {
    const lower = key.toLowerCase()
    if (HOP_BY_HOP.has(lower) || lower === 'x-shield-proxy-secret' || lower === 'x-shield-admin-proxy-secret') {
      continue
    }
    headers.set(key, value)
  }
  if (adminSecret) {
    headers.set('x-shield-admin-proxy-secret', adminSecret)
  }

  const method = request.method.toUpperCase()
  const body = method === 'GET' || method === 'HEAD' ? undefined : await request.arrayBuffer()

  const upstream = await fetch(upstreamUrl, {
    method,
    headers,
    body,
    redirect: 'manual'
  })

  const outHeaders = new Headers()
  for (const [key, value] of upstream.headers.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      outHeaders.append(key, value)
    }
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: outHeaders
  })
})
