import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const APP = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP, ...parts), 'utf-8')

describe('Game page modules (spec 0055)', () => {
  it('[WEB-MOD-001] keeps game.vue at 600 lines or fewer, with its panels and state split out', () => {
    const page = read('pages', 'game.vue')
    expect(page.split('\n').length).toBeLessThanOrEqual(600)

    const panels = readdirSync(join(APP, 'components', 'game')).filter(name => name.endsWith('.vue'))
    expect(panels.length).toBeGreaterThanOrEqual(5)
    expect(existsSync(join(APP, 'composables', 'useGamePage.ts'))).toBe(true)

    for (const panel of panels) {
      expect(page, panel).toContain(`<Game${panel.replace('.vue', '')}`)
    }
  })

  it('[WEB-MOD-002] shares one page state with every panel through provide and inject', () => {
    const page = read('pages', 'game.vue')
    expect(page).toMatch(/const game = useGamePage\(\)/)
    expect(page).toMatch(/provide\(GAME_PAGE, game\)/)

    const composable = read('composables', 'useGamePage.ts')
    expect(composable).toMatch(/export const GAME_PAGE: InjectionKey<GamePage>/)
    expect(composable).toMatch(/export function useGameContext\(\): GamePage/)

    for (const panel of readdirSync(join(APP, 'components', 'game')).filter(name => name.endsWith('.vue'))) {
      expect(read('components', 'game', panel), panel).toMatch(/= useGameContext\(\)/)
    }

    // A template ref binds to page state only when the panel takes that ref from the context.
    for (const panel of readdirSync(join(APP, 'components', 'game')).filter(name => name.endsWith('.vue'))) {
      const source = read('components', 'game', panel)
      for (const [, name] of source.matchAll(/\sref="(\w+)"/g)) {
        expect(source, `${panel} ref="${name}"`).toMatch(new RegExp(`const \\{[^}]*\\b${name}\\b[^}]*\\} = useGameContext\\(\\)`))
      }
    }
  })
})
