import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.WEB_A11Y_BASE_URL || 'http://127.0.0.1:4300'

export default defineConfig({
  testDir: './test',
  testMatch: /a11y\.spec\.ts/,
  outputDir: './test-results',
  reporter: 'list',
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  projects: [{
    name: 'chromium',
    use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } }
  }],
  ...(process.env.WEB_A11Y_BASE_URL
    ? {}
    : {
        webServer: {
          command: 'PORT=4300 HOST=127.0.0.1 node .output/server/index.mjs',
          url: 'http://127.0.0.1:4300/',
          reuseExistingServer: false,
          timeout: 30_000
        }
      })
})
