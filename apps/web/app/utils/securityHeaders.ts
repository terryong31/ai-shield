/**
 * Security headers for every page (spec 0053). nuxt.config.ts uses these as its
 * routeRules, so Vercel and the Node server send the same headers.
 */

interface HeaderRule {
  headers: Record<string, string>
}

const NO_STORE: HeaderRule = { headers: { 'Cache-Control': 'no-store' } }

// Nuxt Icon fetches icons that are not in the bundle from the Iconify API.
const ICONIFY = 'https://api.iconify.design https://api.simplesvg.com https://api.unisvg.com'

// Nuxt inlines its payload and Vue Flow and Nuxt UI set inline styles, so both need
// 'unsafe-inline'. On Vercel, Analytics, Speed Insights and BotID load from this
// origin; outside Vercel the analytics scripts load in debug mode from their CDN.
function contentSecurityPolicy(production: boolean): string {
  const connect = production
    ? `connect-src 'self' ${ICONIFY}`
    : `connect-src 'self' ws: wss: ${ICONIFY} https://va.vercel-scripts.com`
  const script = production
    ? 'script-src \'self\' \'unsafe-inline\''
    : 'script-src \'self\' \'unsafe-inline\' https://va.vercel-scripts.com'
  return [
    'default-src \'self\'',
    script,
    'style-src \'self\' \'unsafe-inline\'',
    'img-src \'self\' data: blob:',
    'font-src \'self\' data:',
    connect,
    'object-src \'none\'',
    'base-uri \'self\'',
    'form-action \'self\'',
    'frame-ancestors \'none\''
  ].join('; ')
}

export function securityRouteRules(production: boolean): Record<string, HeaderRule> {
  const baseline: Record<string, string> = {
    'Content-Security-Policy': contentSecurityPolicy(production),
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'Cross-Origin-Opener-Policy': 'same-origin'
  }
  if (production) {
    baseline['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
  }
  return {
    '/**': { headers: baseline },
    '/auth/**': { headers: { 'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store' } },
    '/_console': NO_STORE,
    '/_console/**': NO_STORE,
    '/settings': NO_STORE,
    '/plans': NO_STORE
  }
}
