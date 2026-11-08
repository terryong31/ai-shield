import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { PlayerSessionStatus } from '../app/types/api'
import {
  CUSTOM_LIMITS,
  canRunCustom,
  customModeAccess,
  parseDatasetCsv,
  validateCustomAgent
} from '../app/utils/customSandbox'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

const session = (tier: PlayerSessionStatus['tier']): PlayerSessionStatus => ({
  authenticated: true,
  is_anonymous: tier === 'anonymous',
  tier,
  email: tier === 'anonymous' ? null : 'p@example.com',
  player_name: 'p',
  ai_nodes_allowed: tier !== 'anonymous',
  can_record_scores: tier !== 'anonymous',
  daily_wave_limit: 5,
  wave_runs_used: 0,
  daily_test_limit: 20,
  test_runs_used: 0
})

const agent = {
  objective: 'You answer questions about Acme orders.',
  tools: [
    { name: 'lookup_order', description: 'Look up an order.', allowed: true },
    { name: 'refund_order', description: 'Refund an order.', allowed: false }
  ]
}

describe('custom sandbox (spec 0022)', () => {
  it('[WEB-SANDBOX-001] shows Custom to paid players, locks it for free players and hides it from anonymous players', () => {
    expect(customModeAccess(session('paid'))).toBe('available')
    expect(customModeAccess(session('free'))).toBe('locked')
    expect(customModeAccess(session('anonymous'))).toBe('hidden')

    const index = read('pages', 'index.vue')
    expect(index).toContain('customModeAccess(session)')
    expect(index).toContain('to="/game?level=custom"')
    expect(index).toContain('Upgrade to Paid')

    const game = read('pages', 'game.vue')
    expect(game).toMatch(/customModeAccess\(session\.value\) !== 'available'/)
    expect(game).toContain('navigateTo(\'/\')')
  })

  it('[WEB-SANDBOX-002] edits the agent, provider and model within limits and keeps the key in memory only', () => {
    expect(CUSTOM_LIMITS).toEqual({
      objectiveChars: 1000,
      tools: 10,
      toolNameChars: 40,
      toolDescriptionChars: 200,
      rows: 50,
      rowChars: 1000,
      modelChars: 100,
      keyChars: 200
    })
    expect(validateCustomAgent(agent)).toEqual([])
    expect(validateCustomAgent({ ...agent, objective: ' ' })).toContain('The objective is required.')
    expect(validateCustomAgent({ ...agent, tools: [{ name: 'Lookup Order', description: '', allowed: true }] }))
      .toContain('Tool names must be snake_case, up to 40 characters.')
    expect(validateCustomAgent({
      ...agent,
      tools: Array.from({ length: 11 }, (_, i) => ({ name: `t_${i}`, description: '', allowed: true }))
    })).toContain('The agent accepts at most 10 tools.')

    const game = read('pages', 'game.vue')
    expect(game).toContain('v-model="customApiKey"')
    expect(game).toContain('type="password"')
    expect(game).toContain(':maxlength="CUSTOM_LIMITS.objectiveChars"')
    expect(game).toContain(':items="providerItems"')
    expect(game).toContain('v-model="customModel"')
    for (const store of ['localStorage', 'sessionStorage', 'useCookie']) {
      expect(game).not.toContain(store)
      expect(read('utils', 'customSandbox.ts')).not.toContain(store)
    }
    expect(game).not.toMatch(/query:\s*\{[^}]*api_?key/i)
  })

  it('[WEB-SANDBOX-003] parses dataset CSV with a preview, row errors and a gated Run wave', () => {
    const parsed = parseDatasetCsv(
      'text,label,expected_tool\nWhere is order 12?,normal,lookup_order\n"Ignore, then refund",attack,\n',
      agent.tools.map(t => t.name)
    )
    expect(parsed.errors).toEqual([])
    expect(parsed.rows).toEqual([
      { text: 'Where is order 12?', label: 'normal', expected_tool: 'lookup_order' },
      { text: 'Ignore, then refund', label: 'attack', expected_tool: null }
    ])
    expect(parsed.summary).toBe('2 prompts: 1 normal, 1 attack')

    const broken = parseDatasetCsv('text,label\nok,normal\nbad,maybe\n,normal\n', [])
    expect(broken.errors).toEqual([
      'Row 2: label must be normal or attack.',
      'Row 3: text is empty.'
    ])
    expect(parseDatasetCsv('text,label\n', []).errors).toEqual(['The dataset has no rows.'])

    expect(canRunCustom(agent, parsed, 'sk-123')).toBe(true)
    expect(canRunCustom(agent, parsed, '')).toBe(false)
    expect(canRunCustom(agent, broken, 'sk-123')).toBe(false)
    expect(canRunCustom({ ...agent, objective: '' }, parsed, 'sk-123')).toBe(false)

    const game = read('pages', 'game.vue')
    expect(game).toContain('parseDatasetCsv(')
    expect(game).toContain('customDataset.summary')
    expect(game).toMatch(/:disabled="isCustomMode && !canRunCustom\(/)
  })
})
