import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const repoRoot = resolve(__dirname, '..', '..', '..')
const webRoot = resolve(repoRoot, 'apps', 'web')
const adminRoot = resolve(repoRoot, 'apps', 'admin')

const read = (...parts: string[]) => readFileSync(resolve(repoRoot, ...parts), 'utf8')

describe('Admin console extraction (spec 0059)', () => {
  it('[WEB-ADMIN-001] removes /_console routes and admin modules from apps/web', () => {
    expect(existsSync(resolve(webRoot, 'app', 'pages', 'console'))).toBe(false)
    expect(existsSync(resolve(webRoot, 'app', 'layouts', 'dashboard.vue'))).toBe(false)
    expect(existsSync(resolve(webRoot, 'app', 'composables', 'useAdminAccess.ts'))).toBe(false)

    const headers = read('apps', 'web', 'app', 'utils', 'securityHeaders.ts')
    expect(headers).not.toContain('/_console')
  })

  it('[WEB-ADMIN-002] serves guarded admin dashboard in apps/admin with noindex, no-store, and admin proxy', () => {
    expect(existsSync(resolve(adminRoot, 'package.json'))).toBe(true)
    expect(existsSync(resolve(adminRoot, 'app', 'pages', 'index.vue'))).toBe(true)
    expect(existsSync(resolve(adminRoot, 'app', 'pages', 'settings.vue'))).toBe(true)
    expect(existsSync(resolve(adminRoot, 'app', 'layouts', 'dashboard.vue'))).toBe(true)
    expect(existsSync(resolve(adminRoot, 'app', 'composables', 'useAdminAccess.ts'))).toBe(true)

    const nuxtConfig = read('apps', 'admin', 'nuxt.config.ts')
    expect(nuxtConfig).toContain('noindex, nofollow')
    expect(nuxtConfig).toContain('no-store')

    const robots = read('apps', 'admin', 'public', 'robots.txt')
    expect(robots).toMatch(/Disallow:\s*\//)

    const proxy = read('apps', 'admin', 'server', 'routes', 'api', 'v1', '[...path].ts')
    expect(proxy).toContain('x-shield-admin-proxy-secret')

    const layout = read('apps', 'admin', 'app', 'layouts', 'dashboard.vue')
    expect(layout).toContain('UAuthForm')
  })
})
