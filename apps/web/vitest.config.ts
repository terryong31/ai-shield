import { defineConfig } from 'vitest/config'

// Unit tests cover framework-free code under app/utils. Component tests can
// opt into a Nuxt environment later via @nuxt/test-utils.
export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node'
  }
})
