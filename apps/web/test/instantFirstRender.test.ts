import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import * as leaderboard from '../app/utils/leaderboard'
import * as ssr from '../app/utils/ssr'
import { DEFAULT_ANONYMOUS_SESSION } from '../app/utils/sessionHint'

const WEB_DIR = join(import.meta.dirname, '..')
const read = (...parts: string[]) => readFileSync(join(WEB_DIR, 'app', ...parts), 'utf-8')
const ADA = {
  ...DEFAULT_ANONYMOUS_SESSION,
  authenticated: true,
  is_anonymous: false,
  tier: 'free' as const,
  player_name: 'Ada'
}
const RANK = { difficulty: 'Easy' as const, rank: 40, total_score: 900 }

describe('instant first render (spec 0044)', () => {
  it('[WEB-LBOARD-018] loads the rows in the server render with a time limit', () => {
    const page = read('pages', 'index.vue')
    expect(page).toMatch(/onServerPrefetch\([\s\S]*?prefetchScores\(\)/)
    const composable = read('composables', 'useLeaderboard.ts')
    expect(composable).toMatch(/prefetchScores[\s\S]*?withSsrTimeout\(getLeaderboard\(/)
    expect(read('utils', 'ssr.ts')).toContain('SSR_TIMEOUT_MS = 800')
    // The proxy refuses a request with no client address, so the server render passes it on.
    expect(read('composables', 'useShieldApi.ts')).toMatch(/import\.meta\.server[\s\S]*?clientIpHeader[\s\S]*?useRequestHeaders/)
  })

  it('[WEB-LBOARD-018] stops waiting for a gateway that does not answer', async () => {
    vi.useFakeTimers()
    try {
      const hung = expect(ssr.withSsrTimeout(new Promise<never>(() => {}))).rejects.toThrow('800 ms')
      await vi.advanceTimersByTimeAsync(800)
      await hung
      await expect(ssr.withSsrTimeout(Promise.resolve(1))).resolves.toBe(1)
      await expect(ssr.withSsrTimeout(Promise.reject(new Error('down')))).rejects.toThrow('down')
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('[WEB-LBOARD-013] [WEB-LBOARD-019] pins the display name first and fills in the rank when it loads', () => {
    const pin = leaderboard.pinnedRow
    expect(pin(null, ADA)).toEqual({ playerName: 'Ada', rankLabel: '#-', scoreLabel: '-' })
    expect(pin(RANK, ADA)).toEqual({ playerName: 'Ada', rankLabel: '#40', scoreLabel: '900' })
    expect(pin({ ...RANK, rank: 1, total_score: 10_000 }, ADA)).toMatchObject({ rankLabel: '#1', scoreLabel: '10,000' })
    expect(pin({ ...RANK, rank: null, total_score: null }, ADA)).toEqual({ playerName: 'Ada', rankLabel: '#-', scoreLabel: '0' })
    expect(pin(RANK, DEFAULT_ANONYMOUS_SESSION)).toBeNull()

    const page = read('pages', 'index.vue')
    expect(page).not.toMatch(/Skeleton/)
    const plugin = read('plugins', 'sessionHint.client.ts')
    expect(plugin).toMatch(/myRanks\.value = \{\}/)
    expect(plugin).not.toContain('rankHint')
    expect(read('utils', 'leaderboard.ts')).not.toContain('RANK_HINT')
  })

  it('[WEB-LBOARD-013] [WEB-LBOARD-014] [WEB-LBOARD-017] [WEB-LBOARD-019] gives a signed-in player exactly one row, in every state', () => {
    const rows = leaderboard.leaderboardRows
    const entries = [
      { player_name: 'Bob', total_score: 2000 },
      { player_name: 'Ada', total_score: 900 }
    ]
    const bob = { rankLabel: '#1', player_name: 'Bob', total_score: '2,000', own: false }
    const own = (rankLabel: string, score: string) => ({ rankLabel, player_name: 'Ada', total_score: score, own: true })

    expect(rows([], null, ADA)).toEqual([own('#-', '-')])
    expect(rows([], { ...RANK, rank: null, total_score: null }, ADA)).toEqual([own('#-', '0')])
    expect(rows(entries, { ...RANK, rank: 2 }, ADA)).toEqual([bob, own('#2', '900')])
    expect(rows(entries.slice(0, 1), RANK, ADA)).toEqual([bob, own('#40', '900')])
    expect(rows([], null, DEFAULT_ANONYMOUS_SESSION)).toEqual([])
    expect(rows(entries.slice(0, 1), null, DEFAULT_ANONYMOUS_SESSION)).toEqual([bob])
  })

  it('[WEB-LBOARD-020] loads the rank in parallel and as soon as the session is confirmed', () => {
    const composable = read('composables', 'useLeaderboard.ts')
    expect(composable).toMatch(/Promise\.all\(\[\s*getLeaderboard\(activeDiff, 25\),\s*refreshMyRank\(activeDiff\)\s*\]\)/)
    expect(read('pages', 'index.vue')).toMatch(/watch\(\(\) => isLoggedIn\.value && session\.value\.player_name,[\s\S]*?refreshMyRank\(/)
  })

  it('[WEB-LBOARD-021] runs the functions next to the data', () => {
    for (const app of ['web', 'api']) {
      const config = JSON.parse(readFileSync(join(WEB_DIR, '..', app, 'vercel.json'), 'utf-8'))
      expect(config.regions).toEqual(['sin1'])
    }
  })
})
