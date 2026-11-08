import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { WaveScoreSchema } from '../app/types/api'
import {
  createStarterBoard,
  scoreBreakdown
} from '../app/utils/gameBoard'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

const score = {
  protection_points: 5000,
  helpfulness_points: 3000,
  tool_points: 0,
  token_points: 0,
  speed_points: 1000,
  cost_points: 1000,
  leak_penalty: 0
} as WaveScoreSchema

describe('game level tiers (spec 0021)', () => {
  it('[WEB-LEVEL-001] ends Easy at a Help Desk with no agent settings and no tool or token score', () => {
    const finalLabel = (level: 'easy' | 'medium' | 'hard') =>
      createStarterBoard(level).nodes.find(n => n.id === 'assistant')?.data?.label
    expect(finalLabel('easy')).toBe('Help Desk')
    expect(finalLabel('medium')).toBe('Protected Agent')
    expect(finalLabel('hard')).toBe('Protected Agent')

    expect(scoreBreakdown(score, 'easy').map(r => r.label)).toEqual([
      'Protection',
      'Helpfulness',
      'Speed',
      'Cost',
      'Leak penalty'
    ])
    expect(scoreBreakdown(score, 'medium').map(r => r.label)).toContain('Tool use')

    const gameSource = read('pages', 'game.vue')
    expect(gameSource).toContain('Every prompt that reaches the help desk is answered. Stop the injections before they get here.')
    expect(gameSource).toContain('scoreBreakdown(waveScore, currentLevelId)')
    expect(gameSource).toMatch(/v-else-if="selectedNode\.data\.kind === 'assistant' && levelAgent"/)
  })

  it('[WEB-LEVEL-002] [WEB-LEVEL-004] shows no model section in the AI Agent modal', () => {
    const gameSource = read('pages', 'game.vue')
    expect(gameSource).not.toContain('modelTierCopy')
    expect(gameSource).not.toContain('levelModel')
    expect(read('utils', 'gameBoard.ts')).not.toContain('Modern model')
  })

  it('[WEB-LEVEL-003] shows no model label on the level cards', () => {
    const index = read('pages', 'index.vue')
    expect(index).not.toContain('levelModelLabel')
    for (const label of ['No AI model', 'Modern AI model', 'Budget AI model']) {
      expect(index).not.toContain(label)
      expect(read('utils', 'gameBoard.ts')).not.toContain(label)
    }
  })
})

describe('final node naming (spec 0021)', () => {
  it('[WEB-LEVEL-005] explains the final node and heads its objective System Instruction', () => {
    const gameSource = read('pages', 'game.vue')
    expect(gameSource).toContain('Wire your last check here. Everything that arrives gets answered, so only let safe prompts through.')
    expect(gameSource).toContain('System Instruction')
    expect(gameSource).not.toMatch(/>\s*Objective\s*</)
    expect(gameSource).toContain('final_node_label: \'Protected Agent\'')
    expect(read('utils', 'gameBoard.ts')).not.toContain('\'AI Agent\'')
  })
})
