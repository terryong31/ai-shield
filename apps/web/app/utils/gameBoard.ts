import type { Edge, Node } from '@vue-flow/core'
import type {
  BoardGraphSchema,
  SavedBoardRequest,
  ClearanceStatus,
  HandleKind,
  LevelId,
  MessageTraceSchema,
  NodeKind,
  PlayerSessionStatus,
  WaveScoreSchema
} from '../types/api'
import type { NodeStatus } from './pipelineGraph'

export interface NodeTraffic {
  in: number
  pass: number
  block: number
}

export interface GameNodeData {
  kind: NodeKind
  label: string
  subtitle: string
  latencyMs: number
  costUsd: number
  handles: HandleKind[]
  hasInput: boolean
  isAnchor: boolean
  status: NodeStatus
  detail: string
  hits: number
  arrivedCount: number
  flaggedCount: number
  traffic: NodeTraffic
  tokens: number
  config: Record<string, unknown>
}

export interface BoardState {
  nodes: Node<GameNodeData>[]
  edges: Edge[]
}

export const NODE_CATALOG: Record<
  NodeKind,
  {
    label: string
    subtitle: string
    icon: string
    latencyMs: number
    costUsd: number
    handles: HandleKind[]
    hasInput: boolean
    isAnchor: boolean
  }
> = {
  incoming: {
    label: 'Input',
    subtitle: 'Incoming messages',
    icon: 'i-lucide-message-square',
    latencyMs: 0,
    costUsd: 0,
    handles: ['out'],
    hasInput: false,
    isAnchor: true
  },
  word_filter: {
    label: 'Word filter',
    subtitle: 'Keyword rules',
    icon: 'i-lucide-filter',
    latencyMs: 0.4,
    costUsd: 0,
    handles: ['safe'],
    hasInput: true,
    isAnchor: false
  },
  text_cleanup: {
    label: 'Text cleaner',
    subtitle: 'Unpack encoded text',
    icon: 'i-lucide-sparkles',
    latencyMs: 1.0,
    costUsd: 0,
    handles: ['out'],
    hasInput: true,
    isAnchor: false
  },
  length_limit: {
    label: 'Length limit',
    subtitle: 'Max character cap',
    icon: 'i-lucide-ruler',
    latencyMs: 0.2,
    costUsd: 0,
    handles: ['safe'],
    hasInput: true,
    isAnchor: false
  },
  secret_scan: {
    label: 'Secret scanner',
    subtitle: 'Key and SQL check',
    icon: 'i-lucide-key-round',
    latencyMs: 0.6,
    costUsd: 0,
    handles: ['safe'],
    hasInput: true,
    isAnchor: false
  },
  ml_classifier: {
    label: 'ML filter',
    subtitle: 'Custom dataset model',
    icon: 'i-lucide-cpu',
    latencyMs: 4.5,
    costUsd: 0,
    handles: ['safe'],
    hasInput: true,
    isAnchor: false
  },
  quick_screen: {
    label: 'Quick screen',
    subtitle: '3-way risk router',
    icon: 'i-lucide-gauge',
    latencyMs: 3.8,
    costUsd: 0,
    handles: ['safe', 'suspicious'],
    hasInput: true,
    isAnchor: false
  },
  safety_check: {
    label: 'Safety check',
    subtitle: 'Jailbreak guard',
    icon: 'i-lucide-shield-alert',
    latencyMs: 85.0,
    costUsd: 0.0002,
    handles: ['safe'],
    hasInput: true,
    isAnchor: false
  },
  agent_review: {
    label: 'Agent review',
    subtitle: 'Dual-agent debate',
    icon: 'i-lucide-scale',
    latencyMs: 920.0,
    costUsd: 0.003,
    handles: ['safe'],
    hasInput: true,
    isAnchor: false
  },
  tool_filter: {
    label: 'Tool filter',
    subtitle: 'Tool policy gate',
    icon: 'i-lucide-lock',
    latencyMs: 1.0,
    costUsd: 0,
    handles: ['safe'],
    hasInput: true,
    isAnchor: false
  },
  assistant: {
    label: 'Protected Agent',
    subtitle: 'Follows the objective and your rules',
    icon: 'i-lucide-bot',
    latencyMs: 0,
    costUsd: 0,
    handles: [],
    hasInput: true,
    isAnchor: true
  }
}

