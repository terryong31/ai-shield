// The promo video lives on the repository's `media` branch and is served by GitHub.
export const PROMO_VIDEO_URL = 'https://raw.githubusercontent.com/terryong31/ai-shield/media/ai-shield-promo.webp'
const PROMO_VIDEO_ORIGIN = new URL(PROMO_VIDEO_URL).origin
const ICONIFY = 'https://api.iconify.design https://api.simplesvg.com https://api.unisvg.com'

export function landingHeaders(production: boolean): Record<string, string> {
  const connect = production
    ? `connect-src 'self' ${ICONIFY}`
    : `connect-src 'self' ws: wss: ${ICONIFY} https://va.vercel-scripts.com`
  const script = production
    ? 'script-src \'self\' \'unsafe-inline\''
    : 'script-src \'self\' \'unsafe-inline\' https://va.vercel-scripts.com'
  const headers: Record<string, string> = {
    'Content-Security-Policy': [
      'default-src \'self\'',
      script,
      'style-src \'self\' \'unsafe-inline\'',
      `img-src 'self' data: blob: ${PROMO_VIDEO_ORIGIN}`,
      'font-src \'self\' data:',
      connect,
      'object-src \'none\'',
      'base-uri \'self\'',
      'form-action \'self\'',
      'frame-ancestors \'none\''
    ].join('; '),
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'Cross-Origin-Opener-Policy': 'same-origin'
  }
  if (production) {
    headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
  }
  return headers
}
