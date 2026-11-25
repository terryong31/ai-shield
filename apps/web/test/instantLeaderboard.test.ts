import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

describe('instant leaderboard (spec 0028 / 0044)', () => {
  it('[WEB-SCORE-001] uses Nuxt useState in useLeaderboard, parallelizes index mount, and prevents empty-state flash', () => {
    const composable = read('composables', 'useLeaderboard.ts')
    expect(composable).toContain('useState')
    expect(composable).toContain('shield_difficulty_leaderboards')
    expect(composable).toContain('shield_leaderboard_loaded')
    expect(composable).not.toContain('pinia')

    const indexPage = read('pages', 'index.vue')
    expect(indexPage).toContain('useLeaderboard')
    expect(indexPage).toContain('Promise.all')
    expect(indexPage).toContain(':loading="loadingScores && !hasLoaded"')
    expect(indexPage).not.toContain('Loading leaderboard...')
    expect(indexPage).toMatch(/hasLoaded\s*&&\s*!loadingScores\s*&&\s*filteredScores\.length\s*===\s*0/)
  })

  it('[WEB-SCORE-001] fetches only the active difficulty tab via getLeaderboard and persists a sessionStorage cache', () => {
    const composable = read('composables', 'useLeaderboard.ts')
    expect(composable).toContain('sessionStorage')
    expect(composable).toContain('hydrateFromCache')
    expect(composable).toContain('persistToCache')
    expect(composable).toContain('getLeaderboard(activeDiff')
    expect(composable).not.toContain('getScores(')
  })

  it('[WEB-SCORE-002] refreshes leaderboard in background after score recording in game.vue and reset in settings.vue', () => {
    const gamePage = read('pages', 'game.vue')
    expect(gamePage).toContain('useLeaderboard')
    expect(gamePage).toMatch(/refreshScores\(\s*\{\s*background:\s*true\s*\}\s*\)/)

    const settingsPage = read('pages', 'settings.vue')
    expect(settingsPage).toContain('useLeaderboard')
    expect(settingsPage).toMatch(/refreshScores\(\s*\{\s*background:\s*true\s*\}\s*\)/)
  })
})