export function makeGameNode(
  id: string,
  kind: NodeKind,
  position: { x: number, y: number },
  config: Record<string, unknown> = {},
  customLabel?: string
): Node<GameNodeData> {
  const meta = NODE_CATALOG[kind]
  const defaultConfig: Record<string, unknown> = {}
  if (kind === 'quick_screen') {
    defaultConfig.safe_threshold = 0.3
    defaultConfig.block_threshold = 0.75
  } else if (kind === 'ml_classifier') {
    defaultConfig.algorithm = 'logistic_regression'
    defaultConfig.threshold = 0.5
    defaultConfig.dataset = []
  } else if (kind === 'length_limit') {
    defaultConfig.max_chars = 240
  } else if (kind === 'word_filter') {
    defaultConfig.groups = ['override', 'encoded', 'sql_tools']
    defaultConfig.custom_words = []
  } else if (kind === 'assistant') {
    defaultConfig.rules = []
  }

  return {
    id,
    type: 'gameNode',
    position,
    deletable: !meta.isAnchor,
    data: {
      kind,
      label: customLabel ?? meta.label,
      subtitle: meta.subtitle,
      latencyMs: meta.latencyMs,
      costUsd: meta.costUsd,
      handles: [...meta.handles],
      hasInput: meta.hasInput,
      isAnchor: meta.isAnchor,
      status: 'idle',
      detail: 'Ready',
      hits: 0,
      arrivedCount: 0,
      flaggedCount: 0,
      traffic: { in: 0, pass: 0, block: 0 },
      tokens: 0,
      config: {
        ...defaultConfig,
        ...config
      }
    }
  }
}

/** Easy is classification only: it ends at a Help Desk and runs no model (spec 0021). */
export const FINAL_NODE_LABELS: Record<LevelId, string> = {
  easy: 'Help Desk',
  medium: 'Protected Agent',
  hard: 'Protected Agent'
}

export function isClassifyOnlyLevel(levelId: LevelId): boolean {
  return levelId === 'easy'
}

export function createStarterBoard(levelId: LevelId = 'easy'): BoardState {
  // Every level ends at one final node; prompts that never reach it count as blocked (spec 0020).
  const nodes: Node<GameNodeData>[] = [
    makeGameNode('incoming', 'incoming', { x: 60, y: 180 }),
    makeGameNode('assistant', 'assistant', { x: 720, y: 180 }, {}, FINAL_NODE_LABELS[levelId])
  ]
  return { nodes, edges: [] }
}

export function addCheckNode(
  board: BoardState,
  kind: NodeKind,
  position: { x: number, y: number }
): BoardState {
  const existingIds = new Set(board.nodes.map(n => n.id))
  let id: string = kind
  let suffix = 2
  while (existingIds.has(id)) {
    id = `${kind}_${suffix}`
    suffix += 1
  }
  const nextNode = makeGameNode(id, kind, position)
  return {
    nodes: [...board.nodes, nextNode],
    edges: [...board.edges]
  }
}

export function removeBoardNode(board: BoardState, nodeId: string): BoardState {
  const target = board.nodes.find(n => n.id === nodeId)
  if (!target || target.data?.isAnchor || nodeId === 'incoming' || nodeId === 'assistant') {
    return board
  }
  return {
    nodes: board.nodes.filter(n => n.id !== nodeId),
    edges: board.edges.filter(e => e.source !== nodeId && e.target !== nodeId)
  }
}

export function connectBoardEdge(
  board: BoardState,
  params: { source: string, sourceHandle?: string | null, target: string }
): BoardState {
  const handle = (params.sourceHandle || 'out') as HandleKind
  if (params.source === params.target) {
    return board
  }
  const filtered = board.edges.filter(
    e => !(e.source === params.source && (e.sourceHandle || 'out') === handle)
  )
  const id = `e-${params.source}-${handle}-${params.target}`
  return {
    nodes: [...board.nodes],
    edges: [
      ...filtered,
      {
        id,
        source: params.source,
        sourceHandle: handle,
        target: params.target,
        animated: false
      }
    ]
  }
}

export function removeBoardEdge(board: BoardState, edgeId: string): BoardState {
  return {
    nodes: [...board.nodes],
    edges: board.edges.filter(e => e.id !== edgeId)
  }
}

/** What the Save button sends (spec 0023): the board plus node positions. */
export function saveFromBoard(
  board: BoardState,
  custom: SavedBoardRequest['custom'] = null
): SavedBoardRequest {
  const positions: SavedBoardRequest['positions'] = {}
  for (const node of board.nodes) {
    positions[node.id] = { x: Math.round(node.position.x), y: Math.round(node.position.y) }
  }
  return { board: toApiBoard(board), positions, custom }
}

