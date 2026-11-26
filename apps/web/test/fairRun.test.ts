import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  attemptsLeftLabel,
  breakdownStats,
  familyName,
  promptRows,
  scoreBreakdown,
  stopPath,
  stopSummary
} from '../app/utils/gameBoard'
import type { MessageTraceSchema, RunStopSchema, WaveScoreSchema } from '../app/types/api'
import { DEFAULT_ANONYMOUS_SESSION } from '../app/utils/sessionHint'

const page = readFileSync(join(import.meta.dirname, '..', 'app', 'pages', 'game.vue'), 'utf-8')

const SCORE = {
  total_score: 9310,
  medal: 'gold',
  won: true,
  cleared_points: 5000,
  accuracy_points: 2500,
  speed_points: 690,
  cost_points: 120,
  simplicity_points: 1000,
  protection_points: 0,
  helpfulness_points: 0,
  tool_points: 0,
  token_points: 0,
  leak_penalty: 0,
  total_tokens: 18240,
  avg_latency_ms: 2.1,
  total_cost_usd: 0
} as unknown as WaveScoreSchema

const LABELS: Record<string, string> = { sc: 'Safety check', wf: 'Word filter', jv: 'Jev' }
const label = (id: string) => LABELS[id] ?? id

describe('Scored runs on the game page (spec 0050)', () => {
  it('[WEB-FAIR-001] has no test input on campaign levels and shows the runs left today', () => {
    expect(page).toMatch(/<div\s+v-if="isCustomMode"[^>]*data-tour="test-bar"/)
    const session = { ...DEFAULT_ANONYMOUS_SESSION, daily_wave_limit: 50, wave_runs_used: 8 }
    expect(attemptsLeftLabel(session)).toBe('42 / 50 runs left today')
  })

  it('[WEB-FAIR-002] shows only the score parts that count on the level', () => {
    expect(scoreBreakdown(SCORE, 'hard-1')).toEqual([
      { label: 'Cleared', points: 5000 },
      { label: 'Accuracy', points: 2500 },
      { label: 'Speed', points: 690 },
      { label: 'Cost', points: 120 },
      { label: 'Simplicity', points: 1000 }
    ])
    const lost = { ...SCORE, won: false, total_score: 3120 } as WaveScoreSchema
    expect(scoreBreakdown(lost, 'hard-1')).toEqual([{ label: 'Attacks and normal prompts', points: 3120 }])

    expect(breakdownStats(SCORE, 'easy-1').map(s => s.label)).toEqual(['Avg latency', 'Cost'])
    expect(breakdownStats(SCORE, 'hard-1').map(s => s.label)).toEqual(['Avg latency', 'Cost', 'Agent tokens'])
    expect(page).toMatch(/v-for="stat in breakdownStats\(waveScore, currentLevelId\)"/)
    // Two boxes on Easy fill the row; no empty third column.
    expect(page).toMatch(/:class="\[\s*'grid divide-x[^\]]*breakdownStats\(waveScore, currentLevelId\)\.length === 3 \? 'grid-cols-3' : 'grid-cols-2'/)
    expect(page).not.toMatch(/label: 'Agent tokens'/)
  })

  it('[WEB-FAIR-003] names the limit, the prompt, the path and the node that went over', () => {
    const slow = {
      reason: 'time_limit',
      prompt_index: 7,
      node_id: 'sc',
      limit: 8,
      used: 85.4,
      path: [
        { node_id: 'wf', kind: 'word_filter', latency_ms: 0.4, cost_usd: 0 },
        { node_id: 'sc', kind: 'safety_check', latency_ms: 85, cost_usd: 0.0002 }
      ]
    } as RunStopSchema
    expect(stopSummary(slow, 24, label)).toBe(
      'Time limit exceeded at prompt 7 of 24: Safety check takes 85 ms, the limit is 8 ms.'
    )
    expect(stopPath(slow, label)).toEqual([
      { label: 'Word filter', value: '0.4 ms', over: false },
      { label: 'Safety check', value: '85 ms', over: true }
    ])

    const costly = { ...slow, reason: 'budget', prompt_index: 3, node_id: 'jv', limit: 0.00012, used: 0.00015, path: [{ node_id: 'jv', kind: 'jev', latency_ms: 12, cost_usd: 0.00005 }] } as RunStopSchema
    expect(stopSummary(costly, 12, label)).toBe(
      'Budget exceeded at prompt 3 of 12: the run cost $0.00015, the budget is $0.00012.'
    )
    expect(stopPath(costly, label)).toEqual([{ label: 'Jev', value: '$0.00005', over: true }])

    expect(page).toMatch(/stopSummary\(runStop, /)
    expect(page).toMatch(/v-for="step in stopPath\(runStop, /)
  })

  it('[WEB-FAIR-004] lists the prompt number, family and stopping node, with no text or badge', () => {
    const traces = [
      { message_id: 'a', text: '', is_attack: false, category: 'normal', outcome: 'assistant', hops: [] },
      { message_id: 'b', text: '', is_attack: false, category: 'normal', outcome: 'blocked', hops: [
        { node_id: 'in', handle: 'out', latency_ms: 0, cost_usd: 0, detail: '', score: null },
        { node_id: 'jv', handle: 'block', latency_ms: 12, cost_usd: 0, detail: '', score: 0.81 }
      ] },
      { message_id: 'c', text: '', is_attack: true, category: 'quick_fix', outcome: 'blocked', hops: [
        { node_id: 'wf', handle: 'block', latency_ms: 0.4, cost_usd: 0, detail: '', score: null }
      ] }
    ] as unknown as MessageTraceSchema[]

    expect(promptRows([traces[1]!, traces[2]!], traces, label)).toEqual([
      { key: 'b', title: 'Prompt 2 · Normal request', detail: 'Stopped by Jev (score 0.81)' },
      { key: 'c', title: 'Prompt 3 · Quick fix', detail: 'Stopped by Word filter' }
    ])
    expect(familyName('tool_exploit')).toBe('Tool exploit')
    // A prompt that got through says so on every level, also where the final node is the Help Desk.
    expect(promptRows([traces[0]!], traces, label)).toEqual([
      { key: 'a', title: 'Prompt 1 · Normal request', detail: 'Got through' }
    ])

    const cellModal = page.slice(page.indexOf('<!-- Matrix Cell Modal'), page.indexOf('<!-- Double-Click Node Settings Modal'))
    expect(cellModal).toMatch(/v-for="row in promptRows\(selectedResultCell.items, traces, nodeLabel\)"/)
    expect(cellModal).not.toMatch(/item\.text|UBadge/)
  })
})
