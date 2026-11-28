const ICONIFY = 'https://api.iconify.design https://api.simplesvg.com https://api.unisvg.com'

function adminHeaders(production: boolean): Record<string, string> {
  const connect = production ? `connect-src 'self' ${ICONIFY}` : `connect-src 'self' ws: wss: ${ICONIFY}`
  const headers: Record<string, string> = {
    'Content-Security-Policy': [
      'default-src \'self\'',
      'script-src \'self\' \'unsafe-inline\'',
      'style-src \'self\' \'unsafe-inline\'',
      'img-src \'self\' data: blob:',
      'font-src \'self\' data:',
      connect,
      'object-src \'none\'',
      'base-uri \'self\'',
      'form-action \'self\'',
      'frame-ancestors \'none\''
    ].join('; '),
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'X-Robots-Tag': 'noindex, nofollow',
    'Cache-Control': 'no-store'
  }
  if (production) {
    headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
  }
  return headers
}

export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@nuxt/a11y'
  ],
  app: {
    head: {
      htmlAttrs: { lang: 'en' },
      charset: 'utf-8',
      viewport: 'width=device-width, initial-scale=1',
      titleTemplate: '%s | ai-shield Admin',
      meta: [
        { name: 'robots', content: 'noindex, nofollow' }
      ]
    }
  },
  css: ['~/assets/css/main.css'],
  colorMode: {
    preference: 'dark'
  },
  runtimeConfig: {
    apiProxyTarget: 'http://localhost:8000',
    apiAdminProxySecret: '',
    clientIpHeader: 'x-vercel-forwarded-for',
    public: {
      siteUrl: 'http://localhost:3002',
      webUrl: 'https://play.ai-shield.my'
    }
  },
  routeRules: {
    '/**': { headers: adminHeaders(process.env.NODE_ENV === 'production') }
  },
  devServer: {
    host: 'localhost',
    port: 3002
  },
  compatibilityDate: '2025-01-01',
  a11y: {
    axe: {
      options: {},
      runOptions: {
        runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']
      }
    }
  },
  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  }
})