/** Changes when the board, a setting or a node position changes; drives the unsaved dot. */
export function boardSignature(board: BoardState, extra: unknown = null): string {
  return JSON.stringify([saveFromBoard(board), extra])
}

/** Rebuild a board from a save, or ``null`` when it no longer fits the current game. */
export function boardFromSave(save: SavedBoardRequest, levelId: LevelId): BoardState | null {
  const kinds = save.board.nodes.map(n => n.kind)
  if (!kinds.includes('incoming') || !kinds.includes('assistant')) return null
  if (kinds.some(kind => !(kind in NODE_CATALOG))) return null
  const nodes = save.board.nodes.map((n) => {
    const kind = n.kind as NodeKind
    const position = save.positions?.[n.id] ?? { x: 0, y: 0 }
    const label = kind === 'assistant' ? FINAL_NODE_LABELS[levelId] : undefined
    return makeGameNode(n.id, kind, { x: position.x, y: position.y }, n.config, label)
  })
  const ids = new Set(nodes.map(n => n.id))
  let board: BoardState = { nodes, edges: [] }
  for (const edge of save.board.edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) return null
    // Older saves may wire a block output, which no longer exists (WEB-AGENT-012).
    const sourceNode = nodes.find(n => n.id === edge.source)
    if (!sourceNode?.data?.handles.includes(edge.source_handle)) continue
    board = connectBoardEdge(board, { source: edge.source, sourceHandle: edge.source_handle, target: edge.target })
  }
  return board
}

export function toApiBoard(board: BoardState): BoardGraphSchema {
  return {
    nodes: board.nodes.map(n => ({
      id: n.id,
      kind: (n.data?.kind ?? 'quick_screen') as NodeKind,
      config: { ...(n.data?.config ?? {}) }
    })),
    edges: board.edges.map(e => ({
      id: e.id,
      source: e.source,
      source_handle: (e.sourceHandle || 'out') as HandleKind,
      target: e.target
    }))
  }
}

export function resetBoardStatuses(board: BoardState): BoardState {
  return {
    nodes: board.nodes.map(node => ({
      ...node,
      data: node.data
        ? {
            ...node.data,
            status: 'idle',
            detail: 'Ready',
            hits: 0,
            arrivedCount: 0,
            flaggedCount: 0,
            traffic: { in: 0, pass: 0, block: 0 },
            tokens: 0
          }
        : undefined
    })),
    edges: board.edges.map(edge => ({
      ...edge,
      animated: false
    }))
  }
}

export function applyMessageTrace(board: BoardState, trace: MessageTraceSchema): BoardState {
  const hopByNode = new Map(trace.hops.map(h => [h.node_id, h]))
  const traversedPairs = new Set<string>()
  for (let i = 0; i < trace.hops.length - 1; i++) {
    const curr = trace.hops[i]
    const next = trace.hops[i + 1]
    if (curr && next) {
      traversedPairs.add(`${curr.node_id}->${next.node_id}`)
    }
  }

  const nodes = board.nodes.map((node) => {
    if (!node.data) return node
    const hop = hopByNode.get(node.id)
    if (!hop) {
      return {
        ...node,
        data: {
          ...node.data,
          status: 'idle' as NodeStatus
        }
      }
    }

    let status: NodeStatus = 'passed'
    if (hop.handle === 'block') {
      status = 'blocked'
    } else if (hop.handle === 'suspicious') {
      status = 'flagged'
    }

    return {
      ...node,
      data: {
        ...node.data,
        status,
        detail: hop.detail,
        hits: node.data.hits + 1
      }
    }
  })

  const edges = board.edges.map(edge => ({
    ...edge,
    animated: traversedPairs.has(`${edge.source}->${edge.target}`)
  }))

  return { nodes, edges }
}

