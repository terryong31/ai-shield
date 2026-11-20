import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { hasInAppHistory } from '../app/utils/navigation'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

// Each page with a Back/Return control, and the fallback it uses with no in-app history.
const BACK_PAGES: Array<[string[], string]> = [
  [['pages', 'plans.vue'], '/'],
  [['pages', 'settings.vue'], '/'],
  [['pages', 'auth', 'login.vue'], '/'],
  [['pages', 'auth', 'register.vue'], '/'],
  [['pages', 'auth', 'recover.vue'], '/auth/login'],
  [['pages', 'game.vue'], '/']
]

describe('back navigation (spec 0016)', () => {
  it('[WEB-GAME-015] Back returns to the previous in-app page, else to the page fallback', () => {
    // vue-router keeps the previous in-app path in history.state.back.
    expect(hasInAppHistory({ back: '/game?level=easy' })).toBe(true)
    expect(hasInAppHistory({ back: null })).toBe(false)
    expect(hasInAppHistory(null)).toBe(false)
    expect(hasInAppHistory({ back: 'https://evil.example/' })).toBe(false)
    expect(hasInAppHistory({ back: '//evil.example/' })).toBe(false)

    const goBack = read('composables', 'useGoBack.ts')
    expect(goBack).toMatch(/hasInAppHistory\(window\.history\.state\)/)
    expect(goBack).toMatch(/router\.back\(\)/)
    expect(goBack).toMatch(/navigateTo\(fallback, \{ replace: true \}\)/)

    for (const [parts, fallback] of BACK_PAGES) {
      const source = read(...parts)
      const name = parts.join('/')
      expect(source, name).toContain(`goBack('${fallback}')`)
      // No Back/Return button jumps to a fixed page.
      expect(source, name).not.toMatch(/to="[^"]*"\s+label="(Back|Return)"/)
    }

    expect(read('pages', 'game.vue')).not.toMatch(/router\.push\('\/'\)/)
  })

  it('[WEB-GAME-015] defines a catch-all 404 route so unmatched paths resolve without router warnings', () => {
    const catchAllPath = join(APP_DIR, 'pages', '[...slug].vue')
    expect(existsSync(catchAllPath)).toBe(true)
    const source = read('pages', '[...slug].vue')
    expect(source).toContain('setResponseStatus(')
    expect(source).toContain('404')
    expect(source).toContain('to: \'/\'')
  })
})
