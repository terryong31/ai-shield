import { PROMO_VIDEO_URL, landingHeaders } from './app/utils/securityHeaders'

export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@nuxt/content',
    '@nuxtjs/i18n',
    '@nuxt/a11y'
  ],
  app: {
    head: {
      charset: 'utf-8',
      viewport: 'width=device-width, initial-scale=1',
      titleTemplate: '%s | ai-shield',
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }
      ]
    }
  },
  css: ['~/assets/css/main.css'],
  colorMode: {
    preference: 'dark'
  },
  content: {
    experimental: {
      sqliteConnector: 'native'
    }
  },
  runtimeConfig: {
    public: {
      siteUrl: 'https://ai-shield.my',
      playUrl: 'https://play.ai-shield.my',
      supportEmail: 'support@ai-shield.my',
      securityEmail: 'security@ai-shield.my',
      promoVideoUrl: PROMO_VIDEO_URL
    }
  },
  routeRules: {
    '/**': {
      prerender: true,
      headers: landingHeaders(process.env.NODE_ENV === 'production')
    }
  },
  devServer: {
    host: 'localhost',
    port: 3001
  },
  compatibilityDate: '2025-01-01',
  nitro: {
    prerender: {
      routes: [
        '/',
        '/pricing',
        '/changelog',
        '/privacy',
        '/terms',
        '/refund',
        '/ms',
        '/ms/pricing',
        '/ms/changelog',
        '/ms/privacy',
        '/ms/terms',
        '/ms/refund'
      ]
    }
  },
  vite: {
    optimizeDeps: {
      include: ['@vercel/analytics', '@vercel/speed-insights']
    }
  },
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
  },
  i18n: {
    defaultLocale: 'en',
    strategy: 'prefix_except_default',
    baseUrl: 'https://ai-shield.my',
    bundle: {
      optimizeTranslationDirective: false
    },
    locales: [
      { code: 'en', language: 'en-MY', name: 'English', file: 'en.ts' },
      { code: 'ms', language: 'ms-MY', name: 'Bahasa Melayu', file: 'ms.ts' }
    ]
  }
})
