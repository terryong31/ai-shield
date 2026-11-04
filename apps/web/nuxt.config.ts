// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  // @nuxt/ui v4 ships @nuxtjs/color-mode, so it is not registered separately
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@vueuse/nuxt'
  ],
  css: [
    '~/assets/css/main.css',
    '@vue-flow/core/dist/style.css',
    '@vue-flow/core/dist/theme-default.css',
    '@vue-flow/controls/dist/style.css'
  ],
  colorMode: {
    preference: 'dark'
  },
  // The browser talks only to the gateway API; no database keys live here.
  // Override at runtime with NUXT_PUBLIC_API_BASE_URL.
  runtimeConfig: {
    public: {
      apiBaseUrl: 'http://localhost:8000'
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
