import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { MessageTraceSchema, PlayerSessionStatus, WaveScoreSchema } from '../app/types/api'
import {
  AGENT_RULE_LIMIT,
  AGENT_RULE_MAX_CHARS,
  NODE_CATALOG,
  addAgentRule,
  addCheckNode,
  boardFromSave,
  agentRulesFrom,
  applyWaveSummary,
  canAddAgentRule,
  connectBoardEdge,
  createStarterBoard,
  formatToolName,
  markBoardRunning,
  needsSignInPrompt,
  confusionMatrix,
  nodeCostLine,
  runsRemaining,
  attemptsLeftLabel,
  nextHighScore,
  isNewRecord,
  nextHighStars,
  starsForMedal,
  scoreBreakdown,
  summarizeNodeTraffic,
  toApiBoard,
  travelledEdgeIds,
  unwiredHandles
} from '../app/utils/gameBoard'

const APP_DIR = join(import.meta.dirname, '..', 'app')
const read = (...parts: string[]) => readFileSync(join(APP_DIR, ...parts), 'utf-8')

const anonSession: PlayerSessionStatus = {
  authenticated: true,
  is_anonymous: true,
  tier: 'anonymous',
  email: null,
  player_name: 'Anonymous',
  ai_nodes_allowed: false,
  can_record_scores: false,
  daily_wave_limit: 1,
  wave_runs_used: 0,
  daily_test_limit: 3,
  test_runs_used: 3
}

function trace(hops: Array<[string, MessageTraceSchema['hops'][number]['handle']]>, outcome: 'assistant' | 'blocked'): MessageTraceSchema {
  return {
    message_id: 'm',
    text: 'hello',
    is_attack: false,
    outcome,
    total_latency_ms: 1,
    total_cost_usd: 0,
    hops: hops.map(([node_id, handle]) => ({ node_id, handle, latency_ms: 0, cost_usd: 0, detail: '' })),
    agent: null
  }
}

function boardWithFilter() {
  const withFilter = addCheckNode(createStarterBoard('easy'), 'word_filter', { x: 240, y: 120 })
  const wiredIn = connectBoardEdge(withFilter, { source: 'incoming', sourceHandle: 'out', target: 'word_filter' })
  return connectBoardEdge(wiredIn, { source: 'word_filter', sourceHandle: 'safe', target: 'assistant' })
}

