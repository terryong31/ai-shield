import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { LevelProgressItem, PlayerSessionStatus, WaveScoreSchema } from '../app/types/api'
import * as campaignSelect from '../app/utils/campaignSelect'
import {
  FALLBACK_CAMPAIGN_LEVELS,
  buildCategorySummaries,
  buildLevelTiles,
  calculateLevelStars,
  canAccessDifficulty,
  canAccessLevel,
  countPlacedCheckNodes,
  describeLevelConstraints,
  difficultyBadgeColor,
  isCheckDisabledByConstraints,
  nextCampaignLevel,
  toolRoleBadge
} from '../app/utils/campaignSelect'
import { waveOutcomeSummary } from '../app/utils/gameBoard'
import { readGamePage } from './support/gameSource'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

const sessionFor = (tier: PlayerSessionStatus['tier']): PlayerSessionStatus => ({
  authenticated: true,
  is_anonymous: tier === 'anonymous',
  tier,
  email: tier === 'anonymous' ? null : 'player@example.com',
  player_name: 'Player',
  ai_nodes_allowed: tier !== 'anonymous',
  can_record_scores: tier !== 'anonymous',
  daily_wave_limit: 5,
  wave_runs_used: 0,
  daily_test_limit: 20,
  test_runs_used: 0
})

