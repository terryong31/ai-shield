import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { ScoreRecord } from '../app/types/api'
import { consoleScoreStats } from '../app/utils/gameBoard'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

const REMOVED_FILES = [
  'components/chat/ChatInterface.vue',
  'components/dashboard/DashboardPipeline.vue',
  'components/dashboard/DashboardStats.vue',
  'components/workflow/AgentNode.vue',
  'components/workflow/DualAgentNode.vue',
  'components/workflow/MLNode.vue',
  'components/workflow/NodeContainer.vue',
  'components/workflow/OblivionNode.vue',
  'components/workflow/SwitchNode.vue',
  'components/workflow/ToolboxNode.vue',
  'components/workflow/UserNode.vue',
  'components/workflow/WorkflowVisualizer.vue',
  'composables/useByodSecrets.ts',
  'composables/useSecurityMode.ts',
  'composables/useShieldWorkflow.ts',
  'utils/chatStream.ts',
  'utils/audit.ts',
  'utils/pipelineGraph.ts',
  'types/workflow.ts',
  'pages/dashboard/index.vue',
  'pages/dashboard/logs.vue',
  'pages/dashboard/settings.vue',
  'pages/console/logs.vue'
]

describe('game-only web app (spec 0026)', () => {
  it('[WEB-CLEAN-001] has no legacy chat, pipeline or audit files and no legacy API methods', () => {
    const present = REMOVED_FILES.filter(file => existsSync(join(APP_DIR, file)))
    expect(present).toEqual([])

    const api = read('composables', 'useShieldApi.ts')
    for (const method of ['streamChat', '/chat', '/screen', '/predict', '/requests', '/stats', '/feedback', 'getAudit', 'getStats', 'sendFeedback']) {
      expect(api).not.toContain(method)
    }
    expect(read('types', 'api.ts')).not.toMatch(/ChatEvent|ChatRequest|AuditRecord|StatsResponse|FeedbackRequest/)
  })

  it('[WEB-CLEAN-002] keeps a game-only admin console', () => {
    const layout = read('layouts', 'dashboard.vue')
    expect(layout).toContain('label: \'Overview\'')
    expect(layout).toContain('label: \'Settings\'')
    expect(layout).toContain('label: \'Main menu\'')
    expect(layout).not.toContain('Audit logs')
    expect(layout).not.toContain('/_console/logs')

    const overview = read('pages', 'console', 'index.vue')
    expect(overview).toContain('consoleScoreStats(scores.value)')
    expect(overview).toContain('label="Clear scoreboard"')
    expect(overview).toContain('clearScores()')
    expect(overview).not.toMatch(/DashboardStats|DashboardPipeline|getStats|block_rate/)
    expect(overview.toLowerCase()).toContain('admin access required')

    const base = { id: 'x', created_at: '2026-11-09T00:00:00Z', attacks_blocked: 4, attacks_total: 4, false_alarms: 0, avg_latency_ms: 1, total_cost_usd: 0, won: true, mastered: false }
    const stats = consoleScoreStats([
      { ...base, player_name: 'Ada', level_id: 'easy-1', total_score: 9000, medal: 'gold' },
      { ...base, player_name: 'Ada', level_id: 'medium-1', total_score: 4000, medal: 'bronze' },
      { ...base, player_name: 'Grace', level_id: 'easy-2', total_score: 7000, medal: 'silver' }
    ] as ScoreRecord[])
    expect(stats).toEqual({
      scores: 3,
      players: 2,
      byLevel: { easy: 2, medium: 1, hard: 0 },
      medals: { gold: 1, silver: 1, bronze: 1, none: 0 }
    })
  })
})
