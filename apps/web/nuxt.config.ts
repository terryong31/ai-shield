// https://nuxt.com/docs/api/configuration/nuxt-config
import { securityRouteRules } from './app/utils/securityHeaders'

export default defineNuxtConfig({
  // @nuxt/ui v4 ships @nuxtjs/color-mode, so it is not registered separately
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@vueuse/nuxt'
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
      siteUrl: 'http://localhost:3000',
      // Contact on /privacy (spec 0058); empty shows the project issues page instead.
      privacyContactEmail: ''
    }
  },
  // Security headers on every page (spec 0053). Analytics are a client plugin
  // (app/plugins/analytics.client.ts) so each event is scrubbed first.
  routeRules: securityRouteRules(process.env.NODE_ENV === 'production'),
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
