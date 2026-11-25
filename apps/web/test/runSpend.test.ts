import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import type { PlayerSessionStatus } from '../app/types/api'
import { planCards, runWithAnonymousRetry } from '../app/utils/gameBoard'

const APP_DIR = join(import.meta.dirname, '..', 'app')

function walkFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...walkFiles(full))
    else out.push(full)
  }
  return out
}

const FREE_SESSION: PlayerSessionStatus = {
  authenticated: true,
  is_anonymous: false,
  tier: 'free',
  email: 'ada@example.com',
  player_name: 'Ada',
  ai_nodes_allowed: true,
  can_record_scores: true,
  daily_wave_limit: 5,
  wave_runs_used: 0,
  daily_test_limit: 20,
  test_runs_used: 0
}

describe('run spend and account integrity (spec 0042)', () => {
  it('[WEB-SPEND-001] disables the Paid upgrade CTA with "Coming soon" when selfUpgradeEnabled is false', () => {
    const locked = planCards(FREE_SESSION, { selfUpgradeEnabled: false })
    expect(locked[1]!.button).toMatchObject({
      label: 'Coming soon',
      disabled: true
    })
    expect(locked[1]!.action).toBeUndefined()

    const enabled = planCards(FREE_SESSION, { selfUpgradeEnabled: true })
    expect(enabled[1]!.button).toMatchObject({
      label: 'Upgrade to Paid'
    })
    expect(enabled[1]!.button?.disabled).not.toBe(true)
    expect(enabled[1]!.action).toBe('upgrade')

    const plansPage = readFileSync(join(APP_DIR, 'pages', 'plans.vue'), 'utf-8')
    expect(plansPage).toContain('selfUpgradeEnabled')
  })

  it('[WEB-SPEND-002] removes submitScore from useShieldApi and never posts to /game/scores under apps/web/app', () => {
    const apiSource = readFileSync(join(APP_DIR, 'composables', 'useShieldApi.ts'), 'utf-8')
    expect(apiSource).not.toContain('submitScore')

    for (const file of walkFiles(APP_DIR)) {
      if (file.endsWith('api.gen.ts')) continue
      const content = readFileSync(file, 'utf-8')
      expect(content).not.toMatch(/['"`]\/game\/scores['"`]\s*,\s*\{[^}]*method:\s*['"`]POST['"`]/i)
      expect(content).not.toContain('submitScore')
    }
  })

  it('[WEB-SPEND-003] shows confirmation prompt on 202 email change and keeps the old displayed email', () => {
    const settingsSource = readFileSync(join(APP_DIR, 'pages', 'settings.vue'), 'utf-8')
    const apiSource = readFileSync(join(APP_DIR, 'composables', 'useShieldApi.ts'), 'utf-8')

    expect(apiSource).toMatch(/changeEmail:\s*\([^)]*\)\s*=>\s*api<PlayerConfirmationResponse>/)
    expect(settingsSource).toContain('Check your new inbox to confirm the change.')
    expect(settingsSource).not.toMatch(/submitEmail[\s\S]*?session\.value\s*=\s*await\s+changeEmail/)
  })

  it('[WEB-SPEND-004] opens an anonymous session once on 401 and retries once without looping', async () => {
    const signInAnonymously = vi.fn(async () => ({ ...FREE_SESSION, is_anonymous: true, tier: 'anonymous' as const }))

    let calls = 0
    const succeedOnRetry = vi.fn(async () => {
      calls += 1
      if (calls === 1) throw { statusCode: 401, data: { detail: 'Start a session to play this level.' } }
      return { level_id: 'medium-1', traces: [], score: {}, agent_mode: 'simulated' }
    })

    const res = await runWithAnonymousRetry(succeedOnRetry, signInAnonymously)
    expect(res.level_id).toBe('medium-1')
    expect(signInAnonymously).toHaveBeenCalledTimes(1)
    expect(succeedOnRetry).toHaveBeenCalledTimes(2)

    const signInAgain = vi.fn(async () => ({ ...FREE_SESSION, is_anonymous: true, tier: 'anonymous' as const }))
    const always401 = vi.fn(async () => {
      throw { statusCode: 401, data: { detail: 'Start a session to play this level.' } }
    })
    await expect(runWithAnonymousRetry(always401, signInAgain)).rejects.toMatchObject({
      statusCode: 401,
      data: { detail: 'Start a session to play this level.' }
    })
    expect(signInAgain).toHaveBeenCalledTimes(1)
    expect(always401).toHaveBeenCalledTimes(2)

    const gamePage = readFileSync(join(APP_DIR, 'pages', 'game.vue'), 'utf-8')
    expect(gamePage).toContain('runWithAnonymousRetry')
  })
})
