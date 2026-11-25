// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  // @nuxt/ui v4 ships @nuxtjs/color-mode, so it is not registered separately
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@vueuse/nuxt',
    // Vercel Web Analytics: the script only reports on Vercel deployments
    '@vercel/analytics',
    // Vercel Speed Insights: sends Core Web Vitals, only on Vercel deployments
    '@vercel/speed-insights'
  ],
  app: {
    head: {
      htmlAttrs: {
        lang: 'en'
      },
      charset: 'utf-8',
      viewport: 'width=device-width, initial-scale=1',
      titleTemplate: '%s | ai-shield',
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }
      ]
    }
  },
  css: [
    '@vue-flow/core/dist/style.css',
    '@vue-flow/core/dist/theme-default.css',
    '~/assets/css/main.css'
  ],
  colorMode: {
    preference: 'dark'
  },
  // The browser calls same-origin /api/v1; the web server proxies it to the gateway
  // (spec 0041). Override at runtime with NUXT_API_PROXY_TARGET (server only)
  // and NUXT_PUBLIC_SITE_URL. No database keys live here.
  runtimeConfig: {
    apiProxyTarget: 'http://localhost:8000',
    apiProxySecret: '',
    clientIpHeader: 'x-vercel-forwarded-for',
    public: {
      siteUrl: 'http://localhost:3000'
    }
  },
  routeRules: {
    '/auth/**': {
      headers: {
        'Referrer-Policy': 'no-referrer',
        'Cache-Control': 'no-store'
      }
    }
  },
  devServer: {
    host: 'localhost'
  },
  compatibilityDate: '2025-01-01',
  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  }
})