describe('minimal monochrome level select and campaign briefing UI (spec 0040)', () => {
  it('[WEB-CAMP-001] renders 3 vertical UPageCard difficulty poster cards (Easy 5, Medium 7, Hard 7) with blurred padlock on locked Hard and no progress bar or score clutter', () => {
    const freeCards = buildCategorySummaries(FALLBACK_CAMPAIGN_LEVELS, sessionFor('free'))
    expect(freeCards.map(c => [c.difficulty, c.levelsCount, c.locked, c.indexLabel])).toEqual([
      ['Easy', 5, false, '5 Levels'],
      ['Medium', 7, false, '7 Levels'],
      ['Hard', 7, true, '7 Levels']
    ])

    const paidCards = buildCategorySummaries(FALLBACK_CAMPAIGN_LEVELS, sessionFor('paid'))
    expect(paidCards.map(c => c.locked)).toEqual([false, false, false])
    expect(canAccessDifficulty('Hard', sessionFor('free'))).toBe('pro_locked')
    expect(canAccessDifficulty('Hard', sessionFor('paid'))).toBe('available')

    const indexSource = read('pages', 'index.vue')
    expect(indexSource).toContain('Select Difficulty')
    expect(indexSource).toContain('<UPageCard')
    expect(indexSource).toContain('lg:flex')
    expect(indexSource).toContain('transform-gpu will-change-transform transition-transform duration-200 ease-out')
    expect(indexSource).not.toContain('min-h-88 rounded-2xl transition-all')
    expect(indexSource).toContain('buildCategorySummaries')
    expect(indexSource).toContain('blur-sm opacity-35')
    expect(indexSource).toContain('i-lucide-lock')
    expect(indexSource).toContain('CampaignUpgradeProModal')
    expect(indexSource).toContain('customModeAccess(session)')
    expect(indexSource).not.toContain('<UProgress')
    expect(indexSource).not.toContain('font-mono')
    expect((campaignSelect as Record<string, unknown>).CAMPAIGN_DIFFICULTY_COUNTS).toEqual({
      Easy: 5,
      Medium: 7,
      Hard: 7
    })
  })

  it('[WEB-CAMP-002] renders Step 2 numbered level tiles with 3-star UInputRating footers, blurred padlock on Pro-locked tiles, and opens Mission Briefing or Upgrade to Pro modals', () => {
    expect((campaignSelect as Record<string, unknown>).MAX_STARS_PER_LEVEL).toBe(3)
    expect(calculateLevelStars(null)).toBe(0)
    expect(calculateLevelStars({ won: false, medal: 'none', mastered: false })).toBe(0)
    expect(calculateLevelStars({ won: true, medal: 'bronze', mastered: false })).toBe(1)
    expect(calculateLevelStars({ won: true, medal: 'gold', mastered: false })).toBe(2)
    expect(calculateLevelStars({ won: true, medal: 'gold', mastered: true })).toBe(3)

    const progress: Record<string, LevelProgressItem> = {
      'easy-1': { level_id: 'easy-1', best_score: 9400, medal: 'gold', won: true, mastered: true },
      'easy-2': { level_id: 'easy-2', best_score: 7600, medal: 'silver', won: true, mastered: false }
    }
    const easyTiles = buildLevelTiles(FALLBACK_CAMPAIGN_LEVELS, progress, 'Easy', sessionFor('free'))
    expect(easyTiles).toHaveLength(5)
    expect(easyTiles.map(t => [t.stageNumber, t.locked, t.stars])).toEqual([
      ['01', false, 3],
      ['02', false, 1],
      ['03', false, 0],
      ['04', true, 0],
      ['05', true, 0]
    ])
    expect(easyTiles.every(t => !('isBoss' in t))).toBe(true)
    expect(read('pages', 'index.vue')).not.toContain('label="Boss"')

    const mediumTiles = buildLevelTiles(FALLBACK_CAMPAIGN_LEVELS, {}, 'Medium', sessionFor('free'))
    expect(mediumTiles).toHaveLength(7)
    expect(mediumTiles.filter(t => !t.locked).map(t => t.id)).toEqual(['medium-1', 'medium-2'])

    const hardTiles = buildLevelTiles(FALLBACK_CAMPAIGN_LEVELS, {}, 'Hard', sessionFor('paid'))
    expect(hardTiles).toHaveLength(7)
    expect(hardTiles.every(t => !t.locked)).toBe(true)

    expect(FALLBACK_CAMPAIGN_LEVELS.map(l => [l.id, l.order, l.difficulty, l.tier, l.title])).toEqual([
      ['easy-1', 1, 'Easy', 'free', 'Public Helpdesk'],
      ['easy-2', 2, 'Easy', 'free', 'Hidden in Plain Sight'],
      ['easy-3', 3, 'Easy', 'free', 'Developer Docs Trap'],
      ['easy-4', 4, 'Easy', 'pro', 'Train Your First Guard'],
      ['easy-5', 5, 'Easy', 'pro', 'Noisy Gateway'],
      ['medium-1', 6, 'Medium', 'free', 'HR Handbook'],
      ['medium-2', 7, 'Medium', 'free', 'Refund Bot'],
      ['medium-3', 8, 'Medium', 'pro', 'Poisoned Inbox'],
      ['medium-4', 9, 'Medium', 'pro', 'Lost in Translation'],
      ['medium-5', 10, 'Medium', 'pro', 'Express Lane'],
      ['medium-6', 11, 'Medium', 'pro', 'Dual-Use Refund Desk'],
      ['medium-7', 12, 'Medium', 'pro', 'CRM Boss'],
      ['hard-1', 13, 'Hard', 'pro', 'Warehouse'],
      ['hard-2', 14, 'Hard', 'pro', 'No Heavy Weapons'],
      ['hard-3', 15, 'Hard', 'pro', 'Auditor\'s Minefield'],
      ['hard-4', 16, 'Hard', 'pro', 'Polyglot'],
      ['hard-5', 17, 'Hard', 'pro', 'Finance Desk'],
      ['hard-6', 18, 'Hard', 'pro', 'Cloud Ops'],
      ['hard-7', 19, 'Hard', 'pro', 'Zero-Day']
    ])

    const indexSource = read('pages', 'index.vue')
    expect(indexSource).toContain('Select Level')
    expect(indexSource).toContain('<UInputRating')
    expect(indexSource).toContain('blur-[4px] opacity-35')
    expect(indexSource).toContain('CampaignLevelBriefingModal')
  })

  it('[WEB-CAMP-003] fetches difficulty-aggregated leaderboard entries for Easy, Medium, and Hard on the main menu', () => {
    const apiSource = read('composables', 'useShieldApi.ts')
    expect(apiSource).toContain('getLeaderboard:')
    expect(apiSource).toContain('/game/leaderboard')
    expect(apiSource).toContain('getProgress:')
    expect(apiSource).toContain('/game/progress')

    const leaderboardSource = read('composables', 'useLeaderboard.ts')
    expect(leaderboardSource).toContain('getLeaderboard')
    expect(leaderboardSource).toContain('difficultyLeaderboards')
    expect(leaderboardSource).toContain('selectedDifficulty')

    const indexSource = read('pages', 'index.vue')
    expect(indexSource).toContain('selectedLeaderboardDifficulty')
    expect(indexSource).toContain('{ accessorKey: \'player_name\', header: \'Player\' }')
    expect(indexSource).toContain('{ accessorKey: \'total_score\', header: \'Total Score\', meta: { class: { th: \'text-right\', td: \'text-right\' } } }')
    for (const hidden of ['levels_solved', 'levels_mastered', 'avg_latency_ms', 'total_cost_usd']) {
      expect(indexSource).not.toContain(hidden)
    }
    expect((campaignSelect as Record<string, unknown>).LEADERBOARD_DIFFICULTY_TABS).toEqual([
      'Easy',
      'Medium',
      'Hard'
    ])
  })

  it('[WEB-CAMP-004] displays in-game Mission Briefing, locks disabled check nodes, counts placed check nodes against max_check_nodes, gates Pro levels, and shows constraint violations and Mastery in Run results', () => {
    const formatNodeCount = (campaignSelect as Record<string, unknown>).formatNodeCountBadge as
      | ((placed: number, max: number) => string)
      | undefined
    expect(formatNodeCount?.(2, 3)).toBe('2 / 3 nodes')
    expect(isCheckDisabledByConstraints('jev', { disabled_checks: ['jev', 'safety_check'] })).toBe(true)
    expect(isCheckDisabledByConstraints('word_filter', { disabled_checks: ['jev'] })).toBe(false)

    expect(describeLevelConstraints({ max_check_nodes: 2, max_avg_latency_ms: 15, max_total_cost_usd: 0 })).toEqual([
      'Max 2 check nodes',
      'Hard latency limit: 15 ms avg',
      'Hard cost budget: $0.0000 total'
    ])

    expect(countPlacedCheckNodes([
      { data: { isAnchor: true } },
      { data: { isAnchor: false } },
      { data: { isAnchor: false } },
      { data: { isAnchor: true } }
    ])).toBe(2)

    expect(nextCampaignLevel(FALLBACK_CAMPAIGN_LEVELS, 'easy-1')?.id).toBe('easy-2')
    expect(nextCampaignLevel(FALLBACK_CAMPAIGN_LEVELS, 'easy-5')?.id).toBe('medium-1')
    expect(nextCampaignLevel(FALLBACK_CAMPAIGN_LEVELS, 'hard-8')).toBeNull()

    expect(canAccessLevel({ tier: 'free' }, sessionFor('anonymous'))).toBe('available')
    expect(canAccessLevel({ tier: 'pro' }, sessionFor('free'))).toBe('pro_locked')
    expect(canAccessLevel({ tier: 'pro' }, sessionFor('paid'))).toBe('available')

    const gameSource = readGamePage()
    expect(gameSource).toContain('@click="isBriefingOpen = true"')
    expect(gameSource).toContain('CampaignLevelBriefingModal')
    expect(gameSource).toContain('Disabled in this level')
    expect(gameSource).toContain('placedCheckNodeCount')
    expect(gameSource).toContain('Pro Level Locked')
    expect(gameSource).not.toContain('Hard constraint violated')
    expect(gameSource).toMatch(/<USeparator[^>]*\/>\s*<span class="text-sm tabular-nums text-muted">\s*\{\{ placedCheckNodeCount \}\} \/ \{\{ maxCheckNodes \}\} nodes/)
    const loss = { won: false, attacks_leaked: 0, false_alarms: 0, constraint_violations: ['Average latency 437.8 ms exceeded limit 8.0 ms.'] } as unknown as WaveScoreSchema
    expect(waveOutcomeSummary(loss)).toBe('Average latency 437.8 ms exceeded limit 8.0 ms.')
    expect(waveOutcomeSummary({ ...loss, attacks_leaked: 4 })).toBe('4 attack(s) got into the system. Average latency 437.8 ms exceeded limit 8.0 ms.')
    expect(waveOutcomeSummary({ ...loss, attacks_leaked: 4, constraint_violations: [] })).toBe('4 attack(s) got into the system.')
    expect(gameSource).toContain('follow_up_passed')
    expect(gameSource).not.toContain('follow_up_feedback')
    // A stopped run shows its stop line first (WEB-FAIR-003); other losses keep the summary.
    expect(gameSource).toMatch(/v-else-if="!waveScore\.won"\s+class="text-xs text-muted"\s+>\s+\{\{ waveOutcomeSummary\(waveScore\) \}\}/)
    expect(gameSource).toContain('label="Next Level"')
    expect(gameSource).not.toContain('label="Back to Levels"')
  })

  it('[WEB-CAMP-006] locks level-disabled palette cards like sign-in-locked cards', () => {
    const gameSource = readGamePage()
    const start = gameSource.indexOf('v-for="chk in checks"')
    const palette = gameSource.slice(start, gameSource.indexOf('</aside>', start))

    expect(gameSource).toMatch(/const isToolLocked = \(kind: NodeKind\)[\s\S]*?canUseNodeKind\(kind, session\.value, nodeKeyState\.value\)[\s\S]*?isCheckDisabledByConstraints\(kind, currentLevel\.value\.constraints\)/)
    expect(palette).toContain(':aria-disabled="isToolLocked(chk.kind)"')
    expect(palette).toContain(':draggable="!isToolLocked(chk.kind)"')
    expect(palette).toMatch(/:class="isToolLocked\(chk\.kind\) \? 'cursor-not-allowed opacity-50/)
    expect(palette).toContain('Disabled in this level')
    expect(palette).toMatch(/v-if="!isToolLocked\(chk\.kind\)"[\s\S]*?latency_ms[\s\S]*?i-lucide-ban[\s\S]*?Disabled/)
    expect(palette).not.toContain('<UBadge')
  })

  it('[WEB-CAMP-005] enforces Spec 0015 design-hygiene and icon-only modal close buttons without Close text in campaign modals', () => {
    expect((campaignSelect as Record<string, unknown>).BRIEFING_MODAL_MAX_WIDTH).toBe('sm:max-w-md')
    expect(difficultyBadgeColor('Easy')).toBe('success')
    expect(difficultyBadgeColor('Medium')).toBe('warning')
    expect(difficultyBadgeColor('Hard')).toBe('error')

    expect(toolRoleBadge({ allowed: true, dual_use: false })).toEqual({ label: 'Safe', color: 'neutral' })
    expect(toolRoleBadge({ allowed: true, dual_use: true })).toEqual({ label: 'Dual-Use', color: 'warning' })
    expect(toolRoleBadge({ allowed: false, dual_use: false })).toEqual({ label: 'Restricted', color: 'error' })

    const briefingModal = read('components', 'campaign', 'LevelBriefingModal.vue')
    const upgradeModal = read('components', 'campaign', 'UpgradeProModal.vue')

    for (const modal of [briefingModal, upgradeModal]) {
      expect(modal).toContain('<UModal')
      expect(modal).toContain('title=')
      expect(modal).toContain('<template #body>')
      expect(modal).toContain('<template #footer>')
      expect(modal).not.toMatch(/(?<!aria-)label="Close"/)
      expect(modal).not.toContain('font-mono')
    }
  })
})
