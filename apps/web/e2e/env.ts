import { fileURLToPath } from 'node:url'

// Empty variables (an unset GitHub secret) count as missing.
export const baseURL = process.env.E2E_BASE_URL || 'http://localhost:3000'
export const bypassSecret = process.env.VERCEL_AUTOMATION_BYPASS_SECRET || ''
export const account = {
  email: process.env.E2E_EMAIL || '',
  password: process.env.E2E_PASSWORD || ''
}
// Outside test-results: that directory is uploaded, and this file holds the bypass cookie.
export const STORAGE_STATE = fileURLToPath(new URL('../.e2e-auth/state.json', import.meta.url))
