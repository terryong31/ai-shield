import { request } from '@playwright/test'
import { STORAGE_STATE, baseURL, bypassSecret } from './env'

// Exchanges the Vercel bypass secret for a cookie. A cookie stays on the deployment's
// host, but an extra header on every request would also reach third-party hosts.
export default async function globalSetup() {
  const context = await request.newContext({ baseURL })
  if (bypassSecret) {
    const response = await context.get('/', {
      headers: {
        'x-vercel-protection-bypass': bypassSecret,
        'x-vercel-set-bypass-cookie': 'true'
      }
    })
    if (!response.ok()) {
      throw new Error(`The preview refused the bypass secret (HTTP ${response.status()})`)
    }
  }
  await context.storageState({ path: STORAGE_STATE })
  await context.dispose()
}