export function applyWaveSummary(board: BoardState, traces: MessageTraceSchema[]): BoardState {
  const traffic = summarizeNodeTraffic(traces)
  const travelled = new Set(travelledEdgeIds(board, traces))
  const reachedAgent = traces.filter(t => t.outcome === 'assistant')
  const leaked = reachedAgent.filter(t => t.agent?.verdict === 'leaked').length

  const nodes = board.nodes.map((node) => {
    if (!node.data) return node
    const counts = traffic[node.id] ?? { in: 0, pass: 0, block: 0 }
    const base = { ...node.data, hits: counts.in, traffic: counts }
    if (node.data.kind === 'assistant') {
      return {
        ...node,
        data: {
          ...base,
          arrivedCount: reachedAgent.length,
          flaggedCount: leaked,
          tokens: reachedAgent.reduce(
            (sum, t) => sum + (t.agent ? t.agent.input_tokens + t.agent.output_tokens : 0),
            0
          ),
          status: (leaked > 0 ? 'blocked' : reachedAgent.length > 0 ? 'passed' : 'idle') as NodeStatus,
          detail: `${reachedAgent.length} arrived (${leaked} leaked)`
        }
      }
    }
    if (node.data.kind === 'incoming') {
      return {
        ...node,
        data: {
          ...base,
          arrivedCount: traces.length,
          flaggedCount: 0,
          status: (traces.length > 0 ? 'passed' : 'idle') as NodeStatus,
          detail: `${traces.length} sent`
        }
      }
    }
    return {
      ...node,
      data: {
        ...base,
        status: (counts.in > 0 ? 'passed' : 'idle') as NodeStatus
      }
    }
  })

  return {
    nodes,
    edges: board.edges.map(edge => ({ ...edge, animated: travelled.has(edge.id) }))
  }
}

/** Every node and edge shows the run is in progress until the response arrives. */
export function markBoardRunning(board: BoardState): BoardState {
  return {
    nodes: board.nodes.map(node => (node.data
      ? { ...node, data: { ...node.data, status: 'active' as NodeStatus, detail: 'Running' } }
      : node)),
    edges: board.edges.map(edge => ({ ...edge, animated: true }))
  }
}

/** Per-node counts of prompts that arrived, passed on, or were stopped there. */
export function summarizeNodeTraffic(traces: MessageTraceSchema[]): Record<string, NodeTraffic> {
  const traffic: Record<string, NodeTraffic> = {}
  for (const trace of traces) {
    for (const hop of trace.hops) {
      const counts = (traffic[hop.node_id] ??= { in: 0, pass: 0, block: 0 })
      counts.in += 1
      if (hop.handle === 'block') counts.block += 1
      else counts.pass += 1
    }
  }
  return traffic
}

/** Edges at least one prompt travelled along, in board order. */
export function travelledEdgeIds(board: BoardState, traces: MessageTraceSchema[]): string[] {
  const used = new Set<string>()
  for (const trace of traces) {
    for (let i = 0; i < trace.hops.length - 1; i++) {
      const hop = trace.hops[i]
      const next = trace.hops[i + 1]
      if (hop && next) used.add(`${hop.node_id}|${hop.handle}|${next.node_id}`)
    }
  }
  return board.edges
    .filter(e => used.has(`${e.source}|${e.sourceHandle || 'out'}|${e.target}`))
    .map(e => e.id)
}

/** Output handles with no wire: prompts leaving through them stop there and count as blocked. */
export function unwiredHandles(nodeId: string, handles: HandleKind[], edges: Edge[]): HandleKind[] {
  return handles.filter(handle => !edges.some(e => e.source === nodeId && (e.sourceHandle || 'out') === handle))
}

export const AGENT_RULE_LIMIT = 5
export const AGENT_RULE_MAX_CHARS = 200

export function agentRulesFrom(config: Record<string, unknown>): string[] {
  const raw = config.rules
  return Array.isArray(raw) ? raw.filter((rule): rule is string => typeof rule === 'string') : []
}

export function canAddAgentRule(rules: string[]): boolean {
  return rules.length < AGENT_RULE_LIMIT
}

export function addAgentRule(rules: string[], text: string): string[] {
  const rule = text.trim().slice(0, AGENT_RULE_MAX_CHARS)
  if (!rule || !canAddAgentRule(rules)) return rules
  return [...rules, rule]
}

const TOOL_NAME_ACRONYMS: Record<string, string> = { sql: 'SQL', sku: 'SKU', hr: 'HR', id: 'ID' }

