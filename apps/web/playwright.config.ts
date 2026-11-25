import { defineConfig, devices } from '@playwright/test'
import { STORAGE_STATE, baseURL } from './e2e/env'

// End-to-end tests against a local stack or a deployment (`E2E_BASE_URL`).
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  globalSetup: './e2e/global-setup.ts',
  // One worker keeps the run under the gateway rate limits (spec 0043).
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL,
    storageState: STORAGE_STATE,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  projects: [{
    name: 'chromium',
    use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } }
  }]
})
