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
  RunStopSchema,
  ScoreRecord,
  WaveScoreSchema
} from '../types/api'
import { formatPassEnd } from './billing'

/** A board node's state during and after a wave. */
export type NodeStatus = 'idle' | 'active' | 'passed' | 'flagged' | 'blocked' | 'skipped'

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
    subtitle: 'ML based router',
    icon: 'i-lucide-cpu',
    latencyMs: 4.5,
    costUsd: 0,
    handles: ['safe', 'suspicious'],
    hasInput: true,
    isAnchor: false
  },
  jev: {
    label: 'Jev',
    subtitle: 'System One noul decider',
    icon: 'i-lucide-zap',
    latencyMs: 12.0,
    costUsd: 0.00005,
    handles: ['safe'],
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
  llm_review: {
    label: 'LLM review',
    subtitle: 'Single LLM judge',
    icon: 'i-lucide-brain-circuit',
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

export const SAFETY_CHECK_MODELS = [
  { label: 'GPT-OSS Safeguard 20B', value: 'openai/gpt-oss-safeguard-20b' },
  { label: 'Llama Prompt Guard 2 86M', value: 'meta-llama/llama-prompt-guard-2-86m' },
  { label: 'Llama Prompt Guard 2 22M', value: 'meta-llama/llama-prompt-guard-2-22m' }
] as const

export const LLM_REVIEW_MODELS = [
  { label: 'Gemini 3.5 Flash-Lite', value: 'gemini-3.5-flash-lite' },
  { label: 'GPT-OSS 120B', value: 'openai/gpt-oss-120b' },
  { label: 'GPT-OSS 20B', value: 'openai/gpt-oss-20b' },
  { label: 'Qwen 3.8 27B', value: 'qwen/qwen3.8-27b' }
] as const

export const DEFAULT_SAFETY_CHECK_MODEL = SAFETY_CHECK_MODELS[0].value
export const DEFAULT_LLM_REVIEW_MODEL = LLM_REVIEW_MODELS[0].value

/** Whether a node's model can think before answering; Prompt Guard only scores (WEB-CHECK-003). */
export function nodeSupportsThinking(kind: NodeKind | string, model: string): boolean {
  if (kind === 'llm_review') return true
  if (kind === 'safety_check') return !model.startsWith('meta-llama/llama-prompt-guard')
  return false
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
  if (kind === 'jev') {
    defaultConfig.question = ''
    defaultConfig.threshold = 0.7
    defaultConfig.tool_policy_enabled = false
    defaultConfig.block_tools = []
  } else if (kind === 'text_cleanup') {
    defaultConfig.transforms = []
  } else if (kind === 'ml_classifier') {
    defaultConfig.algorithm = 'tfidf'
    defaultConfig.safe_threshold = 0.3
    defaultConfig.block_threshold = 0.75
    defaultConfig.dataset = []
  } else if (kind === 'length_limit') {
    defaultConfig.max_chars = 240
  } else if (kind === 'word_filter') {
    defaultConfig.custom_words = []
  } else if (kind === 'secret_scan') {
    defaultConfig.patterns = []
  } else if (kind === 'tool_filter') {
    defaultConfig.rules = []
    defaultConfig.blocked_tools = []
  } else if (kind === 'safety_check') {
    defaultConfig.model = DEFAULT_SAFETY_CHECK_MODEL
    defaultConfig.thinking = false
    defaultConfig.tool_policy_enabled = false
    defaultConfig.block_tools = []
  } else if (kind === 'llm_review') {
    defaultConfig.model = DEFAULT_LLM_REVIEW_MODEL
    defaultConfig.thinking = false
    defaultConfig.prompt = ''
    defaultConfig.tool_policy_enabled = false
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

export const ALL_LEVEL_IDS: readonly LevelId[] = [
  'easy-1', 'easy-2', 'easy-3', 'easy-4', 'easy-5',
  'medium-1', 'medium-2', 'medium-3', 'medium-4', 'medium-5',
  'medium-6', 'medium-7', 'medium-8', 'medium-9', 'medium-10',
  'hard-1', 'hard-2', 'hard-3', 'hard-4', 'hard-5',
  'hard-6', 'hard-7', 'hard-8'
]

const ALL_LEVEL_ID_SET = new Set<string>(ALL_LEVEL_IDS)

export function isValidLevelId(value: unknown): value is LevelId {
  return typeof value === 'string' && ALL_LEVEL_ID_SET.has(value)
}

/** Easy is classification only: it ends at a Help Desk and runs no model (spec 0021). */
export const FINAL_NODE_LABELS: Record<LevelId, string> = {
  'easy-1': 'Help Desk',
  'easy-2': 'Help Desk',
  'easy-3': 'Help Desk',
  'easy-4': 'Help Desk',
  'easy-5': 'Help Desk',
  'medium-1': 'Protected Agent',
  'medium-2': 'Protected Agent',
  'medium-3': 'Protected Agent',
  'medium-4': 'Protected Agent',
  'medium-5': 'Protected Agent',
  'medium-6': 'Protected Agent',
  'medium-7': 'Protected Agent',
  'medium-8': 'Protected Agent',
  'medium-9': 'Protected Agent',
  'medium-10': 'Protected Agent',
  'hard-1': 'Protected Agent',
  'hard-2': 'Protected Agent',
  'hard-3': 'Protected Agent',
  'hard-4': 'Protected Agent',
  'hard-5': 'Protected Agent',
  'hard-6': 'Protected Agent',
  'hard-7': 'Protected Agent',
  'hard-8': 'Protected Agent'
}

export function isClassifyOnlyLevel(levelId: LevelId): boolean {
  return levelId.startsWith('easy-')
}

export function createStarterBoard(levelId: LevelId = 'easy-1'): BoardState {
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
    nodes: board.nodes.map((n) => {
      const config = { ...(n.data?.config ?? {}) }
      if (n.data?.kind === 'ml_classifier') {
        delete config.dataset
        delete config.retrainNeeded
      }
      return {
        id: n.id,
        kind: (n.data?.kind ?? 'ml_classifier') as NodeKind,
        config
      }
    }),
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
        latencyMs: hop.latency_ms,
        costUsd: hop.cost_usd,
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
  return `${left} / ${session.daily_wave_limit} runs left today`
}

/**
 * The score parts of a run (WEB-FAIR-002). A cleared run shows the five parts of the
 * spec 0050 formula; a run that did not clear has one part, from attacks and normal prompts.
 */
export function scoreBreakdown(
  score: WaveScoreSchema,
  _levelId?: LevelId
): Array<{ label: string, points: number }> {
  if (!score.won) {
    return [{ label: 'Attacks and normal prompts', points: score.total_score }]
  }
  return [
    { label: 'Cleared', points: score.cleared_points ?? 0 },
    { label: 'Accuracy', points: score.accuracy_points ?? 0 },
    { label: 'Speed', points: score.speed_points },
    { label: 'Cost', points: score.cost_points },
    { label: 'Simplicity', points: score.simplicity_points ?? 0 }
  ]
}

/** The stat boxes above the points; agent tokens only where the level has an agent. */
export function breakdownStats(
  score: WaveScoreSchema,
  levelId: LevelId
): Array<{ icon: string, label: string, value: string }> {
  const stats = [
    { icon: 'i-lucide-timer', label: 'Avg latency', value: `${score.avg_latency_ms.toFixed(1)} ms` },
    { icon: 'i-lucide-coins', label: 'Cost', value: `$${score.total_cost_usd.toFixed(4)}` }
  ]
  if (!isClassifyOnlyLevel(levelId)) {
    stats.push({ icon: 'i-lucide-cpu', label: 'Agent tokens', value: score.total_tokens.toLocaleString() })
  }
  return stats
}

function formatMs(ms: number): string {
  return `${Number(ms.toFixed(2))} ms`
}

function formatUsd(usd: number): string {
  return `$${Number(usd.toFixed(5))}`
}

/** One sentence for a run that a limit stopped (WEB-FAIR-003). */
export function stopSummary(
  stop: RunStopSchema,
  promptCount: number,
  labelFor: (nodeId: string) => string
): string {
  const where = `at prompt ${stop.prompt_index} of ${promptCount}`
  if (stop.reason === 'time_limit') {
    const step = stop.path.find(s => s.node_id === stop.node_id)
    const takes = step ? formatMs(step.latency_ms) : formatMs(stop.used)
    return `Time limit exceeded ${where}: ${labelFor(stop.node_id)} takes ${takes}, the limit is ${formatMs(stop.limit)}.`
  }
  return `Budget exceeded ${where}: the run cost ${formatUsd(stop.used)}, the budget is ${formatUsd(stop.limit)}.`
}

/** The stopped prompt's path, each node with its latency or cost, and the node that went over. */
export function stopPath(
  stop: RunStopSchema,
  labelFor: (nodeId: string) => string
): Array<{ label: string, value: string, over: boolean }> {
  return stop.path.map(step => ({
    label: labelFor(step.node_id),
    value: stop.reason === 'time_limit' ? formatMs(step.latency_ms) : formatUsd(step.cost_usd),
    over: step.node_id === stop.node_id
  }))
}

const FAMILY_NAMES: Record<string, string> = {
  normal: 'Normal request'
}

/** A prompt family as a player reads it: `tool_exploit` is `Tool exploit`. */
export function familyName(category: string): string {
  const known = FAMILY_NAMES[category]
  if (known) return known
  const words = category.split('_').join(' ').trim()
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : 'Prompt'
}

/**
 * Rows of a result cell (WEB-FAIR-004): the prompt number, its family and the node that
 * stopped it. Campaign prompts stay hidden, so there is no text and no badge.
 */
export function promptRows(
  items: MessageTraceSchema[],
  wave: MessageTraceSchema[],
  labelFor: (nodeId: string) => string
): Array<{ key: string, title: string, detail: string }> {
  return items.map((item) => {
    const number = wave.findIndex(t => t.message_id === item.message_id) + 1
    const stopper = [...item.hops].reverse().find(h => h.handle === 'block')
    let detail = ''
    if (stopper) {
      const score = stopper.score ?? null
      const scoreText = score === null ? '' : ` (score ${Number(score.toFixed(2))})`
      detail = `Stopped by ${labelFor(stopper.node_id)}${scoreText}`
    } else if (item.outcome === 'assistant') {
      detail = item.agent?.verdict === 'protected' ? 'Refused by the agent' : 'Got through'
    }
    return { key: item.message_id, title: `Prompt ${number} · ${familyName(item.category ?? '')}`, detail }
  })
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
  return kind === 'jev' || kind === 'safety_check' || kind === 'llm_review'
}

export interface NodeKeyState {
  jevKeyAvailable: boolean
  aiKeyAvailable: boolean
}

export function canUseNodeKind(
  kind: NodeKind,
  session: PlayerSessionStatus,
  keys?: NodeKeyState
): boolean {
  if (isAiAgentNode(kind)) {
    const signedIn = !session.is_anonymous && session.ai_nodes_allowed
    if (!keys) return signedIn
    return signedIn && (kind === 'jev' ? keys.jevKeyAvailable : keys.aiKeyAvailable)
  }
  return true
}

export function nodeKeyRequirement(kind: NodeKind, keys: NodeKeyState): string | null {
  if (kind === 'jev' && !keys.jevKeyAvailable) {
    return 'Insert Jev API key to continue: add TYPESAFE_API_KEY in system .env.'
  }
  if ((kind === 'safety_check' || kind === 'llm_review') && !keys.aiKeyAvailable) {
    return 'Enter API key to continue: add GROQ_API_KEY or GOOGLE_API_KEY in system .env.'
  }
  return null
}

export function formatCheckCost(costUsd: number): string {
  return costUsd > 0 ? `$${costUsd.toFixed(4)}` : 'Free'
}

export function nodeCostLine(latencyMs: number, costUsd: number): string {
  return `${Number(latencyMs.toFixed(1))} ms per message · ${formatCheckCost(costUsd)}`
}

/** Same rule as the Level Select tiles: a win, a gold medal and a mastered Follow-up each add a star. */
export function waveStars(score: Pick<WaveScoreSchema, 'won' | 'medal' | 'follow_up_passed'>): number {
  if (!score.won) return 0
  return 1 + (score.medal === 'gold' ? 1 : 0) + (score.follow_up_passed ? 1 : 0)
}

/** Stars of the high-score wave: a new wave's stars replace them only when it sets the high score. */
export function nextHighStars(
  previousScore: number | null,
  previousStars: number,
  score: number,
  stars: number
): number {
  return previousScore === null || score > previousScore ? stars : previousStars
}

export function waveOutcomeSummary(score: WaveScoreSchema): string {
  if (score.won) {
    return 'All attacks stopped and all normal prompts helped.'
  }
  const reasons: string[] = []
  if (score.attacks_leaked > 0 && score.false_alarms > 0) {
    reasons.push(`${score.attacks_leaked} attack(s) got through and ${score.false_alarms} normal prompt(s) were blocked.`)
  } else if (score.attacks_leaked > 0) {
    reasons.push(`${score.attacks_leaked} attack(s) got into the system.`)
  } else if (score.false_alarms > 0) {
    reasons.push(`${score.false_alarms} normal prompt(s) were blocked or refused.`)
  }
  reasons.push(...(score.constraint_violations ?? []))
  return reasons.join(' ') || 'Defeat'
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

export interface PlanCard {
  title: 'Free' | 'Paid'
  description: string
  price: string
  billingCycle?: string
  features: string[]
  highlight: boolean
  badge?: string
  terms?: string
  button?: { label: string, to?: string, disabled?: boolean, loading?: boolean, color: 'neutral', variant: 'solid' | 'outline' }
  /** Set when the button upgrades the player instead of linking somewhere. */
  action?: 'upgrade' | 'checkout'
}

/** Plans shown on /plans (WEB-GAME-014). Limits mirror the gateway's DAILY_LIMITS. */
export function planCards(
  session: PlayerSessionStatus,
  options: { selfUpgradeEnabled?: boolean, billingEnabled?: boolean, pending?: boolean } = {}
): PlanCard[] {
  const selfUpgradeEnabled = options.selfUpgradeEnabled ?? true
  const anonymous = session.is_anonymous || session.tier === 'anonymous'
  const signIn = { label: 'Sign in', to: '/auth/login', color: 'neutral' as const, variant: 'outline' as const }
  const current = { label: 'Current plan', disabled: true, color: 'neutral' as const, variant: 'outline' as const }

  const free: PlanCard = {
    title: 'Free',
    description: 'For players who sign in.',
    price: '$0',
    highlight: false,
    features: ['5 wave runs a day', '20 tests a day', 'AI agent tools', 'Scores on the leaderboard']
  }
  const paid: PlanCard = {
    title: 'Paid',
    description: 'For players who defend every day.',
    price: '$0',
    billingCycle: '/month',
    highlight: true,
    features: [
      '300 wave runs a day',
      '1,000 tests a day',
      'Everything in Free',
      'Custom sandbox with your own dataset and model key'
    ]
  }

  // The usual price holds while the state loads, so nothing moves when it arrives (WEB-BILL-006).
  if (options.billingEnabled || options.pending) {
    Object.assign(paid, {
      price: '$5',
      billingCycle: '/30 days',
      features: [...paid.features, 'One payment, does not renew']
    })
  }

  if (anonymous) return [{ ...free, button: signIn }, { ...paid, button: { ...signIn, variant: 'solid' } }]
  if (options.pending) {
    const label = session.tier === 'paid' ? 'Extend' : 'Buy 30-day pass'
    const button = { label, disabled: true, loading: true, color: 'neutral' as const, variant: 'solid' as const }
    return [session.tier === 'paid' ? free : { ...free, button: current }, { ...paid, button }]
  }
  if (session.tier === 'paid') {
    if (!options.billingEnabled || !session.paid_until) return [free, { ...paid, button: current }]
    return [free, {
      ...paid,
      description: `Your pass ends on ${formatPassEnd(session.paid_until)}.`,
      button: { label: 'Extend', color: 'neutral', variant: 'solid' },
      action: 'checkout'
    }]
  }
  if (options.billingEnabled) {
    return [
      { ...free, button: current },
      { ...paid, button: { label: 'Buy 30-day pass', color: 'neutral', variant: 'solid' }, action: 'checkout' }
    ]
  }
  return [
    { ...free, button: current },
    selfUpgradeEnabled
      ? { ...paid, button: { label: 'Upgrade to Paid', color: 'neutral', variant: 'solid' }, action: 'upgrade' }
      : { ...paid, button: { label: 'Coming soon', disabled: true, color: 'neutral', variant: 'solid' } }
  ]
}

/**
 * Retry a model-gated run once after creating an anonymous session when the gateway answers 401 (WEB-SPEND-004).
 */
export async function runWithAnonymousRetry<T>(
  run: () => Promise<T>,
  signInAnonymously: () => Promise<unknown>
): Promise<T> {
  try {
    return await run()
  } catch (err) {
    const e = err as { statusCode?: number, status?: number, response?: { status?: number } }
    const status = e.statusCode ?? e.status ?? e.response?.status
    if (status !== 401) throw err
    await signInAnonymously()
    return await run()
  }
}

export interface ConsoleScoreStats {
  scores: number
  players: number
  byLevel: { easy: number, medium: number, hard: number }
  medals: Record<WaveScoreSchema['medal'], number>
}

/** Stat tiles for the admin console Overview, from the recorded scores (spec 0026). */
export function consoleScoreStats(records: ScoreRecord[]): ConsoleScoreStats {
  const byLevel = { easy: 0, medium: 0, hard: 0 }
  const medals: Record<WaveScoreSchema['medal'], number> = { gold: 0, silver: 0, bronze: 0, none: 0 }
  for (const record of records) {
    if (record.level_id.startsWith('easy-')) byLevel.easy += 1
    else if (record.level_id.startsWith('medium-')) byLevel.medium += 1
    else if (record.level_id.startsWith('hard-')) byLevel.hard += 1
    medals[record.medal] += 1
  }
  return {
    scores: records.length,
    players: new Set(records.map(r => r.player_name)).size,
    byLevel,
    medals
  }
}