/** Shows a tool identifier as plain words: `lookup_order` becomes `Lookup Order`. */
export function formatToolName(name: string): string {
  return name
    .split('_')
    .filter(Boolean)
    .map(word => TOOL_NAME_ACRONYMS[word] ?? word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function needsSignInPrompt(session: PlayerSessionStatus): boolean {
  return session.is_anonymous
}

/** Runs of this kind left today, or ``null`` when the tier has no limit. */
export function runsRemaining(session: PlayerSessionStatus, kind: 'wave' | 'test'): number | null {
  const limit = kind === 'wave' ? session.daily_wave_limit : session.daily_test_limit
  const used = kind === 'wave' ? session.wave_runs_used : session.test_runs_used
  if (limit === null || limit === undefined) return null
  return Math.max(0, limit - used)
}

/** A wave sets a new record only when it beats an earlier high score. */
export function isNewRecord(previous: number | null, score: number): boolean {
  return previous !== null && score > previous
}

/** Best wave score so far; a lower new score never replaces it. */
export function nextHighScore(previous: number | null, score: number): number {
  return previous === null ? score : Math.max(previous, score)
}

/** Header counter of wave runs left today, or '' when the tier has no limit. */
export function attemptsLeftLabel(session: PlayerSessionStatus): string {
  const left = runsRemaining(session, 'wave')
  if (left === null) return ''
  return `${left}/${session.daily_wave_limit} attempts left today`
}

export function scoreBreakdown(
  score: WaveScoreSchema,
  levelId?: LevelId
): Array<{ label: string, points: number }> {
  const agentRows = levelId && isClassifyOnlyLevel(levelId)
    ? []
    : [
        { label: 'Tool use', points: score.tool_points },
        { label: 'Tokens', points: score.token_points }
      ]
  return [
    { label: 'Protection', points: score.protection_points },
    { label: 'Helpfulness', points: score.helpfulness_points },
    ...agentRows,
    { label: 'Speed', points: score.speed_points },
    { label: 'Cost', points: score.cost_points },
    { label: 'Leak penalty', points: -score.leak_penalty }
  ]
}

export function resolveConsoleAccess(status: ClearanceStatus): {
  allowed: boolean
  reason: string | null
} {
  if (status.granted) {
    return { allowed: true, reason: null }
  }
  return { allowed: false, reason: 'Admin access required' }
}

export function isAiAgentNode(kind: NodeKind): boolean {
  return kind === 'safety_check' || kind === 'agent_review'
}

export function canUseNodeKind(kind: NodeKind, session: PlayerSessionStatus): boolean {
  if (isAiAgentNode(kind)) {
    return !session.is_anonymous && session.ai_nodes_allowed
  }
  return true
}

export function formatCheckCost(costUsd: number): string {
  return costUsd > 0 ? `$${costUsd.toFixed(4)}` : 'Free'
}

export function nodeCostLine(latencyMs: number, costUsd: number): string {
  return `${Number(latencyMs.toFixed(1))} ms per message · ${formatCheckCost(costUsd)}`
}

const MEDAL_STARS: Record<WaveScoreSchema['medal'], number> = { none: 0, bronze: 1, silver: 2, gold: 3 }

export function starsForMedal(medal: WaveScoreSchema['medal']): number {
  return MEDAL_STARS[medal]
}

/** Stars of the high-score wave: a new wave's stars replace them only when it sets the high score. */
export function nextHighStars(
  previousScore: number | null,
  previousStars: number,
  score: number,
  medal: WaveScoreSchema['medal']
): number {
  return previousScore === null || score > previousScore ? starsForMedal(medal) : previousStars
}

export interface ConfusionMatrix {
  normalPassed: MessageTraceSchema[]
  normalStopped: MessageTraceSchema[]
  attackStopped: MessageTraceSchema[]
  attackPassed: MessageTraceSchema[]
}

/**
 * Where each prompt of a run ended up (WEB-AGENT-011). A normal prompt got through when it
 * reached the final node and the agent (if any) served it; an injection was stopped when it
 * never reached the final node or the agent resisted it. Mirrors the engine's scoring.
 */
export function confusionMatrix(traces: MessageTraceSchema[]): ConfusionMatrix {
  const matrix: ConfusionMatrix = { normalPassed: [], normalStopped: [], attackStopped: [], attackPassed: [] }
  for (const trace of traces) {
    const reached = trace.outcome === 'assistant'
    if (trace.is_attack) {
      const stopped = !reached || trace.agent?.verdict === 'protected'
      matrix[stopped ? 'attackStopped' : 'attackPassed'].push(trace)
    } else {
      const served = reached && (!trace.agent || trace.agent.verdict === 'helped')
      matrix[served ? 'normalPassed' : 'normalStopped'].push(trace)
    }
  }
  return matrix
}

export function formatQuotaSummary(session: PlayerSessionStatus): string {
  if (session.is_anonymous || session.tier === 'anonymous' || session.tier === 'paid') {
    return ''
  }
  const waveLimit = session.daily_wave_limit ?? 5
  const testLimit = session.daily_test_limit ?? 20
  const wavesLeft = Math.max(0, waveLimit - session.wave_runs_used)
  const testsLeft = Math.max(0, testLimit - session.test_runs_used)
  return `${session.player_name} (Free): ${wavesLeft}/${waveLimit} waves, ${testsLeft}/${testLimit} tests left today`
}
