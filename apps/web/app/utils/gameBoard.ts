import type { Edge, Node } from '@vue-flow/core'
import type {
  BoardGraphSchema,
  ClearanceStatus,
  HandleKind,
  LevelId,
  MessageTraceSchema,
  NodeKind
} from '../types/api'
import type { NodeStatus } from './pipelineGraph'

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
    handles: ['safe', 'block'],
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
    handles: ['safe', 'block'],
    hasInput: true,
    isAnchor: false
  },
  secret_scan: {
    label: 'Secret scanner',
    subtitle: 'Key and SQL check',
    icon: 'i-lucide-key-round',
    latencyMs: 0.6,
    costUsd: 0,
    handles: ['safe', 'block'],
    hasInput: true,
    isAnchor: false
  },
  ml_classifier: {
    label: 'ML filter',
    subtitle: 'Custom dataset model',
    icon: 'i-lucide-cpu',
    latencyMs: 4.5,
    costUsd: 0,
    handles: ['safe', 'block'],
    hasInput: true,
    isAnchor: false
  },
  quick_screen: {
    label: 'Quick screen',
    subtitle: '3-way risk router',
    icon: 'i-lucide-gauge',
    latencyMs: 3.8,
    costUsd: 0,
    handles: ['safe', 'suspicious', 'block'],
    hasInput: true,
    isAnchor: false
  },
  safety_check: {
    label: 'Safety check',
    subtitle: 'Jailbreak guard',
    icon: 'i-lucide-shield-alert',
    latencyMs: 85.0,
    costUsd: 0.0002,
    handles: ['safe', 'block'],
    hasInput: true,
    isAnchor: false
  },
  agent_review: {
    label: 'Agent review',
    subtitle: 'Dual-agent debate',
    icon: 'i-lucide-scale',
    latencyMs: 920.0,
    costUsd: 0.003,
    handles: ['safe', 'block'],
    hasInput: true,
    isAnchor: false
  },
  tool_filter: {
    label: 'Tool filter',
    subtitle: 'Tool policy gate',
    icon: 'i-lucide-lock',
    latencyMs: 1.0,
    costUsd: 0,
    handles: ['safe', 'block'],
    hasInput: true,
    isAnchor: false
  },
  assistant: {
    label: 'Assistant',
    subtitle: 'Allowed output',
    icon: 'i-lucide-bot',
    latencyMs: 0,
    costUsd: 0,
    handles: [],
    hasInput: true,
    isAnchor: true
  },
  blocked: {
    label: 'Blocked',
    subtitle: 'Stopped traffic',
    icon: 'i-lucide-shield-x',
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
      config: {
        ...defaultConfig,
        ...config
      }
    }
  }
}

export function createStarterBoard(levelId: LevelId = 'easy'): BoardState {
  const targetLabel = levelId === 'easy' ? 'Safe' : 'Assistant'
  const nodes: Node<GameNodeData>[] = [
    makeGameNode('incoming', 'incoming', { x: 60, y: 180 }),
    makeGameNode('assistant', 'assistant', { x: 680, y: 70 }, {}, targetLabel),
    makeGameNode('blocked', 'blocked', { x: 680, y: 300 })
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
  if (!target || target.data?.isAnchor || nodeId === 'incoming' || nodeId === 'assistant' || nodeId === 'blocked') {
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
            flaggedCount: 0
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
    if (node.data.kind === 'blocked' || hop.handle === 'block') {
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
  const hitCounts = new Map<string, number>()
  let assistantTotal = 0
  let assistantLeaked = 0
  let blockedTotal = 0
  let blockedFalseAlarms = 0

  for (const trace of traces) {
    if (trace.outcome === 'assistant') {
      assistantTotal += 1
      if (trace.is_attack) assistantLeaked += 1
    } else if (trace.outcome === 'blocked') {
      blockedTotal += 1
      if (!trace.is_attack) blockedFalseAlarms += 1
    }
    for (const hop of trace.hops) {
      hitCounts.set(hop.node_id, (hitCounts.get(hop.node_id) ?? 0) + 1)
    }
  }

  const nodes = board.nodes.map((node) => {
    if (!node.data) return node
    const hits = hitCounts.get(node.id) ?? 0
    if (node.data.kind === 'assistant') {
      return {
        ...node,
        data: {
          ...node.data,
          hits,
          arrivedCount: assistantTotal,
          flaggedCount: assistantLeaked,
          status: (assistantLeaked > 0 ? 'blocked' : assistantTotal > 0 ? 'passed' : 'idle') as NodeStatus,
          detail: `${assistantTotal} arrived (${assistantLeaked} leaked)`
        }
      }
    }
    if (node.data.kind === 'blocked') {
      return {
        ...node,
        data: {
          ...node.data,
          hits,
          arrivedCount: blockedTotal,
          flaggedCount: blockedFalseAlarms,
          status: (blockedTotal > 0 ? 'blocked' : 'idle') as NodeStatus,
          detail: `${blockedTotal} blocked (${blockedFalseAlarms} false)`
        }
      }
    }
    if (node.data.kind === 'incoming') {
      return {
        ...node,
        data: {
          ...node.data,
          hits,
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
        ...node.data,
        hits,
        status: (hits > 0 ? 'passed' : 'idle') as NodeStatus
      }
    }
  })

  return {
    nodes,
    edges: board.edges
  }
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
