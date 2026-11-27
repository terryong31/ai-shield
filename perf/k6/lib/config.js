// Target resolution, the loopback guard, request headers and SLO thresholds (spec 0057).
// No k6 module is imported here, so plain Node can test the guard.

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])
const URL_PATTERN = /^(https?):\/\/(\[[0-9a-fA-F:]+\]|[^/:?#]+)(:\d+)?\/?$/

/** The k6 environment, or nothing when this file runs outside k6. */
export function env(name, fallback = '') {
  // eslint-disable-next-line no-undef
  const vars = typeof __ENV === 'undefined' ? {} : __ENV
  return vars[name] || fallback
}

/**
 * The base URL to test. A host that is not loopback needs K6_ALLOW_REMOTE=1, so a
 * typo can never send load to a real deployment.
 */
export function resolveTarget(raw, allowRemote) {
  const match = URL_PATTERN.exec(String(raw || '').trim())
  if (!match) {
    throw new Error(`K6_TARGET_URL must be an http(s) origin, got "${raw}".`)
  }
  const [, scheme, host, port = ''] = match
  const target = `${scheme}://${host.toLowerCase()}${port}`
  if (!LOOPBACK_HOSTS.has(host.toLowerCase()) && allowRemote !== '1') {
    throw new Error(
      `Refusing to load-test ${target}: it is not loopback. Set K6_ALLOW_REMOTE=1 to allow it.`
    )
  }
  return target
}

export function target() {
  return resolveTarget(env('K6_TARGET_URL', 'http://127.0.0.1:8000'), env('K6_ALLOW_REMOTE'))
}

/**
 * Headers for every request. With K6_PROXY_SECRET (a production-mode gateway) the run
 * proves the proxy secret and the BotID pass. The secret is never logged or reported.
 */
export function requestHeaders() {
  const headers = { 'content-type': 'application/json', 'sec-fetch-site': 'same-origin' }
  const secret = env('K6_PROXY_SECRET')
  if (secret) {
    headers['x-shield-proxy-secret'] = secret
    headers['x-shield-botid'] = 'pass'
  }
  return headers
}

export const TREND_STATS = ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)']

/** The SLOs of spec 0057. `stress` expects 429s, so its write failures are not limited. */
export function thresholds(profile) {
  const slo = {
    'shield_unexpected_5xx': ['count==0'],
    'http_req_duration{endpoint:health}': ['p(95)<50'],
    'http_req_duration{endpoint:leaderboard}': ['p(95)<200', 'p(99)<500'],
    'http_req_duration{endpoint:game_run}': ['p(95)<600', 'p(99)<1200'],
    'http_req_failed{kind:read}': ['rate<0.005']
  }
  if (profile !== 'stress') {
    slo['http_req_failed{kind:write}'] = ['rate<0.01']
    slo.checks = ['rate>0.99']
  }
  return slo
}
