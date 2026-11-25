import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DifficultyCategory, DifficultyLeaderboardEntry, LeaderboardRankResponse } from '../app/types/api'
import {
  createLeaderboardPoller,
  formatRankLabel,
  ownRowPlacement
} from '../app/utils/leaderboard'

const WEB_DIR = join(import.meta.dirname, '..')
const APP_DIR = join(WEB_DIR, 'app')
const SHARED_DIR = join(WEB_DIR, 'shared')

const listSourceFiles = (dir: string): string[] =>
  readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return listSourceFiles(full)
    return /\.(ts|vue)$/.test(name) ? [full] : []
  })

const makeEntries = (count: number): DifficultyLeaderboardEntry[] =>
  Array.from({ length: count }, (_, idx) => ({
    player_name: `Player ${idx + 1}`,
    difficulty: 'Easy',
    total_score: 10000 - idx * 10,
    max_possible_score: 70000,
    levels_solved: 1,
    levels_mastered: 0,
    levels_total: 7,
    avg_latency_ms: 10,
    total_cost_usd: 0.01
  }))

describe('leaderboard read scaling & my rank (spec 0044)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('[WEB-LBOARD-005] polls only the active tab every 20s while visible (3 times in 60s)', async () => {
    const fetchedTabs: DifficultyCategory[] = []
    const poller = createLeaderboardPoller({
      getLeaderboard: async (difficulty) => {
        fetchedTabs.push(difficulty)
        return makeEntries(2)
      },
      getMyRank: async () => ({ difficulty: 'Easy', rank: null, total_score: null }),
      isSignedIn: () => false,
      isHidden: () => false
    })

    poller.start()
    await vi.advanceTimersByTimeAsync(60_000)
    poller.stop()

    expect(fetchedTabs).toEqual(['Easy', 'Easy', 'Easy'])
  })

  it('[WEB-LBOARD-006] pauses while document is hidden and refetches once when visible after >20s', async () => {
    let hidden = false
    const fetchedTabs: DifficultyCategory[] = []
    const poller = createLeaderboardPoller({
      getLeaderboard: async (difficulty) => {
        fetchedTabs.push(difficulty)
        return makeEntries(1)
      },
      getMyRank: async () => ({ difficulty: 'Easy', rank: null, total_score: null }),
      isSignedIn: () => false,
      isHidden: () => hidden
    })

    await poller.refreshActive()
    expect(fetchedTabs).toEqual(['Easy'])

    poller.start()
    hidden = true
    await vi.advanceTimersByTimeAsync(25_000)
    expect(fetchedTabs).toEqual(['Easy'])

    hidden = false
    await poller.onVisibilityChange()
    expect(fetchedTabs).toEqual(['Easy', 'Easy'])
    poller.stop()
  })

  it('[WEB-LBOARD-007] refetches the active tab immediately after own run or reset progress', async () => {
    const fetchedTabs: DifficultyCategory[] = []
    const poller = createLeaderboardPoller({
      getLeaderboard: async (difficulty) => {
        fetchedTabs.push(difficulty)
        return makeEntries(1)
      },
      getMyRank: async () => ({ difficulty: 'Easy', rank: 1, total_score: 10000 }),
      isSignedIn: () => true,
      isHidden: () => false
    })

    await poller.refreshActive({ force: true })
    expect(fetchedTabs).toEqual(['Easy'])

    const gamePage = readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')
    const settingsPage = readFileSync(join(APP_DIR, 'pages', 'settings.vue'), 'utf-8')
    expect(gamePage).toMatch(/refreshScores\(\s*\{\s*background:\s*true\s*\}\s*\)/)
    expect(settingsPage).toMatch(/refreshScores\(\s*\{\s*background:\s*true\s*\}\s*\)/)
  })

  it('[WEB-LBOARD-008] fetches stale (>20s) tabs once on switch and skips fresh (<20s) tabs', async () => {
    const fetchedTabs: DifficultyCategory[] = []
    const poller = createLeaderboardPoller({
      getLeaderboard: async (difficulty) => {
        fetchedTabs.push(difficulty)
        return makeEntries(1)
      },
      getMyRank: async () => ({ difficulty: 'Easy', rank: null, total_score: null }),
      isSignedIn: () => false,
      isHidden: () => false
    })

    await poller.switchTab('Easy')
    expect(fetchedTabs).toEqual(['Easy'])
    await vi.advanceTimersByTimeAsync(10_000)
    await poller.switchTab('Medium')
    expect(fetchedTabs).toEqual(['Easy', 'Medium'])
    await poller.switchTab('Easy')
    expect(fetchedTabs).toEqual(['Easy', 'Medium'])

    await vi.advanceTimersByTimeAsync(21_000)
    await poller.switchTab('Easy')
    expect(fetchedTabs).toEqual(['Easy', 'Medium', 'Easy'])
  })

  it('[WEB-LBOARD-009] hydrates from sessionStorage immediately without flashing empty state', () => {
    const composable = readFileSync(join(APP_DIR, 'composables', 'useLeaderboard.ts'), 'utf-8')
    const indexPage = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    expect(composable).toContain('hydrateFromCache')
    expect(composable).toContain('window.sessionStorage.getItem')
    expect(indexPage).toContain(':empty="hasLoaded ? \'No scores yet\' : \'Loading...\'"')
  })

  it('[WEB-LBOARD-010] removes EventSource, stream path, and refreshRawScores from app and shared code', () => {
    for (const file of [...listSourceFiles(APP_DIR), ...listSourceFiles(SHARED_DIR)]) {
      const content = readFileSync(file, 'utf-8')
      expect(content, file).not.toContain('EventSource')
      expect(content, file).not.toContain('/game/scores/stream')
      expect(content, file).not.toContain('LEADERBOARD_STREAM_PATH')
    }
    const composable = readFileSync(join(APP_DIR, 'composables', 'useLeaderboard.ts'), 'utf-8')
    expect(composable).not.toContain('refreshRawScores')
  })

  it('[WEB-LBOARD-011] formatRankLabel formats sub-1000 ranks exact and >=1000 ranks as K+', () => {
    expect(formatRankLabel(1)).toBe('#1')
    expect(formatRankLabel(999)).toBe('#999')
    expect(formatRankLabel(1000)).toBe('1K+')
    expect(formatRankLabel(1999)).toBe('1K+')
    expect(formatRankLabel(2500)).toBe('2K+')
    expect(formatRankLabel(10000)).toBe('10K+')
  })

  it('[WEB-LBOARD-012] ownRowPlacement chooses none, highlight, or pin', () => {
    const entries = makeEntries(25)
    expect(ownRowPlacement(entries, null, null)).toEqual({ kind: 'none' })
    expect(
      ownRowPlacement(entries, null, { authenticated: true, is_anonymous: true, player_name: 'Guest' })
    ).toEqual({ kind: 'none' })

    const signedIn = { authenticated: true, is_anonymous: false, player_name: 'Player 7' }
    expect(
      ownRowPlacement(entries, { difficulty: 'Easy', rank: 7, total_score: 9940 }, signedIn)
    ).toEqual({ kind: 'highlight', rank: 7, highlightIndex: 6 })

    expect(
      ownRowPlacement(entries, { difficulty: 'Easy', rank: 40, total_score: 4200 }, signedIn)
    ).toEqual({
      kind: 'pin',
      rank: 40,
      rankLabel: '#40',
      playerName: 'Player 7',
      totalScore: 4200
    })

    expect(
      ownRowPlacement(entries, { difficulty: 'Easy', rank: null, total_score: null }, signedIn)
    ).toEqual({
      kind: 'pin',
      rank: null,
      rankLabel: '-',
      playerName: 'Player 7',
      totalScore: 0
    })
    expect(ownRowPlacement(entries, null, signedIn)).toEqual({ kind: 'none' })
  })

  it('[WEB-LBOARD-013] [WEB-LBOARD-014] index.vue renders pinned row outside table and highlights in-list row', () => {
    const indexPage = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    const leaderboardUtil = readFileSync(join(APP_DIR, 'utils', 'leaderboard.ts'), 'utf-8')
    expect(indexPage).toContain('ownPlacement')
    expect(indexPage).toContain('ownPlacement.kind === \'pin\'')
    expect(indexPage).not.toContain('pin-unranked')
    expect(leaderboardUtil).not.toContain('not ranked yet')
    expect(indexPage).toContain('ownPlacement.value.kind === \'highlight\'')
    expect(indexPage).toContain('bg-elevated')
    expect(indexPage).toContain('border-t border-default')
  })

  it('[WEB-LBOARD-016] index.vue puts the rank in its own column before the player name', () => {
    const page = readFileSync(join(import.meta.dirname, '..', 'app', 'pages', 'index.vue'), 'utf-8')
    expect(page).toMatch(/id: 'rank', header: 'Rank'[^\n]*\n\s*\{ accessorKey: 'player_name'/)
    const rankCell = page.slice(page.indexOf('<template #rank-cell'), page.indexOf('<template #player_name-cell'))
    expect(rankCell).toContain('formatRankLabel(row.index + 1)')
    const nameCell = page.slice(page.indexOf('<template #player_name-cell'), page.indexOf('<template #total_score-cell'))
    expect(nameCell).not.toContain('formatRankLabel')
  })

  it('[WEB-LBOARD-017] index.vue keeps the table and uses its own empty state', () => {
    const page = readFileSync(join(APP_DIR, 'pages', 'index.vue'), 'utf-8')
    expect(page).not.toContain('<UEmpty')
    expect(page).not.toContain('filteredScores.length > 0 || !hasLoaded')
    expect(page).toContain(':empty="hasLoaded ? \'No scores yet\' : \'Loading...\'"')
  })

  it('[WEB-LBOARD-015] fetches /game/leaderboard/me for signed-in active tab on poll, switch, and post-run only', async () => {
    const myRankCalls: DifficultyCategory[] = []
    let signedIn = true
    const poller = createLeaderboardPoller({
      getLeaderboard: async () => makeEntries(3),
      getMyRank: async (difficulty): Promise<LeaderboardRankResponse> => {
        myRankCalls.push(difficulty)
        return { difficulty, rank: 2, total_score: 9000 }
      },
      isSignedIn: () => signedIn,
      isHidden: () => false
    })

    await poller.refreshActive({ force: true })
    await poller.switchTab('Medium')
    poller.start()
    await vi.advanceTimersByTimeAsync(20_000)
    poller.stop()
    expect(myRankCalls).toEqual(['Easy', 'Medium', 'Medium'])

    myRankCalls.length = 0
    signedIn = false
    await poller.refreshActive({ force: true })
    await poller.switchTab('Hard')
    expect(myRankCalls).toEqual([])
  })
})
