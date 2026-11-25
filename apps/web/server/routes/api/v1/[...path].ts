import { checkBotId } from 'botid/server'

// Forwards /api/v1/** to the gateway so the browser stays same-origin (spec 0041, 0043).
export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const target = String(config.apiProxyTarget ?? '')
  const proxySecret = String(config.apiProxySecret ?? '').trim() || undefined
  const clientIpHeader = String(config.clientIpHeader ?? '').trim() || undefined
  const requireProxyTrust = process.env.VERCEL === '1'
    || (process.env.NODE_ENV === 'production' && process.env.APP_ENV !== 'development')
  const request = toWebRequest(event)
  const clientIp = clientIpFromHeaders(
    request.headers,
    clientIpHeader,
    requireProxyTrust ? '' : (event.node.req.socket?.remoteAddress || 'unknown')
  )

  const upstreamAbort = new AbortController()
  event.node.res.once('close', () => upstreamAbort.abort())
  const fetchWithAbort: typeof fetch = (input, init) =>
    fetch(input, { ...init, signal: upstreamAbort.signal })

  return proxyToGateway(request, target, fetchWithAbort, {
    clientIp,
    clientIpHeader,
    proxySecret,
    requireProxyTrust,
    checkBot: () => checkBotId()
  })
})