describe('game AI agent (spec 0020)', () => {
  it('[WEB-AGENT-001] starts every level with only Input and AI Agent nodes', () => {
    for (const level of ['easy', 'medium', 'hard'] as const) {
      const board = createStarterBoard(level)
      expect(board.nodes.map(n => n.data?.kind)).toEqual(['incoming', 'assistant'])
      // Easy ends at a Help Desk instead (WEB-LEVEL-001, spec 0021)
      expect(board.nodes.find(n => n.id === 'assistant')?.data?.label).toBe(level === 'easy' ? 'Help Desk' : 'Protected Agent')
    }
    expect(Object.keys(NODE_CATALOG)).not.toContain('blocked')
    expect(read('pages', 'game.vue')).not.toContain('\'blocked\'')
  })

  it('[WEB-AGENT-002] edits up to 5 rules of 200 characters and sends them as config.rules', () => {
    expect(AGENT_RULE_LIMIT).toBe(5)
    expect(AGENT_RULE_MAX_CHARS).toBe(200)

    let rules: string[] = []
    rules = addAgentRule(rules, '  Never share discount codes.  ')
    rules = addAgentRule(rules, '   ')
    rules = addAgentRule(rules, 'x'.repeat(250))
    expect(rules).toEqual(['Never share discount codes.', 'x'.repeat(200)])

    const full = ['a', 'b', 'c', 'd', 'e']
    expect(canAddAgentRule(full)).toBe(false)
    expect(addAgentRule(full, 'f')).toEqual(full)
    expect(canAddAgentRule(rules)).toBe(true)

    expect(agentRulesFrom({ rules: ['keep', 3, 'also'] })).toEqual(['keep', 'also'])
    expect(agentRulesFrom({})).toEqual([])

    const board = createStarterBoard('easy')
    const withRules = {
      ...board,
      nodes: board.nodes.map(n => n.id === 'assistant' && n.data
        ? { ...n, data: { ...n.data, config: { ...n.data.config, rules } } }
        : n)
    }
    const payload = toApiBoard(withRules)
    expect(payload.nodes.find(n => n.kind === 'assistant')?.config.rules).toEqual(rules)

    const gameSource = read('pages', 'game.vue')
    expect(gameSource).toContain('levelAgent?.objective')
    expect(gameSource).toContain(':maxlength="AGENT_RULE_MAX_CHARS"')
    expect(gameSource).toContain('/ {{ AGENT_RULE_MAX_CHARS }}')
    expect(gameSource).toContain('updateNodeConfig(\'rules\'')
    expect(gameSource).toContain(':disabled="!canAddAgentRule(')
  })

  it('[WEB-AGENT-003] counts the runs anonymous players have left (the run prompt is replaced by WEB-AGENT-015)', () => {
    expect(needsSignInPrompt(anonSession)).toBe(true)
    expect(needsSignInPrompt({ ...anonSession, is_anonymous: false, tier: 'free' })).toBe(false)
    expect(runsRemaining(anonSession, 'wave')).toBe(1)
    expect(runsRemaining(anonSession, 'test')).toBe(0)
    expect(runsRemaining({ ...anonSession, daily_wave_limit: null }, 'wave')).toBeNull()

    const gameSource = read('pages', 'game.vue')
    expect(gameSource).toContain('v-model:open="isSignInPromptOpen"')
    expect(gameSource).toContain('to="/auth/login"')
  })

  it('[WEB-AGENT-015] shows attempts left beside the score and runs without a sign-in prompt', () => {
    expect(attemptsLeftLabel(anonSession)).toBe('1/1 attempts left today')
    expect(attemptsLeftLabel({ ...anonSession, wave_runs_used: 1 })).toBe('0/1 attempts left today')
    expect(attemptsLeftLabel({ ...anonSession, daily_wave_limit: null })).toBe('')

    const gameSource = read('pages', 'game.vue')
    expect(gameSource).not.toContain('Run anyway')
    expect(gameSource).not.toContain('Sign in to keep your score')
    expect(gameSource).not.toContain('openSignInPrompt(\'wave\')')
    expect(gameSource).not.toContain('openSignInPrompt(\'test\')')
    expect(gameSource).not.toContain('pendingRunKind')
    expect(gameSource).toContain('@click="handleRunWave()"')
    expect(gameSource).toContain('{{ attemptsLeftLabel(session) }}')
    expect(gameSource).toContain('runsRemaining(session, \'wave\') === 0')
    expect(gameSource).not.toContain('formatQuotaSummary')
  })

  it('[WEB-AGENT-016] puts the wave stats beside the score and the attempts counter beside Save', () => {
    const gameSource = read('pages', 'game.vue')
    const header = gameSource.slice(gameSource.indexOf('<header'), gameSource.indexOf('</header>'))
    const runBar = gameSource.slice(gameSource.indexOf('</header>'), gameSource.indexOf('placeholder="Test a message..."'))

    expect(header).toMatch(/v-if="waveScore"[\s\S]*?label="Results"[\s\S]*?<USeparator[\s\S]*?orientation="vertical"[\s\S]*?Score:/)
    expect(runBar).not.toContain('avg_latency_ms')
    expect(runBar).not.toContain('label="Results"')
    expect(runBar).toMatch(/label="Save"[\s\S]*?<USeparator[\s\S]*?orientation="vertical"[\s\S]*?attemptsLeftLabel\(session\)/)
    expect(header).not.toContain('attemptsLeftLabel')
  })

  it('[WEB-AGENT-017] shows plain stars and a High Score in the header and the stats and breakdown in Run results', () => {
    expect(nextHighScore(null, 1200)).toBe(1200)
    expect(nextHighScore(1500, 1200)).toBe(1500)
    expect(nextHighScore(1500, 2100)).toBe(2100)

    const gameSource = read('pages', 'game.vue')
    const header = gameSource.slice(gameSource.indexOf('<header'), gameSource.indexOf('</header>'))
    const results = gameSource.slice(
      gameSource.indexOf('v-model:open="isResultsOpen"'),
      gameSource.indexOf('<!-- Double-Click Node Settings Modal -->')
    )

    expect(header).toContain('High Score:')
    expect(header).not.toMatch(/>\s*Score:/)
    expect(header).not.toContain('UPopover')
    expect(header).not.toContain('scoreBreakdown')
    expect(header).not.toContain('avg_latency_ms')
    expect(header).not.toContain('total_cost_usd')
    expect(header).toMatch(/label="Results"[^>]*?size="lg"/)
    expect(header).toMatch(/<UInputRating[\s\S]*?readonly[\s\S]*?\/>/)

    expect(results).toContain('scoreBreakdown(waveScore, currentLevelId)')
    expect(results).toContain('waveScore.avg_latency_ms')
    expect(results).toContain('waveScore.total_cost_usd')
    expect(results).toContain('waveScore.total_tokens')

    expect(gameSource).toMatch(/highScore\.value = nextHighScore\(highScore\.value, response\.score\.total_score\)/)
  })

  it('[WEB-AGENT-019] always shows the high-score stars to the right of High Score', () => {
    expect(nextHighStars(null, 0, 9000, 'gold')).toBe(3)
    expect(nextHighStars(9000, 3, 8000, 'bronze')).toBe(3)
    expect(nextHighStars(8000, 1, 9500, 'silver')).toBe(2)

    const gameSource = read('pages', 'game.vue')
    const header = gameSource.slice(gameSource.indexOf('<header'), gameSource.indexOf('</header>'))
    expect(header).toMatch(/High Score:[\s\S]*?<\/span>\s*<UInputRating[\s\S]*?:model-value="highStars"[\s\S]*?readonly/)
    const waveOnly = header.slice(header.indexOf('v-if="waveScore"'), header.indexOf('High Score:'))
    expect(waveOnly).not.toContain('UInputRating')
    expect(gameSource).toMatch(/highStars\.value = nextHighStars\(highScore\.value, highStars\.value, response\.score\.total_score, response\.score\.medal\)/)
  })

  it('[WEB-AGENT-020] shows the confusion matrix in Score breakdown, not in Run results', () => {
    const gameSource = read('pages', 'game.vue')
    const modal = (marker: string) => {
      const start = gameSource.indexOf(marker)
      return gameSource.slice(start, gameSource.indexOf('</UModal>', start))
    }
    const results = modal('v-model:open="isResultsOpen"')
    const breakdown = modal('v-model:open="isBreakdownOpen"')

    expect(results).not.toContain('resultCells')
    expect(results).not.toContain('Got through')
    expect(breakdown).toMatch(/scoreBreakdown\(waveScore, currentLevelId\)[\s\S]*?Got through[\s\S]*?Stopped[\s\S]*?v-for="cell in resultCells"[\s\S]*?@click="openResultCell\(cell\.key\)"/)
  })

  it('[WEB-AGENT-021] folds the points into a collapsed accordion and polishes the breakdown modal', () => {
    const gameSource = read('pages', 'game.vue')
    const start = gameSource.indexOf('v-model:open="isBreakdownOpen"')
    const breakdown = gameSource.slice(start, gameSource.indexOf('</UModal>', start))

    expect(gameSource).toMatch(/const breakdownAccordionItems = \[\{ label: 'Points', value: 'points'/)
    expect(breakdown).toMatch(/<UAccordion[\s\S]*?:items="breakdownAccordionItems"[\s\S]*?#body[\s\S]*?scoreBreakdown\(waveScore, currentLevelId\)/)
    expect(breakdown).not.toMatch(/<UAccordion[^>]*default-value/)
    expect(breakdown).toContain('(row.points || 0).toLocaleString()')
    expect(breakdown).toMatch(/<\/UAccordion>\s*<div[\s\S]*?Prompt outcomes/)
    expect(breakdown).not.toContain('border-t border-default pt-4')
    expect(breakdown).not.toContain('<USeparator')
    expect(breakdown).toContain('Click a cell to see its prompts.')
    for (const icon of ['i-lucide-timer', 'i-lucide-coins', 'i-lucide-cpu']) expect(breakdown).toContain(icon)
    expect(breakdown).toMatch(/v-for="cell in resultCells"[\s\S]*?:name="cell\.icon"/)
  })

  it('[WEB-AGENT-018] leads Run results with stars, score and New record, and opens the breakdown and each matrix cell in modals', () => {
    expect(isNewRecord(null, 9000)).toBe(false)
    expect(isNewRecord(9000, 9000)).toBe(false)
    expect(isNewRecord(9000, 9500)).toBe(true)

    const gameSource = read('pages', 'game.vue')
    const start = gameSource.indexOf('v-model:open="isResultsOpen"')
    const results = gameSource.slice(start, gameSource.indexOf('</UModal>', start))

    expect(gameSource).not.toContain('Green cells are what your board got right.')
    expect(results).not.toContain(':description=')
    expect(results).toMatch(/<UInputRating[\s\S]*?waveScore\.total_score[\s\S]*?New record![\s\S]*?label="Show breakdown"/)
    expect(results).toContain('v-if="newRecord"')
    expect(results).toContain('@click="isBreakdownOpen = true"')
    expect(gameSource).toMatch(/v-for="cell in resultCells"[\s\S]*?@click="openResultCell\(cell\.key\)"/)
    expect(results).not.toContain('scoreBreakdown(')
    expect(results).not.toContain('lastHopDetail(')

    expect(gameSource).toContain('v-model:open="isBreakdownOpen"')
    expect(gameSource).toContain('title="Score breakdown"')
    expect(gameSource).toContain('v-model:open="isResultCellOpen"')
    expect(gameSource).toMatch(/v-for="item in selectedResultCell\.items"/)
    expect(gameSource).toContain('lastHopDetail(item)')
    expect(gameSource).toMatch(/newRecord\.value = isNewRecord\(highScore\.value, response\.score\.total_score\)/)
  })

  it('[WEB-AGENT-004] shows every score component and per-message agent results', () => {
    const score: WaveScoreSchema = {
      total_score: 6325,
      medal: 'bronze',
      protection_points: 3200,
      helpfulness_points: 1300,
      tool_points: 500,
      token_points: 1125,
      speed_points: 600,
      cost_points: 600,
      leak_penalty: 1000,
      attacks_protected: 4,
      attacks_total: 5,
      attacks_leaked: 1,
      benign_helped: 4,
      benign_total: 5,
      false_alarms: 1,
      total_tokens: 2000,
      avg_latency_ms: 400,
      total_cost_usd: 0.002
    }
    expect(scoreBreakdown(score)).toEqual([
      { label: 'Protection', points: 3200 },
      { label: 'Helpfulness', points: 1300 },
      { label: 'Tool use', points: 500 },
      { label: 'Tokens', points: 1125 },
      { label: 'Speed', points: 600 },
      { label: 'Cost', points: 600 },
      { label: 'Leak penalty', points: -1000 }
    ])

    const gameSource = read('pages', 'game.vue')
    expect(gameSource).toContain('scoreBreakdown(waveScore, currentLevelId)')
    expect(gameSource).toContain('waveScore.total_tokens')
  })

  it('[WEB-AGENT-005] renders nodes with labelled ports and traffic counts, without status, info or unwired clutter', () => {
    const board = boardWithFilter()
    expect(unwiredHandles('word_filter', ['safe', 'block'], board.edges)).toEqual(['block'])

    const traffic = summarizeNodeTraffic([
      trace([['incoming', 'out'], ['word_filter', 'safe'], ['assistant', 'done']], 'assistant'),
      trace([['incoming', 'out'], ['word_filter', 'block']], 'blocked')
    ])
    expect(traffic.word_filter).toEqual({ in: 2, pass: 1, block: 1 })
    expect(traffic.assistant).toEqual({ in: 1, pass: 1, block: 0 })

    const nodeSource = read('components', 'workflow', 'GameNode.vue')
    expect(nodeSource).toContain('Position.Left')
    expect(nodeSource).toContain('Position.Right')
    expect(nodeSource).not.toContain('stops here')
    expect(nodeSource).not.toContain('i-lucide-info')
    expect(nodeSource).not.toContain('statusAppearance')
    expect(nodeSource).not.toContain('rules added')
    expect(nodeSource).toContain('data.traffic.pass')
    expect(nodeSource).toContain('data.traffic.block')
    expect(nodeSource).toContain('data.isAnchor ?')
  })

  it('[WEB-AGENT-006] animates travelled edges and shows idle, running and done states', () => {
    const board = boardWithFilter()
    const running = markBoardRunning(board)
    expect(running.nodes.every(n => n.data?.status === 'active')).toBe(true)
    expect(running.edges.every(e => e.animated)).toBe(true)

    const traces = [trace([['incoming', 'out'], ['word_filter', 'block']], 'blocked')]
    expect(travelledEdgeIds(board, traces)).toEqual(['e-incoming-out-word_filter'])

    const done = applyWaveSummary(running, traces)
    expect(done.edges.find(e => e.id === 'e-incoming-out-word_filter')?.animated).toBe(true)
    expect(done.edges.find(e => e.id === 'e-word_filter-safe-assistant')?.animated).toBe(false)
    expect(done.nodes.find(n => n.id === 'word_filter')?.data?.status).toBe('passed')
    expect(done.nodes.find(n => n.id === 'assistant')?.data?.status).toBe('idle')

    const gameSource = read('pages', 'game.vue')
    expect(gameSource).toContain('markBoardRunning(')
  })

  it('[WEB-AGENT-007] lays out the AI Agent modal with tool rows and a rules composer', () => {
    const gameSource = read('pages', 'game.vue')
    expect(gameSource).toContain('\'Restricted\'')
    expect(gameSource).not.toContain('Never call')
    expect(gameSource).toContain('<UTextarea')
    expect(gameSource).toContain('title="No rules yet"')
    expect(gameSource).toContain('title="No runs yet"')
  })

  it('[WEB-AGENT-008] drops the level badge and suggestions, shows plain tool names, and keeps the scrollbar from shifting content', () => {
    expect(formatToolName('lookup_order')).toBe('Lookup Order')
    expect(formatToolName('issue_discount')).toBe('Issue Discount')
    expect(formatToolName('run_sql')).toBe('Run SQL')

    const gameSource = read('pages', 'game.vue')
    expect(gameSource).not.toContain('Set by the level')
    expect(gameSource).not.toContain('Suggested rules')
    expect(gameSource).not.toContain('font-mono')
    expect(gameSource).toContain('formatToolName(tool.name)')
    expect(gameSource).toContain('[scrollbar-gutter:stable]')
    expect(gameSource).toContain('[scrollbar-color:var(--ui-border-accented)_transparent]')
  })

  it('[WEB-AGENT-009] gives the Input and tool node modals the AI Agent modal layout', () => {
    const gameSource = read('pages', 'game.vue')
    const nodeModal = gameSource.slice(gameSource.indexOf('<!-- Double-Click Node Settings Modal -->'))
    expect(nodeModal).toContain('content: \'sm:max-w-2xl\'')
    expect(nodeModal).toContain('What this node does')
    expect(nodeModal).toContain('What it does')
    // The Outputs form was removed; wiring happens on the canvas (WEB-AGENT-012).
    expect(gameSource).not.toContain('handleAddWire')
    expect(gameSource).not.toContain('`-> ${')
  })

  it('[WEB-AGENT-010] shows latency and cost in the header and stars instead of Last run', () => {
    expect(starsForMedal('gold')).toBe(3)
    expect(starsForMedal('silver')).toBe(2)
    expect(starsForMedal('bronze')).toBe(1)
    expect(starsForMedal('none')).toBe(0)

    expect(nodeCostLine(0.2, 0)).toBe('0.2 ms per message · Free')
    expect(nodeCostLine(85, 0.0002)).toBe('85 ms per message · $0.0002')

    const gameSource = read('pages', 'game.vue')
    const nodeModal = gameSource.slice(gameSource.indexOf('<!-- Double-Click Node Settings Modal -->'))
    expect(nodeModal).not.toContain('Remove node')
    expect(gameSource).not.toContain('handleRemoveSelectedNode')
    expect(nodeModal).not.toContain('<UTabs')
    expect(gameSource).not.toContain('Last run')
    expect(gameSource).not.toContain('slot: \'last-run\'')
    expect(nodeModal).not.toContain('ms per message ·')
    expect(gameSource).toContain(':description="nodeModalDescription"')
    expect(gameSource).toContain('nodeCostLine(')
    // The per-node Last wave summary moved to the Run results modal (WEB-AGENT-011).
    expect(gameSource).toMatch(/<UInputRating[^>]*readonly/)
    expect(gameSource).toContain('starsForMedal(waveScore.medal)')
  })

  it('[WEB-AGENT-011] shows a confusion matrix of the run instead of a per-node Last wave', () => {
    const base = (id: string, isAttack: boolean, outcome: 'assistant' | 'blocked', verdict: string | null) => ({
      ...trace([['incoming', 'out']], outcome),
      message_id: id,
      text: `prompt ${id}`,
      is_attack: isAttack,
      agent: verdict
        ? {
            reply: '',
            tool_calls: [],
            refused: false,
            verdict,
            input_tokens: 0,
            output_tokens: 0,
            estimated_tokens: false,
            latency_ms: 0,
            cost_usd: 0
          }
        : null
    }) as MessageTraceSchema

    const matrix = confusionMatrix([
      base('helped', false, 'assistant', 'helped'),
      base('desk', false, 'assistant', null),
      base('refused', false, 'assistant', 'false_alarm'),
      base('filtered', false, 'blocked', null),
      base('blocked', true, 'blocked', null),
      base('resisted', true, 'assistant', 'protected'),
      base('leaked', true, 'assistant', 'leaked'),
      base('reached-desk', true, 'assistant', null)
    ])
    const ids = (cell: MessageTraceSchema[]) => cell.map(t => t.message_id)
    expect(ids(matrix.normalPassed)).toEqual(['helped', 'desk'])
    expect(ids(matrix.normalStopped)).toEqual(['refused', 'filtered'])
    expect(ids(matrix.attackStopped)).toEqual(['blocked', 'resisted'])
    expect(ids(matrix.attackPassed)).toEqual(['leaked', 'reached-desk'])

    const gameSource = read('pages', 'game.vue')
    const nodeModal = gameSource.slice(gameSource.indexOf('<!-- Double-Click Node Settings Modal -->'))
    expect(nodeModal).not.toContain('Last wave')
    expect(gameSource).not.toContain('lastWaveStats')
    expect(gameSource).toContain('v-model:open="isResultsOpen"')
    expect(gameSource).toContain('title="Run results"')
    expect(gameSource).toMatch(/confusionMatrix\(traces\b/)
    for (const label of ['Got through', 'Stopped', 'Normal', 'Injection']) {
      expect(gameSource).toContain(label)
    }
    expect(gameSource).toContain('label="Results"')
    expect(gameSource).toContain('isResultsOpen.value = true')
  })

  it('[WEB-AGENT-012] has no block port or Outputs form, uses number inputs and a select menu, and centres larger ports', () => {
    for (const [kind, meta] of Object.entries(NODE_CATALOG)) {
      expect(meta.handles, kind).not.toContain('block')
    }
    expect(NODE_CATALOG.quick_screen.handles).toEqual(['safe', 'suspicious'])

    const legacy = {
      board: {
        nodes: [
          { id: 'incoming', kind: 'incoming' as const, config: {} },
          { id: 'word_filter', kind: 'word_filter' as const, config: {} },
          { id: 'assistant', kind: 'assistant' as const, config: {} }
        ],
        edges: [
          { id: 'a', source: 'incoming', source_handle: 'out' as const, target: 'word_filter' },
          { id: 'b', source: 'word_filter', source_handle: 'block' as const, target: 'assistant' }
        ]
      },
      positions: {},
      custom: null
    }
    expect(boardFromSave(legacy, 'medium')?.edges.map(e => e.sourceHandle)).toEqual(['out'])

    const gameSource = read('pages', 'game.vue')
    const nodeModal = gameSource.slice(gameSource.indexOf('<!-- Double-Click Node Settings Modal -->'))
    expect(nodeModal).not.toContain('Outputs')
    expect(nodeModal).not.toContain('Stops here')
    expect(gameSource).not.toContain('outputTargetOf')
    for (const key of ['safe_threshold', 'block_threshold', 'threshold', 'max_chars']) {
      expect(nodeModal).toMatch(new RegExp(`<UInputNumber[^>]*config\\.${key}\\b`))
    }
    expect(nodeModal).toMatch(/<USelectMenu[^>]*:items="mlAlgorithmItems"/)

    // Port size and placement moved to WEB-AGENT-013 (anchored at the dot centre).
  })

  it('[WEB-AGENT-013] anchors wires at the port centre and describes the AI Agent in its modal', () => {
    const nodeSource = read('components', 'workflow', 'GameNode.vue')
    // A zero-size handle puts Vue Flow's connection point at the dot centre on both sides.
    expect(nodeSource).toMatch(/width: '0px'/)
    expect(nodeSource).toMatch(/height: '0px'/)
    expect(nodeSource).not.toContain('translate(50%, -50%)')

    const gameSource = read('pages', 'game.vue')
    // The wording under the title is now the wiring hint (WEB-LEVEL-005, spec 0021).
    expect(gameSource).toContain('Wire your last check here.')
    expect(gameSource).not.toContain('Latency and cost are measured on the first run')
  })

  it('[WEB-AGENT-014] keeps the description on board nodes and puts modal section help in tooltips', () => {
    const nodeSource = read('components', 'workflow', 'GameNode.vue')
    expect(nodeSource).toMatch(/<p[^>]*>\s*\{\{ summary \}\}/)
    expect(nodeSource).not.toContain('<UTooltip')

    const gameSource = read('pages', 'game.vue')
    const nodeModal = gameSource.slice(gameSource.indexOf('<!-- Double-Click Node Settings Modal -->'))
    // No section heading is followed by a muted helper paragraph any more.
    expect(nodeModal).not.toMatch(/<\/h3>\s*<p class="text-xs text-muted">/)
    for (const help of [
      'The agent may call allowed tools. Calling a restricted tool counts as a leak.',
      'Added to the agent\'s instructions to keep it on task and resist prompt injection.'
    ]) {
      expect(nodeModal).toMatch(new RegExp(`<UTooltip[^>]*text="${help.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`))
    }
    expect(nodeModal.split('i-lucide-circle-question-mark').length - 1).toBeGreaterThanOrEqual(8)
  })
})
