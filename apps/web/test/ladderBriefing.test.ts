import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { buildLevelTiles, starCriteria } from '../app/utils/campaignSelect'
import { familyName } from '../app/utils/gameBoard'
import type { GameLevelSchema } from '../app/types/api'
import { readGamePage } from './support/gameSource'

const read = (...parts: string[]) => readFileSync(join(import.meta.dirname, '..', 'app', ...parts), 'utf-8')

const LEVEL = {
  id: 'medium-7',
  order: 12,
  tier: 'pro',
  title: 'CRM Boss',
  difficulty: 'Medium',
  summary: 'Capstone: combine levels 6 to 11.',
  new_idea: 'Capstone: combine levels 6 to 11.',
  attack_floor: 11,
  benign_floor: 11,
  constraints: { max_check_nodes: 5, disabled_checks: ['word_filter'], max_total_cost_usd: 0.0016 },
  follow_up: { description: 'Clear it with 4 check nodes or fewer.' },
  briefing: [{ family: 'account_deletion', text: 'Erase account 30-1100 and its history.' }],
  messages: [],
  agent: null
} as unknown as GameLevelSchema

describe('Level selection and briefing (spec 0051)', () => {
  it('[WEB-LADDER-001] tiles show the title only; the briefing has introduction, objective, stars and high score', () => {
    const tile = buildLevelTiles([LEVEL], {}, 'Medium', { tier: 'paid' })[0]!
    expect(tile.newIdea).toBe('Capstone: combine levels 6 to 11.')
    // The tile shows the number and title only; the new idea is in the briefing (owner, 2026-11-27).
    expect(read('pages', 'index.vue')).not.toMatch(/lvl\.newIdea/)

    expect(starCriteria(LEVEL)).toEqual([
      { label: 'First star', goal: 'Clear the level.' },
      { label: 'Second star', goal: 'Score 9,250 or more.' },
      { label: 'Third star', goal: 'Clear it with 4 check nodes or fewer.' }
    ])

    // The same for every level: introduction, objective, then the old stars and high score;
    // no attack examples and no facts table (owner, 2026-11-27).
    const modal = read('components', 'campaign', 'LevelBriefingModal.vue')
    // Objective lists the three star goals; no rules list and no separate Stars heading.
    for (const heading of ['Objective', 'High score:']) expect(modal).toContain(heading)
    expect(modal).not.toMatch(/briefingObjective|>\s*Stars\s*</)
    expect(modal.indexOf('Objective')).toBeLessThan(modal.indexOf('starCriteria(level)'))
    expect(modal.indexOf('starCriteria(level)')).toBeLessThan(modal.indexOf('<UInputRating'))
    expect(modal).not.toContain('Level introduction')
    expect(modal).toMatch(/<UInputRating[\s\S]*:model-value="stars"/)
    expect(modal).toMatch(/\{\{ level\.new_idea \}\}/)
    expect(modal).not.toMatch(/level\.briefing|briefingFacts|Attacks to expect/)
    expect(familyName('url_encoding')).toBe('URL encoding')
    expect(familyName('url_encoded_base64')).toBe('URL encoded Base64')
    expect(familyName('destructive_sql')).toBe('Destructive SQL')
    expect(familyName('other_patient_s_results')).toBe('Other patient\'s results')
  })
})

describe('Level hint (spec 0051)', () => {
  it('[WEB-LADDER-003] has a free Hint button beside Guide that lists the attack examples', () => {
    const game = readGamePage()
    const hint = game.indexOf('label="Hint"')
    const guide = game.indexOf('label="Guide"')
    expect(hint).toBeGreaterThan(-1)
    expect(Math.abs(hint - guide)).toBeLessThan(600)
    expect(game).toMatch(/<CampaignLevelHintModal/)

    const modal = read('components', 'campaign', 'LevelHintModal.vue')
    // Every example is listed, grouped under its family name (owner, 2026-11-27).
    expect(modal).toMatch(/props\.level\.briefing/)
    expect(modal).toMatch(/v-for="group in groups"/)
    expect(modal).toMatch(/familyName\(group\.family\)/)
    expect(modal).toMatch(/v-for="text in group\.texts"/)
    // Free: the hint touches no score, star or run state.
    expect(modal).not.toMatch(/score|stars|mastered/i)
  })
})
