// Forwards /api/v1/** to the gateway so the browser stays same-origin (spec 0041).
export default defineEventHandler(async (event) => {
  const target = String(useRuntimeConfig(event).apiProxyTarget ?? '')
  // Close the upstream request when the browser goes away, so a closed
  // leaderboard tab does not keep a gateway event stream open.
  const upstreamAbort = new AbortController()
  event.node.res.once('close', () => upstreamAbort.abort())
  const fetchWithAbort: typeof fetch = (input, init) =>
    fetch(input, { ...init, signal: upstreamAbort.signal })

  const response = await proxyToGateway(toWebRequest(event), target, fetchWithAbort)
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    return response
  }
  // h3 only sends headers with the first body chunk; an idle event stream would
  // leave EventSource waiting, so flush them now and pipe the stream.
  setResponseStatus(event, response.status)
  response.headers.forEach((value, name) => {
    if (name !== 'set-cookie') setResponseHeader(event, name, value)
  })
  for (const cookie of response.headers.getSetCookie()) appendResponseHeader(event, 'set-cookie', cookie)
  event.node.res.flushHeaders()
  return sendStream(event, response.body)
})
